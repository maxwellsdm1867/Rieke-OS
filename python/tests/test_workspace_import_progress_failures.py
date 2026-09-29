"""Adversarial import job failures, using disposable files and SQL doubles only."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from recording_workspace import write_json
from workspace_import_check import SourceChangedError
from workspace_import_progress import ProgressReporter, read_job, read_jobs, recover_jobs

try:
    from . import test_workspace_import_api as import_tests
except ImportError:
    import test_workspace_import_api as import_tests


class HeldThread:
    """Accept the HTTP request; explicitly execute its worker after it ends."""
    pending = []

    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.pending.append(self)

    def run(self):
        return self.target(*self.args)


class ImportProgressFailures(unittest.TestCase):
    def setUp(self):
        self.fixture = import_tests.ImportPreflightAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.case = self.fixture.case
        self.source = self.fixture.source
        HeldThread.pending = []
        patcher = patch('workspace_api.threading.Thread', HeldThread)
        patcher.start()
        self.addCleanup(patcher.stop)

    def submit(self, source=None):
        return self.case.client.post('/api/imports', json={'source_path': str(source or self.source)},
                                     headers=self.case.headers)

    def rows(self):
        response = self.case.client.get('/api/jobs')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['jobs']

    def job(self, identity):
        return next(row for row in self.rows() if row['job_uuid'] == identity)

    def accepted(self, source=None):
        response = self.submit(source)
        self.assertEqual(response.status_code, 202, response.get_json())
        return response.get_json()['job_uuid'], HeldThread.pending[-1]

    def test_second_import_is_rejected_until_first_worker_finishes(self):
        identity, worker = self.accepted()
        self.assertEqual(self.submit().status_code, 409)
        self.assertEqual(len(HeldThread.pending), 1)
        worker.run()
        self.assertEqual(self.job(identity)['status'], 'duplicate')
        self.assertEqual(self.submit().status_code, 202)

    def test_accepted_worker_survives_end_of_request_context(self):
        identity, worker = self.accepted()
        # There is no request context while this worker executes; polling comes
        # from another client, as after navigation/disconnection and reconnect.
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('Duplicate must not parse')):
            worker.run()
        other = self.case.app.test_client()
        records = other.get('/api/jobs').get_json()['jobs']
        self.assertEqual(next(row for row in records if row['job_uuid'] == identity)['status'], 'duplicate')

    def test_source_removed_after_acceptance_fails_and_releases_lock(self):
        identity, worker = self.accepted()
        self.source.unlink()
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('Missing source must not parse')):
            worker.run()
        self.assertEqual(self.job(identity)['status'], 'failed')
        self.source.write_bytes(self.fixture.bytes)
        self.assertEqual(self.submit().status_code, 202)

    def test_source_changed_during_hash_never_starts_parser(self):
        identity, worker = self.accepted()
        before = len(self.case.sources.rows)
        with patch('workspace_api.classify_source', side_effect=SourceChangedError('changed during hashing')), \
                patch('workspace_api.subprocess.run', side_effect=AssertionError('Unstable source must not parse')):
            worker.run()
        job = self.job(identity)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('changed during hashing', job['error'])
        self.assertEqual(len(self.case.sources.rows), before)
        self.assertFalse(self.case.protocol_bindings.rows)

    def test_sql_audit_failure_stays_visible_without_relabeling_duplicate(self):
        identity, worker = self.accepted()
        with patch.object(self.case.events, 'insert1', side_effect=PermissionError('SQL audit unavailable')):
            worker.run()
        job = self.job(identity)
        self.assertEqual(job['status'], 'duplicate')
        self.assertIn('SQL audit unavailable', job['audit_write_error'])
        self.assertEqual(self.submit().status_code, 202)

    def test_corrupt_queued_job_does_not_leak_worker_lock(self):
        identity, worker = self.accepted()
        worker.args[1].write_text('{broken')
        worker.run()
        job = self.job(identity)
        self.assertIn(job['status'], {'failed', 'interrupted'})
        self.assertTrue(job.get('error'))
        self.assertEqual(self.submit().status_code, 202)

    def test_corrupt_history_record_does_not_hide_healthy_jobs(self):
        identity, worker = self.accepted()
        worker.run()
        bad = worker.args[1].with_name('corrupt-job.json')
        bad.write_text('{broken')
        rows = self.rows()
        self.assertEqual(next(row for row in rows if row['job_uuid'] == identity)['status'], 'duplicate')
        corrupt = next(row for row in rows if row['job_uuid'] == 'corrupt-job')
        self.assertTrue(corrupt.get('error'))
        self.assertNotIn(corrupt['status'], {'complete', 'duplicate'})

    def test_job_record_disappearing_before_worker_does_not_lock_future_imports(self):
        _, worker = self.accepted()
        worker.args[1].unlink()
        worker.run()
        self.assertEqual(self.submit().status_code, 202)

    def test_queue_write_permission_failure_never_starts_worker_or_leaks_lock(self):
        with patch('workspace_api.write_json', side_effect=PermissionError('Job directory not writable')):
            response = self.submit()
        self.assertGreaterEqual(response.status_code, 400)
        self.assertFalse(HeldThread.pending)
        self.assertEqual(self.submit().status_code, 202)

    def test_worker_progress_and_final_log_write_failure_releases_lock(self):
        _, worker = self.accepted()
        with patch('workspace_api.write_json', side_effect=PermissionError('disk full')):
            try:
                worker.run()
            except PermissionError:
                pass  # A failed durable log may escape the worker, never its lock.
        self.assertEqual(self.submit().status_code, 202)
        self.assertFalse(self.case.protocol_bindings.rows)

    def test_malformed_import_request_is_bad_request_not_server_failure(self):
        for payload in ([], None, {'source_path': []}, {'source_path': 1}):
            with self.subTest(payload=payload):
                response = self.case.client.post('/api/imports', data=json.dumps(payload),
                    content_type='application/json', headers=self.case.headers)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(HeldThread.pending)
        self.assertEqual(self.submit().status_code, 202)

    def child_failure(self, marker):
        source = Path(self.case.temp.name) / 'invalid-new-source.h5'
        source.write_bytes(b'isolated new source; subprocess is mocked')
        identity, worker = self.accepted(source)

        def parser(command, stdout, stderr):
            self.assertIn('--expected-sha256', command)
            self.assertIn('--progress-file', command)
            if marker is not None:
                progress_path = Path(command[command.index('--progress-file') + 1])
                ProgressReporter(progress_path).emit('failed', outcome='failed', error='Invalid HDF5 fixture',
                    error_type='ValueError', **marker)
            stdout.write('Import stopped: ValueError: Invalid HDF5 fixture.\n')
            return SimpleNamespace(returncode=1)

        with patch('workspace_api.subprocess.run', side_effect=parser) as process:
            worker.run()
        process.assert_called_once()
        return self.job(identity)

    def test_explicit_precommit_parser_failure_is_failed_without_catalog_changes(self):
        count = len(self.case.sources.rows)
        job = self.child_failure({'commit_state': 'not_started', 'catalog_committed': False})
        self.assertEqual(job['status'], 'failed')
        self.assertIs(job['catalog_committed'], False)
        self.assertEqual(len(self.case.sources.rows), count)
        self.assertIn('Invalid HDF5 fixture', job['error'])

    def test_child_failure_without_durable_terminal_marker_requires_reconciliation(self):
        job = self.child_failure(None)
        self.assertEqual(job['status'], 'interrupted')
        self.assertIsNone(job['catalog_committed'])
        self.assertTrue(job['requires_reconciliation'])

    def test_committed_child_failure_is_warning_not_rollback_claim(self):
        job = self.child_failure({'commit_state': 'committed', 'catalog_committed': True})
        self.assertEqual(job['status'], 'complete_with_warnings')
        self.assertTrue(job['catalog_committed'])
        self.assertTrue(job.get('warnings'))
        self.assertEqual(self.submit().status_code, 202)  # No stuck worker lock.

    def test_api_terminal_log_disk_failure_keeps_commit_evidence_and_releases_lock(self):
        source = Path(self.case.temp.name) / 'committed-source.h5'
        source.write_bytes(b'isolated successful child fixture')
        identity, worker = self.accepted(source)
        job_path = worker.args[1]

        def parser(command, stdout, stderr):
            progress = Path(command[command.index('--progress-file') + 1])
            ProgressReporter(progress).emit('complete', outcome='completed',
                commit_state='committed', catalog_committed=True)
            return SimpleNamespace(returncode=0)

        def save(path, value):
            if path == job_path and value.get('status') in {'complete', 'complete_with_warnings'}:
                raise PermissionError('disk full saving final API receipt')
            return write_json(path, value)

        with patch('workspace_api.subprocess.run', side_effect=parser), \
                patch('workspace_api.write_json', side_effect=save):
            worker.run()
        job = self.job(identity)
        self.assertEqual(job['status'], 'interrupted')
        self.assertTrue(job['catalog_committed'])
        self.assertTrue(job['requires_reconciliation'])
        self.assertIn('Terminal job log could not be saved', job['progress']['error'])
        self.assertEqual(self.submit().status_code, 202)


class ProgressLogDurability(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.job = self.folder / 'fixture-job.json'
        self.sidecar = self.folder / 'progress' / self.job.name
        write_json(self.job, {'status': 'validating', 'source': '/fixture/raw.h5',
                             'owner_run_id': 'old-server', 'started_at': '2026-09-27T00:00:00+00:00'})

    def test_restart_without_commit_marker_is_unknown_not_safe_failure(self):
        recover_jobs(self.folder, 'new-server')
        row = read_job(self.job, 'new-server')
        self.assertEqual(row['status'], 'interrupted')
        self.assertIsNone(row['catalog_committed'])
        self.assertTrue(row['requires_reconciliation'])
        persisted = json.loads(self.job.read_text())
        self.assertEqual(persisted['status'], 'interrupted')
        self.assertIsNone(persisted['catalog_committed'])

    def test_terminal_progress_disk_failure_preserves_prior_committed_evidence(self):
        reporter = ProgressReporter(self.sidecar)
        reporter.emit('catalog_committed', commit_state='committed', catalog_committed=True)
        with patch('workspace_import_progress.atomic_json', side_effect=PermissionError('disk full after SQL commit')):
            final = reporter.emit('complete', outcome='completed', commit_state='committed', catalog_committed=True)
        self.assertIn('disk full', final['progress_write_error'])
        row = read_job(self.job, 'new-server')
        self.assertTrue(row['catalog_committed'])
        self.assertEqual(row['status'], 'interrupted')
        self.assertTrue(row['requires_reconciliation'])
        self.assertEqual(row['progress']['stage'], 'catalog_committed')

    def test_missing_commit_marker_after_disk_failure_does_not_invent_rollback(self):
        with patch('workspace_import_progress.atomic_json', side_effect=PermissionError('disk full')):
            reporter = ProgressReporter(self.sidecar)
            reporter.emit('catalog_committed', commit_state='committed', catalog_committed=True)
        row = read_job(self.job, 'new-server')
        self.assertIsNone(row['catalog_committed'])
        self.assertTrue(row['requires_reconciliation'])

    def test_polling_heartbeat_never_changes_measured_stage_timestamp(self):
        write_json(self.job, {'status': 'validating', 'owner_run_id': 'server'})
        reporter = ProgressReporter(self.sidecar)
        reporter.emit('validating_metadata', completed=3, total=100, unit='epochs')
        first = read_job(self.job, 'server', {'fixture-job'})
        second = read_job(self.job, 'server', {'fixture-job'})
        self.assertTrue(second['monitor_alive'])
        self.assertEqual(first['progress']['updated_at'], second['progress']['updated_at'])
        self.assertEqual(second['progress']['completed'], 3)
        self.assertEqual(second['progress']['total'], 100)

    def test_corrupt_sidecar_is_visible_without_hiding_parent_job(self):
        self.sidecar.parent.mkdir()
        self.sidecar.write_text('{bad')
        row = read_job(self.job, 'new-server')
        self.assertEqual(row['warnings'][0]['stage'], 'progress_log')
        self.assertIsNone(row['catalog_committed'])

    def test_malformed_json_object_shapes_never_crash_job_listing(self):
        self.sidecar.parent.mkdir()
        self.sidecar.write_text('{bad')
        for invalid in ({'status': []}, {'status': 'complete', 'warnings': None},
                        {'status': {}, 'source': {'unexpected': True}}):
            with self.subTest(invalid=invalid):
                write_json(self.job, invalid)
                recover_jobs(self.folder, 'new-server')
                rows = read_jobs(self.folder, 'server')
                self.assertEqual(len(rows), 1)
                self.assertTrue(rows[0].get('error') or rows[0].get('warnings'))

    def test_parser_rejects_changed_preflight_hash_before_loading_parser(self):
        from recording_workspace import prepare
        source = self.folder / 'changed.h5'
        source.write_bytes(b'changed after stable duplicate check')
        with patch('recording_workspace.load_parser', side_effect=AssertionError('Hash mismatch must fail before parser load')):
            with self.assertRaisesRegex(ValueError, 'changed|checksum|identity'):
                prepare(source, self.folder / 'project', self.folder / 'unused-parser', expected_sha256='0'*64)
        self.assertFalse((self.folder / 'project').exists())

    def test_cli_final_receipt_disk_failure_never_overwrites_known_commit(self):
        import recording_workspace
        progress_path = self.folder / 'cli-progress.json'
        manifest = {'status': 'imported', 'counts': {'epochs': 1}}
        failed = False

        def save(path, value):
            nonlocal failed
            if value.get('status') == 'imported' and not failed:
                failed = True
                raise PermissionError('transient disk failure after catalog commit')
            return write_json(path, value)

        def import_catalog(*args):
            args[-1]('catalog_committed', commit_state='committed', catalog_committed=True)
            return manifest

        arguments = ['recording_workspace.py', str(self.folder / 'fixture.h5'),
            '--project-dir', str(self.folder / 'cli-project'), '--retinanalysis', str(self.folder),
            '--progress-file', str(progress_path), '--container', 'isolated-fixture']
        with patch('sys.argv', arguments), \
                patch('recording_workspace.prepare', return_value=({}, [], manifest, self.folder)), \
                patch('recording_workspace.import_catalog', side_effect=import_catalog), \
                patch('recording_workspace.write_json', side_effect=save):
            with self.assertRaises(SystemExit):
                recording_workspace.main()
        self.assertTrue(failed)
        progress = json.loads(progress_path.read_text())
        self.assertTrue(progress['catalog_committed'])
        self.assertEqual(progress['commit_state'], 'committed')
        child_job = next((self.folder / 'cli-project' / 'logs' / 'imports').glob('*.json'))
        self.assertTrue(json.loads(child_job.read_text())['catalog_committed'])

    def test_corrupt_legacy_history_does_not_abort_postcommit_finalization(self):
        from recording_workspace import sync_job_history
        folder = self.folder / 'logs' / 'imports'
        folder.mkdir(parents=True)
        corrupt = folder / (str(uuid.uuid4()) + '.json')
        corrupt.write_text('{broken')
        valid_id = str(uuid.uuid4())
        write_json(folder / (valid_id + '.json'), {'status': 'failed',
                   'finished_at': '2026-09-27T00:00:00+00:00', 'error': 'fixture validation failure'})
        events = Mock()
        sync_job_history(self.folder, events, str(uuid.uuid4()))
        events.insert1.assert_called_once()
        self.assertEqual(events.insert1.call_args.args[0]['event_uuid'], valid_id)
        self.assertEqual(corrupt.read_text(), '{broken')
        diagnostics = list((self.folder / 'logs' / 'errors').glob('history-*.json'))
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(json.loads(diagnostics[0].read_text())['stage'], 'legacy_job_history')
