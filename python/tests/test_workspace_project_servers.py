import io
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from workspace_project_servers import open_project, ready_url, write_server_record, project_server_port


class ProjectServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'project'
        index = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(Path(self.temp.name) / 'preferences/project-index.json')})
        index.start()
        self.addCleanup(index.stop)
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
        with patch('workspace_project_servers.urlopen', return_value=io.StringIO(json.dumps({'status': 'ready', 'project_uuid': self.identity, 'project_path':str(self.path.resolve())}))) as get:
            self.assertEqual(ready_url(self.path, self.identity), 'http://127.0.0.1:8877/')
            self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:8877/api/health')
        with patch('workspace_project_servers.urlopen', return_value=io.StringIO(json.dumps({'status': 'ready', 'project_uuid': str(uuid.uuid4())}))):
            self.assertIsNone(ready_url(self.path, self.identity))
        write_server_record(self.path, self.identity, '8877')
        with patch('workspace_project_servers.urlopen') as get:
            self.assertIsNone(ready_url(self.path, self.identity))
            get.assert_not_called()

    def test_reopen_reuses_available_port_for_exact_local_project(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        write_server_record(self.path, self.identity, port)
        self.assertEqual(project_server_port(self.path, self.identity), port)

    def test_port_conflict_falls_back_without_touching_existing_listener(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            write_server_record(self.path, self.identity, port)
            alternative = project_server_port(self.path, self.identity)
            self.assertNotEqual(alternative, port)
            self.assertGreaterEqual(alternative, 1024)
            self.assertEqual(listener.getsockname()[1], port)

    def test_copied_foreign_invalid_or_linked_record_never_selects_sender_port(self):
        record_path = self.path / 'logs/workspace-server.json'
        for case in ('copied', 'other-uuid', 'low-port', 'string-port', 'boolean-port', 'symlink'):
            with self.subTest(case=case):
                if record_path.is_symlink():
                    record_path.unlink()
                write_server_record(self.path, self.identity, 8877)
                record = json.loads(record_path.read_text())
                if case == 'copied':
                    record['project_path'] = str(self.path.parent / 'sender')
                elif case == 'other-uuid':
                    record['project_uuid'] = str(uuid.uuid4())
                elif case == 'low-port':
                    record['port'] = 80
                elif case == 'string-port':
                    record['port'] = '8877'
                elif case == 'boolean-port':
                    record['port'] = True
                record_path.write_text(json.dumps(record))
                if case == 'symlink':
                    target = self.path / 'sender-record.json'
                    target.write_text(record_path.read_text())
                    record_path.unlink()
                    record_path.symlink_to(target)
                listener = Mock()
                listener.getsockname.return_value = ('127.0.0.1', 45123)
                context = Mock()
                context.__enter__ = Mock(return_value=listener)
                context.__exit__ = Mock(return_value=False)
                with patch('workspace_project_servers.socket.socket', return_value=context):
                    self.assertEqual(project_server_port(self.path, self.identity), 45123)
                listener.bind.assert_called_once_with(('127.0.0.1', 0))

    def test_existing_process_reused_without_spawn(self):
        with patch('workspace_project_servers.ready_url', return_value='http://127.0.0.1:8877/'), patch('workspace_project_servers.subprocess.Popen') as spawn:
            result = open_project(self.path, self.identity, self.path)
            self.assertEqual(result['project_uuid'], self.identity)
            spawn.assert_not_called()

    def test_explicit_folder_wins_over_same_identity_native_copy(self):
        copy = self.path.parent / 'copy'
        copy.mkdir()
        project = json.loads((self.path / 'project.json').read_text())
        project['name'] = 'A copy sorted before the selected project'
        (copy / 'project.json').write_text(json.dumps(project))
        for directory in (self.path, copy):
            catalog = json.loads((self.path / 'catalog.json').read_text())
            catalog['managed_database'] = {'kind': 'native-mysql'}
            (directory / 'catalog.json').write_text(json.dumps(catalog))
        with patch('workspace_project_servers.ready_url', return_value='http://127.0.0.1:8877/') as ready:
            open_project(self.path, self.identity, self.path)
            ready.assert_called_once_with(self.path.resolve(), self.identity)
        from workspace_desktop import desktop_open_project
        services = Mock()
        with patch('workspace_desktop._SERVICES', services):
            desktop_open_project(self.path, self.identity, self.path)
        services.open.assert_called_once_with(str(self.path.resolve()), self.identity, self.path, 300)

    def test_copied_server_record_never_reuses_original_service(self):
        write_server_record(self.path,self.identity,8877)
        record=self.path/'logs/workspace-server.json'
        value=json.loads(record.read_text());value['project_path']=str(self.path.parent/'original')
        record.write_text(json.dumps(value))
        with patch('workspace_project_servers.urlopen') as get:
            self.assertIsNone(ready_url(self.path,self.identity))
            get.assert_not_called()
        write_server_record(self.path,self.identity,8877)
        with patch('workspace_project_servers.urlopen',return_value=io.StringIO(json.dumps({
            'status':'ready','project_uuid':self.identity,'project_path':str(self.path.parent/'original')}))):
            self.assertIsNone(ready_url(self.path,self.identity))

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
