#!/usr/bin/env python3
"""Broad native scientific/failure E2E against an exact packaged runtime.

Only creates isolated scratch projects. Public receipts omit recordings, project
paths, capabilities and credentials. Signed updates are a separate release gate.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socketserver
import http.server
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

from desktop_backend_smoke import inventory

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Harness:
    def __init__(self, resources, state=None):
        self.resources = Path(resources).resolve(strict=True)
        self.runtime = self.resources / 'runtime'
        self.manifest = json.loads((self.runtime / 'runtime-manifest.json').read_text())
        self.state = Path(state or tempfile.mkdtemp(prefix='rieke-scientific-e2e-')).resolve()
        self.state.mkdir(exist_ok=True)
        (self.state / 'home').mkdir(exist_ok=True)
        self.capability = secrets.token_hex(32)
        self.session_id = str(uuid.uuid4())
        self.env = {'HOME': str(self.state / 'home'), 'PATH': '/usr/bin:/bin', 'LANG': 'en_US.UTF-8',
                    'TMPDIR': os.environ.get('TMPDIR', '/tmp'), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
                    'RIEKE_DESKTOP_CAPABILITY': self.capability, 'RECORDING_WORKSPACE_ROOT': str(self.state / 'projects')}
        self.python = self.runtime / 'python/bin/python3.11'
        self.process = None
        self.known_projects = set()
        self.cases = []
        self.failures = []

    def python_code(self, code, *arguments, timeout=180):
        environment = dict(self.env)
        executable = self.python
        application = self.runtime / 'application'
        environment.update(RIEKE_DESKTOP_MODE='1', RIEKE_DESKTOP_RUNTIME=str(self.runtime),
            RIEKE_DESKTOP_USER_STATE=str(self.state / 'user-state'),
            RIEKE_PARSER_CONFIG=str(self.state / 'user-state/parser/config.ini'))
        command = [str(executable), '-B', '-c',
                   "import sys; sys.path.insert(0, sys.argv[1]); " + code,
                   str(application / 'python'), *map(str, arguments)]
        result = subprocess.run(command, cwd=self.state, env=environment,
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            (self.state / 'helper-failure.log').write_text(result.stdout + result.stderr)
            raise RuntimeError('Bundled helper failed; private diagnostic retained')
        markers = [line for line in result.stdout.splitlines() if line.startswith('E2E=')]
        return json.loads(markers[-1][4:]) if markers else None

    def start(self, timeout=180):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.log = (self.state / 'backend.log').open('ab')
        command = [str(self.python), '-B', str(self.runtime / 'application/python/workspace_desktop.py'),
                   '--resources', str(self.resources), '--manifest', str(self.runtime / 'runtime-manifest.json'),
                   '--user-state', str(self.state / 'user-state'), '--session-id', self.session_id, '--port', str(self.port)]
        self.process = subprocess.Popen(command, cwd=self.state, env=self.env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=self.log)
        packet, bound = {}, threading.Event()
        def reader():
            for line in iter(self.process.stdout.readline, b''):
                self.log.write(line)
                self.log.flush()
                if line.startswith(b'RIEKE_DESKTOP_BOUND='):
                    packet.update(json.loads(line.split(b'=', 1)[1]))
                    bound.set()
                    break
        threading.Thread(target=reader, daemon=True).start()
        expected = {'pid': self.process.pid, 'session_id': self.session_id, 'port': self.port,
                    'application_version': self.manifest['application_version'], 'source_commit': self.manifest['source_commit'],
                    'workspace_formats': self.manifest['workspace_formats'], 'database_compatibility': self.manifest['database_compatibility']}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Packaged root exited before private bind receipt')
            if not bound.wait(.2):
                continue
            if any(packet.get(key) != value for key, value in expected.items()):
                raise RuntimeError('Private bind receipt identity mismatch')
            try:
                health = self.call('/api/desktop/health')
                if not health.get('ready') or any(health.get(key) != value for key, value in expected.items() if key != 'port'):
                    raise RuntimeError('Root health identity mismatch')
                return health
            except OSError:
                time.sleep(.1)
        raise RuntimeError('Packaged root readiness timeout')

    def call(self, route, body=None, *, origin=None, timeout=30, headers=None, raw=False, expect=None):
        request_headers = {'X-Rieke-Desktop-Capability': self.capability, 'X-Workspace-Request': '1', 'Content-Type': 'application/json'}
        request_headers.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        try:
            with urlopen(Request((origin or self.origin) + route, data=data, headers=request_headers), timeout=timeout) as response:
                value = response.read()
                if expect and response.status != expect:
                    raise AssertionError('Expected failure status was accepted')
                return value if raw else json.loads(value)
        except HTTPError as error:
            value = error.read()
            if expect == error.code:
                return json.loads(value) if value.startswith(b'{') else {'status': error.code}
            (self.state / 'http-failure.log').write_bytes(value)
            raise

    def create(self, name):
        directory = self.state / name
        project = self.call('/api/projects', {'name': name, 'project_directory': str(directory)})['project']
        self.known_projects.add(directory)
        return project

    def open(self, project):
        opened = self.call('/api/projects/open-folder', {'directory': project['path']}, timeout=180)
        origin = opened['url'].rstrip('/')
        authorization = self.call('/api/desktop/authorize-project', {'port': urlsplit(origin).port})
        if (authorization['health']['project_uuid'] != project['uuid']
                or authorization['health']['project_path'] != str(Path(project['path']).resolve())
                or authorization['record'].get('bound') is not True):
            raise AssertionError('Project listener identity changed')
        return origin, authorization['record']

    def close_project(self, origin, project):
        self.call('/api/project/close', {}, origin=origin, timeout=45)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            records = self.call('/api/desktop/health')['services']
            if not any(record['project_path'] == project['path'] for record in records):
                owner = json.loads((Path(project['path']) / 'database/native-owner.json').read_text())
                assert owner['clean_shutdown'] is True
                return
            time.sleep(.2)
        raise AssertionError('Project service did not exit')

    def import_recording(self, origin, source, *, expected='complete', check_busy=False):
        job = self.call('/api/imports', {'source_path': str(source)}, origin=origin)
        if check_busy:
            self.call('/api/desktop/drain', {}, expect=409, timeout=65)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            current = next(item for item in self.call('/api/jobs', origin=origin)['jobs'] if item['job_uuid'] == job['job_uuid'])
            if current['status'] in ('complete', 'complete_with_warnings', 'duplicate', 'failed', 'interrupted'):
                if expected == 'complete' and current['status'] not in ('complete', 'complete_with_warnings'):
                    raise AssertionError('Recording import failed')
                if expected != 'complete' and current['status'] != expected:
                    raise AssertionError('Unexpected terminal import state')
                return current
            time.sleep(.3)
        raise TimeoutError('Import completion deadline exceeded')

    def export(self, origin, protocol_uuid, export_format, *, epoch=None):
        revision = self.call('/api/protocols/' + protocol_uuid, origin=origin)['query_revision']
        body = {'format': export_format, 'name': 'Isolated E2E export', 'query_revision': revision}
        if epoch:
            body['filters'] = {'epoch_uuid': epoch}
        return self.call('/api/protocols/' + protocol_uuid + '/exports', body, origin=origin, timeout=120)

    def check(self, name, function):
        started = time.monotonic()
        try:
            evidence = function()
            self.cases.append({'name': name, 'passed': True, 'seconds': round(time.monotonic() - started, 3),
                               **({'evidence': evidence} if evidence else {})})
            print('PASS', name, flush=True)
            return evidence
        except Exception as error:
            self.cases.append({'name': name, 'passed': False, 'seconds': round(time.monotonic() - started, 3),
                               'error_type': type(error).__name__})
            self.failures.append({'case': name, 'error': repr(error)})
            (self.state / 'failures-private.json').write_text(json.dumps(self.failures, indent=2))
            print('FAIL', name, type(error).__name__, flush=True)
            return None

    def cleanup_database(self, project, *, source=False):
        self.python_code("from workspace_native_mysql import stop_native_database; import json; "
                         "stop_native_database(sys.argv[2]); print('E2E='+json.dumps({'stopped':True}))", project, source=source)

    def stop(self):
        if not self.process or self.process.poll() is not None:
            return
        result = self.call('/api/desktop/drain', {}, timeout=90)
        assert result['ready'] is True
        self.call('/api/desktop/stop', {})
        self.process.wait(timeout=35)
        assert self.process.returncode == 0
        self.log.close()


TRACE_CHECK = r'''
import json, h5py, numpy as np, sqlite3, scipy.io, zipfile, io
from workspace_sqlite import load_frozen_record
spec=json.loads(open(sys.argv[2]).read())
def raw(source,pointer,start,count):
    with h5py.File(source,'r') as h5:
        return h5[pointer.rstrip('/')+'/data'][start:start+count]['quantity'].astype(float)
api=np.array(spec['api']['values'],dtype=float)
expected=raw(spec['reference']['source_reference']['path'],spec['stream']['h5_path'],spec['api']['start'],spec['api']['count'])
assert np.array_equal(api,expected), 'HTTP trace samples changed'
assert spec['api']['sample_rate']==spec['stream']['sample_rate']
assert spec['api']['units']==spec['stream']['units']
with sqlite3.connect('file:'+sys.argv[3]+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert db.execute('SELECT epoch_uuid FROM epochs').fetchall()==[(spec['reference']['epoch_uuid'],)]
    frozen=load_frozen_record(db,spec['reference']['epoch_uuid'])
    pointer=db.execute("SELECT s.source_path,st.h5_path,st.sample_rate,st.units FROM streams st JOIN epochs e USING(epoch_uuid) JOIN sources s USING(source_sha256) WHERE st.stream_uuid=?",(spec['stream']['uuid'],)).fetchone()
    assert np.array_equal(raw(pointer[0],pointer[1],spec['api']['start'],spec['api']['count']),expected)
    assert pointer[2:]==(spec['stream']['sample_rate'],spec['stream']['units'])
    assert frozen['parameters']==spec['reference']['parameters']
mat_checked=False
if len(sys.argv)>4:
    with zipfile.ZipFile(sys.argv[4]) as archive:
        mat=scipy.io.loadmat(io.BytesIO(archive.read('recordings.mat')),simplify_cells=True)
    found=[]
    def walk(obj):
        if isinstance(obj,dict):
            if obj.get('h5_uuid')==spec['reference']['epoch_uuid'] and 'responses' in obj:
                found.append(obj)
            for value in obj.values():walk(value)
        elif isinstance(obj,(list,tuple,np.ndarray)):
            for value in np.asarray(obj,dtype=object).reshape(-1):walk(value)
    walk(mat)
    assert len(found)==1, 'MAT epoch membership changed'
    responses=found[0]['responses'];responses=[responses] if isinstance(responses,dict) else list(responses)
    stream=next(item for item in responses if item['h5_uuid']==spec['stream']['uuid'])
    assert np.array_equal(raw(stream['h5_file'],stream['h5_path'],spec['api']['start'],spec['api']['count']),expected)
    assert stream['sample_rate']==spec['stream']['sample_rate'] and stream['units']==spec['stream']['units']
    assert json.loads(found[0]['source_metadata_json'])['parameters']==spec['reference']['parameters']
    mat_checked=True
print('E2E='+json.dumps({'sample_count':len(expected),'exact_numeric_match':True,'sqlite_integrity':True,'mat_lazy_trace_match':mat_checked}))
'''


def exercise(h, recording):
    project = h.create('primary-science')
    origin, record = h.open(project)
    baseline = h.import_recording(origin, recording, check_busy=True)
    overview = h.call('/api/overview', origin=origin)
    counts = {key: overview['counts'][key] for key in ('sources', 'cells', 'epochs', 'protocols')}
    h.cases.append({'name': 'real-import-and-active-writer-drain-deferral', 'passed': True, 'evidence': counts})
    protocol_uuid = overview['protocols'][0]['protocol_uuid']
    page = h.call('/api/protocols/' + protocol_uuid + '/epochs?limit=3', origin=origin)
    first, second = page['epochs'][:2]
    epoch_uuid = first['epoch_uuid']
    source_hash = sha(recording)
    artifacts = {}

    def duplicate():
        same = h.import_recording(origin, recording, expected='duplicate')
        renamed = h.state / 'renamed-recording.h5'
        shutil.copy2(recording, renamed)
        moved = h.import_recording(origin, renamed, expected='duplicate')
        after = h.call('/api/overview', origin=origin)
        assert {key: after['counts'][key] for key in counts} == counts
        assert same['catalog_committed'] is False and moved['catalog_committed'] is False
        return {'same_bytes_and_renamed_bytes_do_not_duplicate_catalog': True}
    h.check('dedup-original-and-renamed-H5', duplicate)

    def failed_import():
        damaged = h.state / 'truncated-input.h5'
        with recording.open('rb') as source:
            damaged.write_bytes(source.read(1024))
        job = h.import_recording(origin, damaged, expected='failed')
        after = h.call('/api/overview', origin=origin)
        assert {key: after['counts'][key] for key in counts} == counts
        assert job['catalog_committed'] is False
        return {'failed_parse_did_not_commit_catalog': True, 'previous_catalog_preserved': True}
    h.check('truncated-import-preserves-catalog-and-releases-writer', failed_import)

    def annotations():
        profile = h.call('/api/annotation-profiles', {'display_name': 'Isolated scientific E2E'}, origin=origin)
        h.call('/api/annotation-profiles/selected', {'profile_uuid': profile['profile_uuid']}, origin=origin)
        h.call('/api/annotations', {'target_kind': 'epoch', 'target_uuids': [epoch_uuid],
            'profile_uuid': profile['profile_uuid'], 'tags_add': ['e2e-epoch'], 'expected_revisions': {epoch_uuid: 0}}, origin=origin)
        h.call('/api/annotations', {'target_kind': 'cell', 'target_uuids': [first['cell_uuid']],
            'profile_uuid': profile['profile_uuid'], 'tags_add': ['e2e-cell'], 'expected_revisions': {first['cell_uuid']: 0}}, origin=origin)
        one = h.call('/api/explore/run', {'predicate': {'field': 'annotations/epoch/tags', 'operator': 'contains', 'value': 'e2e-epoch'},
            'splits': 'date,protocol,cell'}, origin=origin)
        inherited = h.call('/api/explore/run', {'predicate': {'field': 'annotations/effective/tags', 'operator': 'contains', 'value': 'e2e-cell'},
            'splits': 'date,protocol,cell'}, origin=origin)
        expected_cell = next(cell['epochs'] for cell in overview['cells'] if cell['cell_uuid'] == first['cell_uuid'])
        assert one['matched_count'] == 1 and inherited['matched_count'] == expected_cell
        h.call('/api/annotations', {'target_kind': 'epoch', 'target_uuids': [epoch_uuid],
            'profile_uuid': profile['profile_uuid'], 'tags_add': ['stale-must-not-commit'], 'expected_revisions': {epoch_uuid: 0}}, origin=origin, expect=409)
        return {'direct_tag_query_matches': 1, 'inherited_cell_tag_matches': expected_cell, 'stale_revision_rejected': True}
    h.check('annotation-attribution-inheritance-and-query-semantics', annotations)

    def current_backend_contracts():
        fields = h.call('/api/metadata/fields', origin=origin)['fields']
        assert fields and len({field['id'] for field in fields}) == len(fields)
        assert all('values' not in field and 'value' not in field for field in fields)
        h.call('/api/metadata/fields?cell_uuid=unregistered', origin=origin, expect=400)
        ordinary = h.call('/api/protocols/' + protocol_uuid + '/epochs?limit=3', origin=origin)
        combined = h.call('/api/protocols/' + protocol_uuid + '/epochs?limit=3&include_cells=true', origin=origin)
        assert 'cells' not in ordinary
        assert combined['epochs'] == ordinary['epochs'] and combined['total'] == ordinary['total']
        assert sum(cell['epochs'] for cell in combined['cells']) == combined['total']
        assert {row['cell_uuid'] for row in combined['epochs']} <= {cell['cell_uuid'] for cell in combined['cells']}
        h.call('/api/protocols/' + protocol_uuid + '/epochs?include_cells=1', origin=origin, expect=400)
        metadata = h.call('/api/metadata/status', origin=origin)
        preparation = metadata['annotation_preparation']
        assert metadata['status'] == 'ready' and preparation['status'] == 'ready', 'Native annotation preparation failed'
        assert preparation['storage'] == 'native_sql'
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            backup = h.call('/api/backup/status', origin=origin)
            if backup['status'] == 'current' and backup['last_success'] and backup['completed_sequence'] > 0:
                break
            assert backup['status'] != 'degraded', 'Committed annotation backup failed'
            time.sleep(.2)
        else:
            raise TimeoutError('Committed annotation backup did not become current')
        health = h.call('/api/health', origin=origin)
        assert health['backup']['status'] == 'current' and health['project_uuid'] == project['uuid']
        events = h.call('/api/events?limit=1', origin=origin)
        assert events['events'] and all('payload' not in event for event in events['events'])
        detail = h.call('/api/events/' + events['events'][0]['event_uuid'], origin=origin)
        assert 'payload' in detail['event']
        return {'registered_metadata_field_count': len(fields), 'combined_epoch_cell_membership_matches': True,
                'native_annotation_preparation_ready': True, 'committed_backup_current': True,
                'event_summary_and_detail_contract': True}
    h.check('current-metadata-fields-combined-cells-annotation-preparation-and-backup-APIs', current_backend_contracts)

    def inclusion():
        current = h.call('/api/protocols/' + protocol_uuid + '/epochs?limit=3', origin=origin)
        excluded = next(item for item in current['epochs'] if item['epoch_uuid'] == second['epoch_uuid'])
        h.call('/api/protocols/' + protocol_uuid + '/curation', {'epoch_uuids': [excluded['epoch_uuid']],
            'query_revision': current['query_revision'], 'expected_revisions': {excluded['epoch_uuid']: excluded['curation']['revision']},
            'changes': {'included': False}}, origin=origin)
        protocol = h.call('/api/protocols/' + protocol_uuid, origin=origin)
        h.call('/api/protocols/' + protocol_uuid + '/exports', {'format': 'reference-json',
            'query_revision': protocol['query_revision'], 'filters': {'epoch_uuid': excluded['epoch_uuid']}}, origin=origin, expect=400)
        artifacts['membership-reference'] = h.export(origin, protocol_uuid, 'reference-json')
        package = json.loads(Path(artifacts['membership-reference']['artifact_path']).read_text())
        ids = {item['epoch_uuid'] for item in package['epochs']}
        assert epoch_uuid in ids and excluded['epoch_uuid'] not in ids
        assert len(ids) == protocol['counts']['included']
        return {'excluded_epoch_not_exported': True, 'included_export_count': len(ids)}
    h.check('inclusion-mask-export-membership-and-stale-protection', inclusion)

    def export(format):
        artifacts[format] = h.export(origin, protocol_uuid, format, epoch=epoch_uuid)
        downloaded = h.call(artifacts[format]['download_url'], origin=origin, raw=True)
        assert hashlib.sha256(downloaded).hexdigest() == artifacts[format]['artifact_sha256']
        return {'download_matches_published_hash': True}
    h.check('reference-export-real-artifact-download', lambda: export('reference-json'))
    h.check('SQLite-export-real-artifact-download', lambda: export('wheeler-sqlite'))
    h.check('MAT-export-real-artifact-download', lambda: export('epictree-mat'))

    def trace():
        package = json.loads(Path(artifacts['reference-json']['artifact_path']).read_text())
        row = package['epochs'][0]
        stream = next(item for item in row['streams'] if item['kind'] == 'responses' and item['sample_count'] > 50)
        api = h.call('/api/epochs/' + epoch_uuid + '/trace?stream_uuid=' + stream['uuid'] + '&start=17&count=127', origin=origin)
        spec = h.state / 'trace-private.json'
        spec.write_text(json.dumps({'reference': row, 'stream': stream, 'api': api}))
        arguments = [spec, artifacts['wheeler-sqlite']['artifact_path']]
        if 'epictree-mat' in artifacts:
            arguments.append(artifacts['epictree-mat']['artifact_path'])
        return h.python_code(TRACE_CHECK, *arguments)
    h.check('numeric-trace-fidelity-HTTP-and-frozen-export-pointers', trace)

    def multiservice():
        second_project = h.create('second-project')
        second_origin, second_record = h.open(second_project)
        records = h.call('/api/desktop/health')['services']
        assert len(records) == 2 and len({item['pid'] for item in records}) == 2
        assert h.call('/api/overview', origin=second_origin)['counts']['epochs'] == 0
        assert h.call('/api/overview', origin=origin)['counts']['epochs'] == counts['epochs']
        h.close_project(second_origin, second_project)
        return {'isolated_processes': 2, 'scientific_catalog_not_shared': True}
    h.check('simultaneous-project-services-are-owned-and-isolated', multiservice)

    h.close_project(origin, project)
    origin, record = h.open(project)
    def reopen():
        annotations = h.call('/api/annotations/read', {'target_kind': 'epoch', 'target_uuids': [epoch_uuid]}, origin=origin)
        assert 'e2e-epoch' in [item['tag'] for item in annotations['targets'][epoch_uuid]['tags']]
        current = h.call('/api/protocols/' + protocol_uuid + '/epochs?limit=3', origin=origin)
        assert next(item for item in current['epochs'] if item['epoch_uuid'] == second['epoch_uuid'])['curation']['included'] is False
        for artifact in artifacts.values():
            assert sha(artifact['artifact_path']) == artifact['artifact_sha256']
        assert sha(recording) == source_hash
        return {'annotations_mask_exports_and_original_checksum_preserved': True}
    h.check('project-restart-preserves-scientific-state-and-original', reopen)
    h.close_project(origin, project)

    def portability():
        target = h.state / 'portable-package'
        submitted = h.call('/api/projects/prepare-transfer', {'directory': project['path'], 'destination': str(target)})
        h.call('/api/desktop/drain', {}, expect=409, timeout=65)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            job = h.call('/api/projects/transfers/' + submitted['job_id'])
            if job['state'] != 'running':
                assert job['state'] == 'complete', 'Portable preparation failed'
                break
            time.sleep(.3)
        else:
            raise TimeoutError('Portable preparation did not finish')
        owner = json.loads((Path(project['path']) / 'database/native-owner.json').read_text())
        if owner.get('clean_shutdown') is not True:
            # This is a safety failure, even if the package itself is valid.
            h.cases.append({'name': 'transfer-owned-MySQL-closes-before-job-ack', 'passed': False,
                            'error_type': 'UnregisteredRunningDatabase'})
            h.failures.append({'case': 'transfer-owned-MySQL-closes-before-job-ack', 'error': 'Transfer completed with native database still alive'})
            h.cleanup_database(project['path'])
        restored_path = h.state / 'portable-recipient'
        submitted = h.call('/api/projects/restore-transfer', {'directory': str(target), 'destination': str(restored_path)})
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            job = h.call('/api/projects/transfers/' + submitted['job_id'])
            if job['state'] != 'running':
                assert job['state'] == 'complete', 'Portable restore failed'
                break
            time.sleep(.3)
        else:
            raise TimeoutError('Portable restore did not finish')
        restored_owner = json.loads((restored_path / 'database/native-owner.json').read_text())
        assert restored_owner.get('clean_shutdown') is True, 'Restore database was not closed before job acknowledgement'
        h.known_projects.add(restored_path)
        restored_project = {'path': str(restored_path), 'uuid': project['uuid']}
        restored_origin, restored_record = h.open(restored_project)
        restored = h.call('/api/overview', origin=restored_origin)
        assert {key: restored['counts'][key] for key in counts} == counts
        tags = h.call('/api/annotations/read', {'target_kind': 'epoch', 'target_uuids': [epoch_uuid]}, origin=restored_origin)
        assert 'e2e-epoch' in [item['tag'] for item in tags['targets'][epoch_uuid]['tags']]
        exported = h.call('/api/exports', origin=restored_origin)['exports']
        assert len(exported) == len(artifacts)
        assert all(Path(item['artifact_path']).is_relative_to(restored_path) for item in exported)
        h.close_project(restored_origin, restored_project)
        return {'restored_counts_equal': True, 'annotations_and_exports_rebased': True, 'real_logical_backup_restore_verified': True}
    h.check('portable-prepare-restore-saved-state-source-pointers-and-exports', portability)
    return project, counts


def legacy_copy(h, donor, counts):
    """Real source SQL/data, fake read-only Docker inspect transport only."""
    source = h.state / 'legacy-source'
    subprocess.run(['/bin/cp', '-cR', donor['path'], str(source)], check=True)
    native_catalog = json.loads((source / 'catalog.json').read_text())
    source_settings = h.python_code("from workspace_project_database import ensure_project_database; "
        "from workspace_portability import rebase_project_paths,_database_inventory; "
        "from workspace_native_mysql import connection_parameters; import pymysql,json; "
        "ensure_project_database(sys.argv[2]); rebase_project_paths(sys.argv[2]); "
        "settings=connection_parameters(sys.argv[2]); connection=pymysql.connect(**settings,autocommit=True); "
        "cursor=connection.cursor(); cursor.execute('SELECT @@hostname'); hostname=cursor.fetchone()[0]; "
        "inventory=_database_inventory(connection); cursor.execute('SELECT COUNT(*) FROM recording_workspace.event'); history=cursor.fetchone()[0]; "
        "connection.close(); print('E2E='+json.dumps({'settings':settings,'hostname':hostname,'inventory':inventory,'history':history}))", source)
    native_catalog = json.loads((source / 'catalog.json').read_text())
    legacy = {**native_catalog, 'connection': {'host': '127.0.0.1', 'port': source_settings['settings']['port'],
              'credential_provider': {'kind': 'docker-container-env', 'container': 'isolated-source-fixture'}}}
    legacy.pop('managed_database', None)
    (source / 'catalog.json').write_text(json.dumps(legacy))
    scientific_before = inventory(source)
    # Exclude a live server's operational files: the source's scientific SQL is
    # compared separately by complete logical inventory below.
    scientific_before = {key:value for key,value in scientific_before.items() if not key.startswith('database/')}
    # AF_UNIX has a short path limit on macOS. Keep the test transport in a
    # short owned directory; the production resolver follows the user's normal
    # ~/.docker/run location and verifies the resulting socket's ownership.
    socket_directory = Path(tempfile.mkdtemp(prefix='rieke-inspect-', dir='/tmp'))
    docker_home = h.state / 'home/.docker'
    docker_home.mkdir(parents=True, exist_ok=True)
    (docker_home / 'run').symlink_to(socket_directory, target_is_directory=True)
    socket_path = socket_directory / 'docker.sock'
    requests = []
    inspect = {'Id': 'isolated-source-fixture-identity', 'State': {'Running': True},
               'Config': {'Hostname': source_settings['hostname'],
                          'Env': ['MYSQL_ROOT_PASSWORD=' + source_settings['settings']['password']]},
               'NetworkSettings': {'Ports': {'3306/tcp': [{'HostIp': '127.0.0.1',
                                           'HostPort': str(source_settings['settings']['port'])}]}}}
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command,self.path))
            assert self.path == '/containers/isolated-source-fixture/json'
            body=json.dumps(inspect).encode(); self.send_response(200); self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    class Server(socketserver.UnixStreamServer):pass
    server=Server(str(socket_path),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    target = h.state / 'migrated-desktop-copy'
    try:
        preview = h.call('/api/projects/inspect-folder', {'directory': str(source)})
        assert preview['desktop_compatibility']['requires_migration'] is True
        before_services = h.call('/api/desktop/health')['services']
        rejection = h.call('/api/projects/open-folder', {'directory': str(source)}, expect=409)
        assert rejection['code'] == 'legacy_project_requires_migration'
        assert h.call('/api/desktop/health')['services'] == before_services
        # Existing source lease is observed; no forced close or source mutation.
        import fcntl
        with (source / '.app-state-session.lock').open('r') as lease:
            fcntl.flock(lease.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            submitted = h.call('/api/projects/migrate-source', {'directory': str(source), 'destination': str(target)})
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                job=h.call('/api/projects/transfers/'+submitted['job_id'])
                if job['state']!='running':break
                time.sleep(.1)
            assert job['state']=='failed' and not target.exists(), 'Active source lease did not defer migration'
        submitted = h.call('/api/projects/migrate-source', {'directory': str(source), 'destination': str(target)})
        h.call('/api/desktop/drain', {}, expect=409, timeout=65)
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            job=h.call('/api/projects/transfers/'+submitted['job_id'])
            if job['state']!='running':break
            time.sleep(.3)
        assert job['state']=='complete', 'Full source migration failed'
        assert job['result']['source_unchanged'] and job['result']['migrated'] and job['result']['verified']
        assert all(method=='GET' for method,path in requests), 'Migration used a mutating Docker API'
        assert {key:value for key,value in inventory(source).items() if not key.startswith('database/')} == scientific_before
        direct = h.python_code("import pymysql,json; from workspace_portability import _database_inventory; "
            "settings=json.loads(open(sys.argv[3]).read()); connection=pymysql.connect(**settings,autocommit=True); "
            "value=_database_inventory(connection); connection.close(); print('E2E='+json.dumps(value))", source,
            _write_private_json(h.state / 'source-connection-private.json', source_settings['settings']))
        assert direct == source_settings['inventory'], 'Original source SQL changed during migration'
        migrated = {'path':str(target),'uuid':donor['uuid']};h.known_projects.add(target)
        origin,record=h.open(migrated)
        overview=h.call('/api/overview',origin=origin)
        assert {key:overview['counts'][key] for key in counts}==counts
        exports=h.call('/api/exports',origin=origin)['exports']
        assert exports and all(Path(item['artifact_path']).is_relative_to(target) for item in exports)
        assert all(sha(item['artifact_path'])==item['artifact_sha256'] for item in exports)
        history=h.python_code("from workspace_native_mysql import connection_parameters; import pymysql,json; "
            "connection=pymysql.connect(**connection_parameters(sys.argv[2]),autocommit=True);cursor=connection.cursor(); "
            "cursor.execute('SELECT COUNT(*) FROM recording_workspace.event'); value=cursor.fetchone()[0];connection.close(); "
            "print('E2E='+json.dumps(value))",target)
        assert history>=source_settings['history']>0, 'Source SQL-only history was lost'
        protocols={item['protocol_uuid'] for item in overview['protocols']}
        assert len(protocols)==counts['protocols']
        # Historical exported bytes keep their sealed hashes. Active source
        # manifests and a new export must resolve exclusively to the copy.
        protocol = overview['protocols'][0]['protocol_uuid']
        page = h.call('/api/protocols/'+protocol+'/epochs?limit=3',origin=origin)
        epoch = next(item for item in page['epochs'] if item['curation']['included'])['epoch_uuid']
        fresh = h.export(origin,protocol,'reference-json',epoch=epoch)
        reference = json.loads(Path(fresh['artifact_path']).read_text())['epochs'][0]
        assert Path(reference['source_reference']['path']).is_relative_to(target)
        stream = next(item for item in reference['streams'] if item['kind']=='responses' and item['sample_count']>50)
        api = h.call('/api/epochs/'+epoch+'/trace?stream_uuid='+stream['uuid']+'&start=17&count=127',origin=origin)
        private_spec = _write_private_json(h.state/'migration-trace-private.json',{'reference':reference,'stream':stream,'api':api})
        numeric = h.python_code("import json,h5py,numpy as np; spec=json.load(open(sys.argv[2])); "
            "source=spec['reference']['source_reference']['path']; pointer=spec['stream']['h5_path']; "
            "h5=h5py.File(source,'r'); values=h5[pointer.rstrip('/')+'/data'][17:144]['quantity']; "
            "assert np.array_equal(np.asarray(spec['api']['values']),values); h5.close(); "
            "print('E2E='+json.dumps({'matched_samples':len(values)}))",private_spec)
        assert numeric['matched_samples']==127
        h.close_project(origin,migrated)
        return {'legacy_preflight_does_not_spawn_failed_service':True,'active_source_lease_defers_copy':True,
                'source_files_and_full_SQL_unchanged':True,'read_only_Docker_inspect_only':True,
                'scientific_counts_preserved':counts,'history_records_preserved':source_settings['history'],
                'export_artifacts_rebased_and_verified':len(exports),
                'new_export_resolves_copy_with_127_exact_trace_samples':True}
    finally:
        server.shutdown();server.server_close();socket_path.unlink(missing_ok=True)
        (docker_home / 'run').unlink();socket_directory.rmdir()
        # Restore our test fixture's native descriptor only after proving the
        # migration itself made no source mutation, then close its owned server.
        (source/'catalog.json').write_text(json.dumps(native_catalog))
        h.cleanup_database(source)


def _write_private_json(path,value):
    path.write_text(json.dumps(value));path.chmod(0o600);return path


def fault_recovery(h, recording):
    """Crash our import monitor only; the scientific child finishes untouched."""
    project = h.create('interrupted-monitor-fixture')
    origin, record = h.open(project)
    submitted = h.call('/api/imports', {'source_path': str(recording)}, origin=origin)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        job = next(item for item in h.call('/api/jobs', origin=origin)['jobs']
                   if item['job_uuid'] == submitted['job_uuid'])
        progress = job.get('progress') or {}
        worker_pid = progress.get('pid')
        if type(worker_pid) is int and worker_pid != record['pid'] and progress.get('stage') not in {'complete', 'failed', 'duplicate'}:
            break
        time.sleep(.1)
    else:
        raise AssertionError('No active scientific child was observed')
    # Verify the complete command belongs to this fixture before injecting the
    # monitor fault. Never signal the MySQL or importer processes.
    import fcntl
    ownership = _write_private_json(h.state/'fault-ownership-private.json',
                                  {'record':record,'worker_pid':worker_pid,'path':project['path']})
    worker_created = h.python_code("import json,psutil,signal,os; from pathlib import Path; "
        "spec=json.load(open(sys.argv[2])); record=spec['record']; monitor=psutil.Process(record['pid']); "
        "assert monitor.create_time()==record['created_at']; assert str(Path(monitor.exe()).resolve())==record['executable']; "
        "assert spec['path'] in monitor.cmdline(); worker=psutil.Process(spec['worker_pid']); "
        "created=worker.create_time(); os.kill(record['pid'],signal.SIGTERM); print('E2E='+json.dumps(created))",ownership)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if any(item.get('recovery_required') for item in h.call('/api/desktop/health')['services']
               if item['project_uuid'] == project['uuid']):
            break
        time.sleep(.1)
    rejected = h.call('/api/desktop/authorize-project', {'port': record['port']}, expect=409)
    assert rejected.get('error')
    h.call('/api/desktop/drain', {}, expect=409, timeout=65)
    lease_path = Path(project['path']) / '.app-state-session.lock'
    with lease_path.open('r') as lease:
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise AssertionError('Importer lost its inherited session lease after monitor crash')
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        alive = h.python_code("import json,psutil\ntry:\n"
            " current=psutil.Process(int(sys.argv[2])); alive=current.create_time()==float(sys.argv[3]) and current.status()!=psutil.STATUS_ZOMBIE\n"
            "except psutil.NoSuchProcess: alive=False\nprint('E2E='+json.dumps(alive))",worker_pid,worker_created)
        if not alive:
            break
        time.sleep(.2)
    else:
        raise AssertionError('Scientific child remains active; preserve fixture for recovery')
    with lease_path.open('r') as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    h.cleanup_database(project['path'])
    assert not any(item['project_uuid'] == project['uuid'] for item in h.call('/api/desktop/health')['services'])
    reopened, new_record = h.open(project)
    assert new_record['pid'] != record['pid']
    jobs = h.call('/api/jobs', origin=reopened)['jobs']
    interrupted = next(item for item in jobs if item['job_uuid'] == submitted['job_uuid'])
    assert interrupted['status'] == 'interrupted'
    overview = h.call('/api/overview', origin=reopened)
    assert overview['counts']['sources'] == 1 and overview['counts']['epochs'] == 1915
    h.close_project(reopened, project)
    return {'crashed_monitor_never_authorizes_reused_port': True,
            'active_importer_preserves_exclusive_session_lease': True,
            'importer_finishes_without_signal_or_force_kill': True,
            'interrupted_job_retained_and_committed_catalog_recovered': True,
            'explicit_owned_MySQL_shutdown_allows_clean_project_reopen': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, default=ROOT / 'desktop/dist/mac-arm64/Rieke OS.app/Contents/Resources')
    parser.add_argument('--recording', type=Path, default=ROOT / 'test_data/h5/2025-12-02_F.h5')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/dev/desktop-scientific-e2e.json')
    parser.add_argument('--state', type=Path)
    args = parser.parse_args()
    recording = args.recording.resolve(strict=True)
    original = sha(recording)
    h = Harness(args.resources, args.state)
    before = inventory(h.runtime)
    try:
        h.start()
        project, counts = exercise(h, recording)
        h.check('full-legacy-source-copy-identity-history-and-scientific-state', lambda: legacy_copy(h, project, counts))
        h.check('interrupted-import-monitor-lease-and-owned-service-recovery', lambda: fault_recovery(h, recording))
    except Exception as error:
        h.failures.append({'case': 'suite-setup-or-termination', 'error': repr(error)})
        h.cases.append({'name': 'suite-setup-or-termination', 'passed': False, 'error_type': type(error).__name__})
        (h.state / 'failures-private.json').write_text(json.dumps(h.failures, indent=2))
    finally:
        try:
            h.stop()
            h.cases.append({'name': 'all-owned-WSGI-project-and-root-services-drain-exit', 'passed': True})
        except Exception as error:
            h.cases.append({'name': 'all-owned-WSGI-project-and-root-services-drain-exit', 'passed': False, 'error_type': type(error).__name__})
        after = inventory(h.runtime)
        unchanged = before == after
        source_unchanged = original == sha(recording)
        receipt = {'format': 'rieke-desktop-scientific-e2e', 'version': 1, 'production_ready': False,
            'runtime_manifest_sha256': sha(h.runtime / 'runtime-manifest.json'), 'runtime_resource_count': len(h.manifest['resources']),
            'app_asar_sha256': sha(h.resources / 'app.asar'),
            'runtime_identity': {key: h.manifest[key] for key in ('application_version', 'source_commit', 'parser_commit', 'platform', 'architecture', 'python_version', 'mysql_version')},
            'cases': h.cases, 'packaged_resources_unchanged': unchanged, 'original_recording_unchanged': source_unchanged,
            'limitations': ['Unsigned developer machine; no signed update or clean-machine certification',
                            'MATLAB runtime execution is not available; MAT structure and numeric lazy H5 pointers are checked with bundled scipy',
                            'Legacy migration uses an isolated read-only Docker inspect transport with real MySQL SQL/H5 data; no live Docker daemon or user source database is used'],
            'passed': all(case['passed'] for case in h.cases) and unchanged and source_unchanged}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))
        print('Private diagnostics retained:', h.state)
    raise SystemExit(0 if receipt['passed'] else 1)


if __name__ == '__main__':
    main()
