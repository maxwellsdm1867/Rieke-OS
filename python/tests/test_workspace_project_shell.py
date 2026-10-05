"""A project's shell is independent of its SQL, recordings, and derived caches."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

from flask import Flask, jsonify
from disco.projects.project_shell import create_project_shell, unused_session
from workspace_desktop import DesktopServices
from disco.projects.project_validation import validate_project_folder


class ProjectShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.project_uuid = str(uuid.uuid4())
        (self.project / 'project.json').write_text(json.dumps({
            'format': 'recording-project', 'version': 1, 'name': 'Large recording project',
            'project_uuid': self.project_uuid, 'catalog_ref': 'catalog.json'}))
        (self.project / 'catalog.json').write_text(json.dumps({
            'format': 'recording-catalog-reference', 'version': 1, 'project_uuid': self.project_uuid,
            'connection': {'credential_provider': {'kind': 'native-project'}},
            'managed_database': {'kind': 'native-mysql'}}))
        self.frontend = self.root / 'frontend'
        self.frontend.mkdir()
        (self.frontend / 'index.html').write_text('<html><head></head><body>Project shell</body></html>')
        env = patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1',
            'RIEKE_DESKTOP_FRONTEND': str(self.frontend), 'RIEKE_DESKTOP_USER_STATE': str(self.root / 'state')})
        env.start()
        self.addCleanup(env.stop)
        self.identity = {'session_id': str(uuid.uuid4()), 'pid': os.getpid(),
            'project_uuid': self.project_uuid, 'project_path': str(self.project),
            'source_commit': 'test-source', 'data_deferred': True}
        self.cleanup = Mock()
        self.build = Mock(side_effect=self.successful_build)
        self.app = create_project_shell(self.project, self.root / 'missing-parser',
            user_state=self.root / 'state', identity=self.identity, build=self.build,
            cleanup_failed=self.cleanup)
        self.client = self.app.test_client()
        self.data = self.app.extensions['project_data']
        self.headers = {'X-Workspace-Request': '1'}
        self.stop_data = Mock()
        self.inbox = Mock()

    def successful_build(self, capture, begin):
        begin()
        app = Flask('scientific-data')
        capture(app)
        app.extensions.update(desktop_stop_database=self.stop_data, h5_inbox=self.inbox)
        app.get('/api/overview')(lambda: jsonify(project_uuid=self.project_uuid, counts={'epochs': 17}))
        return app

    def activate(self, retry=False):
        return self.client.post('/api/project/activate', json={'retry': retry}, headers=self.headers)

    def test_html_and_discovery_do_not_inspect_database_or_recordings(self):
        # A sparse 200 GiB file has negligible allocated storage. Its size and
        # deliberately invalid bytes cannot affect the shell's read set.
        recordings = self.project / 'raw-uploads'
        recordings.mkdir()
        with (recordings / 'unreadable.h5').open('wb') as handle:
            handle.truncate(200 * 1024**3)
        (recordings / 'unreadable.h5').chmod(0)
        with patch('disco.projects.project_database.ensure_project_database', side_effect=AssertionError('SQL startup')), \
                patch('recording_workspace.digest', side_effect=AssertionError('recording hashing')), \
                patch.object(Path, 'rglob', side_effect=AssertionError('recursive scan')):
            for path in ('/', '/api/projects', '/api/health', '/api/project/data-status'):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            self.assertEqual(self.client.get('/api/overview').status_code, 409)
        self.build.assert_not_called()
        self.assertTrue(unused_session(self.root / 'state', self.identity))
        self.app.extensions['desktop_stop_database']()
        self.cleanup.assert_not_called()
        self.assertFalse((self.project / 'database').exists())
        self.assertFalse((self.project / 'exports').exists())

    def test_storage_problems_are_deferred_by_folder_discovery(self):
        result = validate_project_folder(self.project, verify_storage=False)
        self.assertTrue(result['valid'])
        self.assertEqual(result['database_status'], 'not_loaded')
        with self.assertRaisesRegex(ValueError, 'service.json'):
            validate_project_folder(self.project)
        response = self.client.post('/api/projects/inspect-folder',
            json={'directory': str(self.project)}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['database_status'], 'not_loaded')

    def test_explicit_data_action_initializes_once_and_installs_lifecycle(self):
        self.assertEqual(self.activate().status_code, 200)
        self.assertEqual(self.activate().status_code, 200)
        self.build.assert_called_once()
        self.assertFalse(unused_session(self.root / 'state', self.identity))
        self.inbox.start.assert_called_once()
        self.assertIs(self.app.extensions['h5_inbox'], self.inbox)
        self.assertEqual(self.client.get('/api/overview').json['counts']['epochs'], 17)
        self.assertEqual(self.client.get('/api/projects').json['project_data']['status'], 'ready')
        self.app.extensions['desktop_stop_database']()
        self.stop_data.assert_called_once()

    def test_failed_load_leaves_shell_available_and_retry_is_explicit(self):
        self.build.side_effect = FileNotFoundError('The requested recording is unavailable')
        self.assertEqual(self.activate().status_code, 400)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/api/projects').status_code, 200)
        self.assertEqual(self.activate().status_code, 400)
        self.build.assert_called_once()
        self.cleanup.assert_not_called()
        self.assertTrue(unused_session(self.root / 'state', self.identity))
        self.build.side_effect = self.successful_build
        self.assertEqual(self.activate(retry=True).status_code, 200)
        self.assertEqual(self.build.call_count, 2)

    def test_partial_load_closes_its_database_and_preserves_recovery_on_failure(self):
        def fail(capture, begin):
            begin()
            raise ValueError('Corrupt requested metadata')
        self.build.side_effect = fail
        self.assertEqual(self.activate().status_code, 400)
        self.cleanup.assert_called_once()
        self.assertFalse(unused_session(self.root / 'state', self.identity))
        self.cleanup.side_effect = ValueError('Database is still writing')
        with self.assertLogs(self.app.logger, level='ERROR'):
            self.assertEqual(self.activate(retry=True).status_code, 400)
        self.assertIn('still writing', self.data.status()['cleanup_error'])
        with self.assertRaisesRegex(ValueError, 'still writing'):
            self.data.stop()
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_concurrent_activation_does_not_duplicate_services(self):
        began, release = threading.Event(), threading.Event()
        def build(capture, begin):
            began.set()
            self.assertTrue(release.wait(2))
            return self.successful_build(capture, begin)
        self.build.side_effect = build
        errors = []
        def activate():
            try: self.data.activate()
            except Exception as error: errors.append(error)
        first, second = threading.Thread(target=activate), threading.Thread(target=activate)
        first.start()
        self.assertTrue(began.wait(2))
        second.start()
        self.assertEqual(self.client.get('/api/project/data-status').json['status'], 'loading')
        self.assertEqual(self.client.get('/').status_code, 200)
        release.set()
        first.join(2); second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.build.assert_called_once()

    def test_supervisor_dismisses_only_proven_unused_shells_without_database_reads(self):
        services = DesktopServices.__new__(DesktopServices)
        services.user_state = self.root / 'state'
        services.lock = threading.RLock()
        process = Mock(); process.poll.return_value = 0
        services.children = {str(self.project): {'record': self.identity, 'process': process}}
        services._save = Mock()
        with patch.object(services, '_clean_database', side_effect=AssertionError('database inspected')):
            self.assertEqual(services.records(), [])
        self.assertFalse(unused_session(self.root / 'state', {**self.identity, 'source_commit': 'other'}))
        self.data.begin_database()
        self.assertFalse(unused_session(self.root / 'state', self.identity))



if __name__ == "__main__":
    unittest.main()
