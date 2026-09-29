import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from workspace_project_servers import open_project, ready_url, write_server_record


class ProjectServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'project'
        self.path.mkdir()
        bootstrap = patch('workspace_project_database.ensure_project_database')
        bootstrap.start()
        self.addCleanup(bootstrap.stop)
        self.identity = str(uuid.uuid4())
        (self.path / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1,
            'project_uuid': self.identity, 'name': 'Project'}))
        (self.path / 'catalog.json').write_text(json.dumps({'format': 'recording-catalog-reference', 'version': 1,
            'project_uuid': self.identity}))

    def test_health_requires_exact_identity_and_local_port(self):
        write_server_record(self.path, self.identity, 8877)
        with patch('workspace_project_servers.urlopen', return_value=io.StringIO(json.dumps({'status': 'ready', 'project_uuid': self.identity, 'project_path': str(self.path.resolve())}))) as get:
            self.assertEqual(ready_url(self.path, self.identity), 'http://127.0.0.1:8877/')
            self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:8877/api/health')
        with patch('workspace_project_servers.urlopen', return_value=io.StringIO(json.dumps({'status': 'ready', 'project_uuid': str(uuid.uuid4())}))):
            self.assertIsNone(ready_url(self.path, self.identity))
        write_server_record(self.path, self.identity, '8877')
        with patch('workspace_project_servers.urlopen') as get:
            self.assertIsNone(ready_url(self.path, self.identity))
            get.assert_not_called()

    def test_existing_process_reused_without_spawn(self):
        with patch('workspace_project_servers.ready_url', return_value='http://127.0.0.1:8877/'), patch('workspace_project_servers.subprocess.Popen') as spawn:
            result = open_project(self.path, self.identity, self.path)
            self.assertEqual(result['project_uuid'], self.identity)
            spawn.assert_not_called()

    def test_unknown_project_never_starts(self):
        with patch('workspace_project_servers.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'registered project'):
                open_project(self.path, str(uuid.uuid4()), self.path)
            spawn.assert_not_called()

    def test_new_process_uses_validated_project_and_waits_for_ready(self):
        process = Mock()
        process.poll.return_value = None
        with patch('workspace_project_servers.ready_url', side_effect=[None, 'http://127.0.0.1:8877/']), patch('workspace_project_servers.subprocess.Popen', return_value=process) as spawn:
            result = open_project(self.path, self.identity, self.path)
            self.assertEqual(result['url'], 'http://127.0.0.1:8877/')
            arguments = spawn.call_args.args[0]
            self.assertEqual(arguments[arguments.index('--project-dir') + 1], str(self.path.resolve()))
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])

    def test_failed_start_has_no_successful_navigation(self):
        process = Mock()
        process.poll.return_value = 1
        with patch('workspace_project_servers.ready_url', return_value=None), patch('workspace_project_servers.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(ValueError, 'could not start'):
                open_project(self.path, self.identity, self.path)

    def test_same_uuid_at_another_physical_root_is_not_reused(self):
        write_server_record(self.path, self.identity, 8877)
        for reported in (None, str(self.path.parent / 'copied-project')):
            with self.subTest(reported=reported), patch('workspace_project_servers.urlopen',
                    return_value=io.StringIO(json.dumps({'status':'ready', 'project_uuid':self.identity,
                                                        'project_path':reported}))):
                self.assertIsNone(ready_url(self.path, self.identity))

    def test_copied_server_record_never_contacts_original_process(self):
        write_server_record(self.path, self.identity, 8877)
        path = self.path / 'logs/workspace-server.json'
        record = json.loads(path.read_text())
        record['project_path'] = str(self.path.parent / 'original-project')
        path.write_text(json.dumps(record))
        with patch('workspace_project_servers.urlopen') as get:
            self.assertIsNone(ready_url(self.path, self.identity))
            get.assert_not_called()

    def test_legacy_live_server_requires_restart_instead_of_spawning_duplicate(self):
        write_server_record(self.path, self.identity, 8877)
        response = {'status':'ready', 'project_uuid':self.identity}
        with patch('workspace_project_servers.urlopen', return_value=io.StringIO(json.dumps(response))), \
             patch('workspace_project_servers.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'older server.*Stop the existing'):
                open_project(self.path, self.identity, self.path)
            spawn.assert_not_called()
