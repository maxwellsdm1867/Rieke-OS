"""Duplicate import jobs use disposable files and SQL doubles only."""
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import unittest
import tempfile
import uuid
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
        self.assertEqual(job['catalog_delta'], dict.fromkeys(
            ['sources_added', 'cells_added', 'epochs_added', 'responses_added', 'stimuli_added', 'protocol_types_added'], 0))
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
        self.assertEqual(job['catalog_delta'], dict.fromkeys(
            ['sources_added', 'cells_added', 'epochs_added', 'responses_added', 'stimuli_added', 'protocol_types_added'], 0))
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
        self.assertFalse(job['recording_storage']['original_removal_safe'])
        self.assertEqual(len(job['duplicate_check']['same_name_warnings']), 1)
        self.assertIn('Existing recording identities require reconciliation', job['error'])
        self.assertFalse(self.case.data_store_states.rows)
        self.assertEqual(len(self.case.sources.rows), 1)

    def test_new_path_import_uses_verified_managed_copy_for_every_provider(self):
        self.source.write_bytes(b'new source bytes')
        def parse(command, stdout, stderr):
            retained = Path(command[2])
            self.assertNotEqual(retained, self.source)
            self.assertTrue(retained.is_relative_to(Path(self.case.temp.name).resolve() / 'raw-uploads'))
            self.assertEqual(retained.read_bytes(), self.source.read_bytes())
            from workspace_import_progress import ProgressReporter
            ProgressReporter(command[command.index('--progress-file') + 1]).emit(
                'catalog_committed', commit_state='committed', catalog_committed=True,
                catalog_delta={'sources_added': 1, 'cells_added': 2, 'epochs_added': 9,
                               'responses_added': 9, 'stimuli_added': 9})
            return type('Completed', (), {'returncode': 0})()
        with patch('workspace_api.subprocess.run', side_effect=parse):
            self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        job = self.latest_job()
        self.assertIn(job['status'], {'complete', 'complete_with_warnings'}, job)
        self.assertTrue(job['recording_storage']['original_removal_safe'])
        self.assertTrue(job['recording_storage']['verified'])
        self.assertTrue(job['retained_in_project'])
        self.assertTrue(self.source.exists())
        self.assertEqual(job['catalog_delta']['epochs_added'], 9)
        self.assertEqual(job['catalog_delta']['cells_added'], 2)

    def test_new_upload_reports_verified_copy_only_after_success(self):
        with patch('workspace_api.subprocess.run') as parser:
            parser.return_value.returncode = 0
            self.case.client.post('/api/imports',
                data={'file': (io.BytesIO(b'new uploaded bytes'), 'uploaded.h5')},
                content_type='multipart/form-data', headers=self.case.headers)
        job = self.latest_job()
        self.assertIn(job['status'], {'complete', 'complete_with_warnings'}, job)
        self.assertTrue(job['recording_storage']['original_removal_safe'])
        self.assertTrue(job['recording_storage']['verified'])
        self.assertTrue(job['retained_in_project'])
        self.assertEqual(Path(job['source']).read_bytes(), b'new uploaded bytes')

    def test_managed_folder_drop_uses_import_pipeline_without_second_copy(self):
        inbox = self.case.app.extensions['h5_inbox']
        self.assertFalse(inbox.enabled)
        inbox.scan()
        source = inbox.path / 'finder-drop.h5'
        source.write_bytes(b'new folder drop')
        current = [100]
        inbox.clock = lambda: current[0]
        inbox.scan()
        def parse(command, stdout, stderr):
            self.assertEqual(Path(command[2]), source)
            return type('Completed', (), {'returncode': 0})()
        current[0] += 6
        with patch('workspace_api.subprocess.run', side_effect=parse):
            inbox.scan()
        job = self.latest_job()
        self.assertIn(job['status'], {'complete', 'complete_with_warnings'}, job)
        self.assertEqual(job['origin'], 'h5-inbox')
        self.assertFalse(job['recording_storage']['original_removal_safe'])
        self.assertEqual(Path(job['source']), source)
        self.assertEqual(list(inbox.path.iterdir()), [source])
        self.assertTrue(job['recording_storage']['verified'])

    def test_h5_folder_open_requires_local_mutation_header_and_empty_body(self):
        endpoint = '/api/import-inbox/open-folder'
        with patch('workspace_h5_inbox.subprocess.run') as opener:
            self.assertEqual(self.case.client.post(endpoint, json={}).status_code, 403)
            self.assertEqual(self.case.client.post(endpoint, json={'path': '/tmp'}, headers=self.case.headers).status_code, 400)
            opener.assert_not_called()
            self.assertEqual(self.case.client.post(endpoint, json={}, headers=self.case.headers).status_code, 200)
            self.assertEqual(opener.call_args.args[0][-1], str(self.case.app.extensions['h5_inbox'].path))

    def test_identical_source_in_other_project_fails_without_relinking(self):
        self.case.sources.rows[0]['project_uuid'] = '00000000-0000-0000-0000-000000000001'
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('No cross-project parse')):
            self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        job = self.latest_job()
        self.assertEqual(job['status'], 'failed')
        self.assertIn('another project', job['error'])
        self.assertEqual(self.case.sources.rows[0]['project_uuid'], '00000000-0000-0000-0000-000000000001')


class ImportLibraryAPITests(unittest.TestCase):
    """Real managed filesystem, synchronous HTTP worker and explicit SQL/parser doubles."""
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory
        self.master = temporary_directory()
        self.addCleanup(self.master.cleanup)
        fixture = ImportPreflightAPITests()
        with patch.object(api_tests.tempfile, 'TemporaryDirectory',
                          side_effect=lambda: temporary_directory(dir=self.master.name)):
            fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.case = fixture, fixture.case
        self.project = Path(self.case.temp.name).resolve()
        (self.project / 'project.json').write_text(json.dumps({
            'format': 'recording-project', 'version': 1, **self.case.service.project}))
        self.source = Path(self.master.name).resolve() / 'Downloads' / 'original.h5'
        self.source.parent.mkdir()
        self.source.write_bytes(b'new external recording')
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def submit(self, source=None, *, upload=False, returncode=0):
        with patch('workspace_api.subprocess.run') as parser:
            parser.return_value.returncode = returncode
            if upload:
                response = self.case.client.post('/api/imports', data={'file': (io.BytesIO(self.source.read_bytes()), self.source.name)},
                    content_type='multipart/form-data', headers=self.case.headers)
            else:
                response = self.case.client.post('/api/imports', json={'source_path': str(source or self.source)}, headers=self.case.headers)
        self.assertEqual(response.status_code, 202)
        return self.fixture.latest_job()

    def test_successful_external_import_reports_verified_library_and_safe_original(self):
        job = self.submit()
        storage = job['recording_storage']
        self.assertEqual(storage['kind'], 'managed_library')
        self.assertTrue(storage['verified'])
        self.assertTrue(storage['original_removal_safe'])
        self.assertTrue(job['retained_in_library'])
        self.assertFalse(job['retained_in_project'])
        self.assertTrue(Path(storage['path']).is_relative_to(self.project.parent / 'recordings'))
        self.assertEqual(Path(storage['path']).read_bytes(), self.source.read_bytes())
        self.assertTrue(self.source.exists(), 'The app never deletes Downloads')

    def test_upload_leaves_one_permanent_copy(self):
        job = self.submit(upload=True)
        self.assertTrue(job['recording_storage']['original_removal_safe'])
        self.assertTrue(job['duplicate_staging_removed'])
        self.assertEqual(len(list(self.project.parent.glob('recordings/**/*.h5'))), 1)
        self.assertEqual(list(self.project.glob('raw-uploads/**/*.h5')), [])

    def test_unconfirmed_import_never_authorizes_original_removal(self):
        job = self.submit(returncode=1)
        self.assertEqual(job['status'], 'interrupted')
        self.assertFalse(job['recording_storage']['original_removal_safe'])
        self.assertTrue(self.source.exists())

    def test_import_from_another_managed_project_does_not_offer_to_delete_input(self):
        other = self.project.parent / 'older-project'
        other.mkdir()
        (other / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1, 'project_uuid': str(uuid.uuid4())}))
        managed = other / 'raw-uploads' / 'original.h5'
        managed.parent.mkdir()
        managed.write_bytes(self.source.read_bytes())
        job = self.submit(managed)
        self.assertFalse(job['recording_storage']['original_removal_safe'])
        self.assertTrue(managed.exists())

    def prepare_duplicate(self):
        from disco.projects.recording_files import retain_recording
        retained = retain_recording(self.project, self.source, self.sha)
        self.case.sources.rows[0].update(source_sha256=self.sha,
            manifest={'source_sha256': self.sha, 'source_path': str(retained), 'source_size': self.source.stat().st_size})
        return retained

    def test_duplicate_external_input_requires_fresh_verification_of_managed_copy(self):
        retained = self.prepare_duplicate()
        job = self.submit()
        self.assertEqual(job['status'], 'duplicate')
        self.assertTrue(job['recording_storage']['original_removal_safe'])
        self.assertEqual(job['recording_storage']['path'], str(retained))
        self.assertTrue(self.source.exists())

    def test_duplicate_managed_input_does_not_offer_to_delete_it(self):
        retained = self.prepare_duplicate()
        job = self.submit(retained)
        self.assertEqual(job['status'], 'duplicate')
        self.assertFalse(job['recording_storage']['original_removal_safe'])
        self.assertTrue(retained.exists())

    def test_duplicate_catalog_with_missing_or_changed_recording_has_no_safe_receipt(self):
        retained = self.prepare_duplicate()
        retained.write_bytes(b'changed managed bytes')
        job = self.submit()
        self.assertEqual(job['status'], 'duplicate')
        self.assertNotIn('recording_storage', job)
        self.assertTrue(self.source.exists())

    def test_inbox_import_keeps_only_library_copy_after_confirmed_success(self):
        inbox = self.case.app.extensions['h5_inbox']
        inbox.scan()
        source = inbox.path / 'finder-drop.h5'
        source.write_bytes(self.source.read_bytes())
        current = [100]
        inbox.clock = lambda: current[0]
        inbox.scan()
        current[0] += 6
        with patch('workspace_api.subprocess.run') as parser:
            parser.return_value.returncode = 0
            inbox.scan()
        job = self.fixture.latest_job()
        self.assertTrue(job['inbox_staging_removed'])
        self.assertFalse(source.exists())
        self.assertFalse(job['recording_storage']['original_removal_safe'])
        self.assertEqual(Path(job['recording_storage']['path']).read_bytes(), self.source.read_bytes())

    def test_changed_inbox_file_is_preserved_after_library_import(self):
        inbox = self.case.app.extensions['h5_inbox']
        inbox.scan()
        source = inbox.path / 'finder-drop.h5'
        source.write_bytes(self.source.read_bytes())
        current = [100]
        inbox.clock = lambda: current[0]
        inbox.scan()
        current[0] += 6
        def parse(*args, **kwargs):
            source.write_bytes(b'a newer recording dropped during import')
            return type('Completed', (), {'returncode': 0})()
        with patch('workspace_api.subprocess.run', side_effect=parse):
            inbox.scan()
        job = self.fixture.latest_job()
        self.assertNotIn('inbox_staging_removed', job)
        self.assertEqual(source.read_bytes(), b'a newer recording dropped during import')
        self.assertTrue(any(row['stage']=='inbox_cleanup' for row in job['warnings']))
        self.assertEqual(Path(job['recording_storage']['path']).read_bytes(), self.source.read_bytes())
