"""Duplicate import jobs use disposable files and SQL doubles only."""
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

if __package__:
    from . import test_workspace_api as api_tests
else:
    import test_workspace_api as api_tests


class ImmediateThread:
    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args
    def start(self):
        self.target(*self.args)


class ImportPreflightAPITests(unittest.TestCase):
    def setUp(self):
        self.case = api_tests.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.bytes = b'disposable byte-identity fixture; not parsed'
        self.source = Path(self.case.temp.name) / 'fixture.h5'
        self.source.write_bytes(self.bytes)
        self.identity = hashlib.sha256(self.bytes).hexdigest()
        self.case.sources.rows[0].update(source_sha256=self.identity,
            manifest={'source_path': str(self.source), 'source_sha256': self.identity, 'source_size': len(self.bytes)})
        self.case.service.config['connection'] = {'credential_provider': {'container': 'unused-fixture'}}
        self.patches = [patch('workspace_api.threading.Thread', ImmediateThread),
            patch('recording_workspace.workspace_tables', return_value=(None, self.case.sources, self.case.events, None))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def latest_job(self):
        rows = self.case.client.get('/api/jobs').get_json()['jobs']
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_duplicate_local_file_skips_parser_and_preserves_excluded_frozen_state(self):
        self.case.data_store_states.insert1({'project_uuid': self.case.service.project['project_uuid'],
            'source_sha256': self.identity, 'version': 4, 'frozen': True, 'archived': True, 'query_excluded': True,
            'updated_at': dt.datetime(2026, 9, 27), 'actor': 'fixture', 'server_actor': 'fixture', 'actor_kind': 'local_user', 'reason': 'Keep'})
        before = copy.deepcopy((self.case.sources.rows, self.case.data_store_states.rows))
        renamed = self.source.with_name('renamed.h5')
        renamed.write_bytes(self.bytes)
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('Duplicate must not invoke parser')):
            response = self.case.client.post('/api/imports', json={'source_path': str(renamed)}, headers=self.case.headers)
        self.assertEqual(response.status_code, 202)
        job = self.latest_job()
        self.assertEqual(job['status'], 'duplicate')
        self.assertEqual(job['existing_source']['source_path'], str(self.source))
        self.assertEqual(renamed.read_bytes(), self.bytes)
        self.assertEqual((self.case.sources.rows, self.case.data_store_states.rows), before)
        self.assertEqual(self.case.events.rows[-1]['action'], 'import_job_duplicate')
        self.assertEqual(self.case.events.rows[-1]['payload']['audit']['outcome'], 'completed')

    def test_duplicate_upload_discards_only_new_staging_copy(self):
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('No duplicate parse')):
            response = self.case.client.post('/api/imports', data={'file': (io.BytesIO(self.bytes), 'different-name.h5')},
                content_type='multipart/form-data', headers=self.case.headers)
        self.assertEqual(response.status_code, 202)
        job = self.latest_job()
        self.assertEqual(job['status'], 'duplicate')
        self.assertTrue(job['duplicate_staging_removed'])
        self.assertFalse(Path(job['source']).exists())
        self.assertTrue(self.source.exists())
        self.assertEqual(self.source.read_bytes(), self.bytes)
        self.assertFalse(list((Path(self.case.temp.name) / 'raw-uploads').iterdir()))

    def test_same_filename_different_content_is_warned_not_silently_deduplicated(self):
        self.source.write_bytes(b'different bytes; parser should validate identities')
        with patch('workspace_api.subprocess.run') as parser:
            parser.return_value.returncode = 1
            def failed_validation(command, stdout, stderr):
                stdout.write('Import stopped: ValueError: Existing recording identities require reconciliation.\n')
                from workspace_import_progress import ProgressReporter
                ProgressReporter(command[command.index('--progress-file')+1]).emit('failed', outcome='failed', catalog_committed=False, commit_state='not_started', error='Existing recording identities require reconciliation')
                return parser.return_value
            parser.side_effect = failed_validation
            response = self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        self.assertEqual(response.status_code, 202)
        parser.assert_called_once()
        job = self.latest_job()
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(len(job['duplicate_check']['same_name_warnings']), 1)
        self.assertIn('Existing recording identities require reconciliation', job['error'])
        self.assertFalse(self.case.data_store_states.rows)
        self.assertEqual(len(self.case.sources.rows), 1)

    def test_identical_source_in_other_project_fails_without_relinking(self):
        self.case.sources.rows[0]['project_uuid'] = '00000000-0000-0000-0000-000000000001'
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('No cross-project parse')):
            self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        job = self.latest_job()
        self.assertEqual(job['status'], 'failed')
        self.assertIn('another project', job['error'])
        self.assertEqual(self.case.sources.rows[0]['project_uuid'], '00000000-0000-0000-0000-000000000001')
