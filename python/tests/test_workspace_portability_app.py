"""Opt-in production API roundtrip with a real Symphony H5 fixture.

Set RIEKE_TEST_PORTABLE_APP=1 and RIEKE_PORTABILITY_H5=/path/to/recording.h5.
All writes target disposable projects; the supplied recording is read only.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import workspace_portability as transfer
from workspace_projects import create_project_at
from workspace_project_database import ensure_project_database
from workspace_recording_files import retain_recording


API_CHECK = r'''
import json, sys, uuid
from pathlib import Path
from workspace_api import create_app
root, parser, receipt, mode = map(str, sys.argv[1:])
if mode == 'seed':
    from recording_workspace import write_json
    write_json(Path(root) / 'logs/app-jobs' / (str(uuid.uuid4()) + '.json'),
               {'status': 'failed', 'source': '/historical/sender/failed.h5',
                'error': 'Preserved diagnostic fixture', 'started_at': '2026-09-29T01:00:00+00:00',
                'finished_at': '2026-09-29T01:00:02+00:00', 'catalog_committed': False})
app = create_app(root, parser)
client = app.test_client()
headers = {'X-Workspace-Request': '1'}
def request(path, body=None, method='GET'):
    response = client.open('/api/' + path, method=method, json=body, headers=headers)
    assert response.status_code < 300, (path, response.status_code, response.get_json())
    payload = response.get_json()
    if path == 'jobs':
        for job in payload['jobs']:
            job.pop('heartbeat_at', None)
    return payload
service = app.extensions['workspace_service']
if mode == 'seed':
    row = next(row for row in service.rows.values() if row['streams'])
    predicate = {'field': 'epoch', 'operator': 'eq', 'value': row['epoch_uuid']}
    recipe = {'name': 'Portable audit query', 'description': 'Recipient reproduction check',
              'predicate': predicate, 'splits': 'cell', 'pinned': True}
    preset = request('search-presets', recipe, 'POST')
    request('search-presets/' + preset['preset_uuid'],
            {**recipe, 'name': 'Portable audit query v2', 'expected_version': 1}, 'PUT')
    request('explore/run', {'predicate': predicate, 'splits': 'cell'}, 'POST')
    revision = request('explore/revisions',
                       {'predicate': predicate, 'splits': 'cell', 'name': 'Portable audit baseline'}, 'POST')
    profile = request('annotation-profiles', {'display_name': 'Portable audit author'}, 'POST')
    request('annotations', {'target_kind': 'epoch', 'target_uuids': [row['epoch_uuid']],
                            'profile_uuid': profile['profile_uuid'], 'tags_add': ['portable-audit'],
                            'expected_revisions': {row['epoch_uuid']: 0}}, 'POST')
    protocol = next(identity for identity in service.protocols
                    if row['epoch_uuid'] in service.fingerprints(identity))
    detail = request('protocols/' + protocol)
    request('protocols/' + protocol + '/curation',
            {'epoch_uuids': [row['epoch_uuid']], 'changes': {'included': False, 'review_state': 'approved'},
             'expected_revisions': {row['epoch_uuid']: 0}, 'query_revision': detail['query_revision']}, 'POST')
    request('protocols/' + protocol + '/tree-layout',
            {'split_order': ['cell', 'block'], 'expected_version': 0}, 'PUT')
    request('project-preferences',
            {'field': 'recent_searches', 'value': [{'id': 'portable-audit-search',
                'name': 'Portable audit recent search', 'predicate': predicate, 'splits': 'cell',
                'pinned': True, 'matched_count': 1, 'cell_count': 1}], 'expected_revision': 0}, 'PUT')
    request('project-preferences',
            {'field': 'protocol_shortcuts', 'value': {protocol: {'section': 'pinned', 'rank': 0}},
             'expected_revision': 0}, 'PUT')
    endpoints = ['search-presets', 'search-presets/' + preset['preset_uuid'] + '/versions',
                 'explore/revisions/' + revision['revision_uuid'],
                 'epochs/' + row['epoch_uuid'] + '/annotations', 'annotation-profiles',
                 'events?limit=100', 'jobs', 'project-preferences', 'protocols/' + protocol + '/masks/export',
                 'protocols/' + protocol + '/tree-layout',
                 'epochs/' + row['epoch_uuid'] + '/trace?stream_uuid=' + row['streams'][0]['uuid'] + '&start=3&count=16']
    expected = {'project_uuid': service.project['project_uuid'], 'epochs': len(service.rows),
                'protocols': sorted(service.protocols),
                'responses': {endpoint: request(endpoint) for endpoint in endpoints}}
    Path(receipt).write_text(json.dumps(expected))
else:
    expected = json.loads(Path(receipt).read_text())
    assert service.project['project_uuid'] == expected['project_uuid']
    assert len(service.rows) == expected['epochs']
    assert sorted(service.protocols) == expected['protocols']
    for endpoint, payload in expected['responses'].items():
        assert request(endpoint) == payload, endpoint
    assert all(Path(manifest['source_path']).is_relative_to(Path(root))
               and Path(manifest['metadata_path']).is_relative_to(Path(root))
               for manifest in service.manifests.values())
    request('overview')
    print('Recipient production API state and waveform checks passed', flush=True)
app.extensions['app_state_session_lock'].close()
service.dj.conn().close()
'''


@unittest.skipUnless(os.environ.get('RIEKE_TEST_PORTABLE_APP') == '1',
                     'opt-in production API/native MySQL integration')
class PortableAppTests(unittest.TestCase):
    def test_recipient_opens_all_saved_scientific_state_without_donor(self):
        source = Path(os.environ['RIEKE_PORTABILITY_H5']).expanduser().resolve(strict=True)
        code = Path(__file__).resolve().parents[2]
        parser = code / '.rieke-runtime/retinanalysis'
        with tempfile.TemporaryDirectory(prefix='rieke-portable-app-') as temporary:
            base = Path(temporary).resolve()
            root, restored = base / 'donor', base / 'recipient'
            create_project_at(str(root), 'Production portability audit')
            runtimes = [root]
            try:
                ensure_project_database(root)
                managed = retain_recording(root, source, transfer._hash(source))
                env = {**os.environ, 'PYTHONPATH': str(code / 'python')}
                self.run_checked([sys.executable, str(code / 'python/recording_workspace.py'),
                                  str(managed), '--project-dir', str(root), '--retinanalysis', str(parser)], env)
                receipt = base / 'expected.json'
                self.run_checked([sys.executable, '-c', API_CHECK, str(root), str(parser), str(receipt), 'seed'], env)
                prepared = transfer.prepare_project(root, base / 'portable-package')
                self.assertTrue(prepared['verified'])
                transfer._remove_runtime(root)
                shutil.rmtree(root)
                runtimes.remove(root)
                received = transfer.restore_project(prepared['directory'], restored)
                runtimes.append(restored)
                self.assertTrue(received['verified'])
                self.run_checked([sys.executable, '-c', API_CHECK, str(restored), str(parser), str(receipt), 'check'], env)
            finally:
                for runtime in runtimes:
                    transfer._remove_runtime(runtime)

    def run_checked(self, command, env):
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=240)
        self.assertEqual(result.returncode, 0, result.stdout[-8000:] + result.stderr[-8000:])


if __name__ == '__main__':
    unittest.main()
