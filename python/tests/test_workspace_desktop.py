"""Fault contracts for desktop supervision; no claim of artifact qualification."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from flask import Flask, jsonify
from werkzeug.test import Client, EnvironBuilder
from werkzeug.wrappers import Response

from workspace_desktop import DesktopBoundary, DesktopServices, acquire_project_session
from workspace_app_routes import register_app_routes


class DesktopBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.get('/api/write')(lambda: jsonify(ok=True))
        self.identity = {'pid': 15, 'session_id': 'test-session', 'application_version': '1.2.3',
                         'source_commit': 'source', 'workspace_formats': [1], 'database_compatibility': 1}
        self.boundary = DesktopBoundary(self.app, port=8766, capability='s' * 48,
                                        identity=self.identity, deadline=.01)
        self.client = Client(self.boundary, Response)
        self.headers = {'X-Rieke-Desktop-Capability': 's' * 48}

    def get(self, path, **kwargs):
        overrides = {'REMOTE_ADDR': '127.0.0.1', **kwargs.pop('environ_overrides', {})}
        return self.client.get(path, base_url='http://127.0.0.1:8766', headers=self.headers,
                               environ_overrides=overrides, buffered=True, **kwargs)

    def post(self, operation, **kwargs):
        return self.client.post('/api/desktop/' + operation, base_url='http://127.0.0.1:8766',
                                headers=self.headers, json={}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'}, buffered=True, **kwargs)

    def test_health_is_exact_owned_version_session_and_pid(self):
        value = self.get('/api/desktop/health').json
        self.assertTrue(value['ready'])
        for key, expected in self.identity.items():
            self.assertEqual(value[key], expected)

    def test_capability_is_required_for_ui_and_health(self):
        for path in ('/', '/api/desktop/health', '/api/write'):
            self.assertEqual(self.client.get(path, base_url='http://127.0.0.1:8766').status_code, 403)

    def test_renderer_session_authorizes_science_but_never_desktop_control(self):
        headers = {'X-Rieke-Desktop-Session': self.boundary.renderer_session}
        response = self.client.get('/api/write', base_url='http://127.0.0.1:8766', headers=headers,
                                   environ_overrides={'REMOTE_ADDR': '127.0.0.1'}, buffered=True)
        self.assertEqual(response.status_code, 200)
        for operation in ('health', 'drain', 'resume', 'stop', 'open-project', 'authorize-project'):
            response = self.client.post('/api/desktop/' + operation, base_url='http://127.0.0.1:8766',
                                       headers=headers, json={}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            self.assertEqual(response.status_code, 403)

    def test_wrong_capability_host_origin_and_remote_rejected(self):
        for changes in ({'HTTP_HOST': 'localhost:8766'}, {'HTTP_HOST': '127.0.0.1:9999'},
                        {'HTTP_ORIGIN': 'https://attacker.invalid'}, {'REMOTE_ADDR': '192.168.1.1'},
                        {'HTTP_X_RIEKE_DESKTOP_CAPABILITY': 'x' * 48}):
            self.assertEqual(self.get('/api/desktop/health', environ_overrides=changes).status_code, 403)
        self.assertEqual(self.get('/api/desktop/health', environ_overrides={
            'HTTP_ORIGIN': 'http://127.0.0.1:8766'}).status_code, 200)

    def test_transfer_import_and_refresh_busy_defer_without_shutdown(self):
        for name in ('app_active_writers', 'project_active_writers'):
            with self.subTest(name=name):
                self.app.extensions[name] = lambda: True
                self.assertEqual(self.post('drain').status_code, 409)
                self.assertFalse(self.boundary.draining)
                self.assertEqual(self.get('/api/write').status_code, 200)
                del self.app.extensions[name]

    def test_drain_waits_for_complete_stream_then_rejects_new_operations(self):
        environ = EnvironBuilder(path='/api/write', base_url='http://127.0.0.1:8766', headers=self.headers).get_environ()
        environ['REMOTE_ADDR'] = '127.0.0.1'
        response = self.boundary(environ, lambda *args: None)
        self.assertEqual(self.boundary.active, 1)
        self.assertEqual(self.post('drain').status_code, 409)
        # Closing a response before iteration must release its admission too.
        response.close()
        self.assertEqual(self.boundary.active, 0)
        self.assertEqual(self.post('drain').status_code, 200)
        self.assertEqual(self.get('/api/write').status_code, 503)
        self.assertEqual(self.post('resume').status_code, 200)
        self.assertEqual(self.get('/api/write').status_code, 200)

    def test_inbox_is_quiesced_and_busy_rechecked(self):
        busy = [False]
        inbox = Mock()
        inbox.stop.side_effect = lambda: busy.__setitem__(0, True)
        self.app.extensions.update(h5_inbox=inbox, project_active_writers=lambda: busy[0])
        self.assertEqual(self.post('drain').status_code, 409)
        inbox.stop.assert_called_once()
        inbox.start.assert_called_once()
        self.assertFalse(self.boundary.draining)

    def test_stop_requires_drain_and_database_acknowledgement(self):
        self.boundary.stop_callback = Mock()
        self.assertEqual(self.post('stop').status_code, 409)
        self.assertEqual(self.post('drain').status_code, 200)
        stop = Mock(side_effect=ValueError('not clean'))
        self.app.extensions['desktop_stop_database'] = stop
        self.assertEqual(self.post('stop').status_code, 409)
        self.boundary.stop_callback.assert_not_called()

    def test_source_updates_disabled_even_with_managed_installation(self):
        app = Flask('desktop_updates')
        with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1', 'RIEKE_INSTALLATION_ROOT': '/old/source'}):
            register_app_routes(app)
            boundary = DesktopBoundary(app, port=8766, capability='s' * 48, identity=self.identity)
            client = Client(boundary, Response)
            for suffix, method in (('', 'get'), ('/check', 'post'), ('/stage', 'post'), ('/download', 'get')):
                response = getattr(client, method)('/api/app/updates' + suffix,
                    base_url='http://127.0.0.1:8766', headers=self.headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
                self.assertEqual(response.status_code, 409)
                self.assertTrue(response.json['desktop'])

    def test_owned_services_must_finish_before_root_drain_ack(self):
        services = Mock()
        services.lock = threading.RLock()
        services.database_operation_records.return_value = []
        services.drain.return_value = False
        self.boundary.services = services
        self.assertEqual(self.post('drain').status_code, 409)
        self.assertFalse(self.boundary.drained)
        services.drain.return_value = True
        self.assertEqual(self.post('drain').status_code, 200)

    def test_main_authorization_never_contacts_crashed_project_port(self):
        services = Mock()
        services.records.return_value = [{'port': 8767, 'bound': True, 'recovery_required': True}]
        self.boundary.services = services
        response = self.client.post('/api/desktop/authorize-project', base_url='http://127.0.0.1:8766',
            headers=self.headers, json={'port': 8767}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'}, buffered=True)
        self.assertEqual(response.status_code, 409)
        services.call.assert_not_called()


class DesktopRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.services = DesktopServices(self.state, self.state / 'resources', self.state / 'manifest',
                                        'session', 's' * 48, {'application_version': '1.0'})

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_never_records_capability(self):
        self.assertNotIn('s' * 48, self.services.path.read_text())

    def test_registry_flushes_content_then_directory_before_acknowledging(self):
        from workspace_desktop import _atomic_json
        events = []
        replace = os.replace
        with patch('workspace_desktop.os.fsync', side_effect=lambda fd: events.append('sync')), \
                patch('workspace_desktop.os.replace', side_effect=lambda *args: (events.append('replace'), replace(*args))[-1]):
            _atomic_json(self.services.path, {'version': 1, 'services': []})
        self.assertEqual(events, ['sync', 'replace', 'sync'])
        original = self.services.path.read_bytes()
        with patch('workspace_desktop.os.fsync', side_effect=OSError('durability unavailable')):
            with self.assertRaises(OSError):
                _atomic_json(self.services.path, {'version': 1, 'services': ['unacknowledged']})
        self.assertEqual(self.services.path.read_bytes(), original)

    def test_desktop_excludes_live_source_app_before_database_start(self):
        import fcntl
        path = self.state / '.app-state-session.lock'
        with path.open('a') as source_app:
            fcntl.flock(source_app.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'Another app'):
                acquire_project_session(self.state)
        with acquire_project_session(self.state):
            with self.assertRaisesRegex(ValueError, 'Another app'):
                acquire_project_session(self.state)

    def test_session_lock_cannot_redirect_to_another_project(self):
        outside = self.state / 'outside.lock'
        outside.touch()
        (self.state / '.app-state-session.lock').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            acquire_project_session(self.state)

    def test_crashed_child_is_retained_and_blocks_drain(self):
        process = Mock()
        process.poll.return_value = 1
        record = {'pid': 99999999, 'project_path': str(self.state / 'project'), 'project_uuid': 'abc'}
        self.services.children['project'] = {'record': record, 'process': process}
        self.assertTrue(self.services.records()[0]['recovery_required'])
        self.assertFalse(self.services.drain(.01))
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_zombie_service_still_requires_clean_database_exit_proof(self):
        import psutil
        root = self.state / 'zombie-native'
        database = root / 'database'
        database.mkdir(parents=True)
        owner = database / 'native-owner.json'
        owner.write_text(json.dumps({'project_uuid': 'project', 'clean_shutdown': False}))
        record = {'pid': 123456789, 'project_path': str(root), 'project_uuid': 'project'}
        self.services.path.write_text(json.dumps({'version': 1, 'services': [record]}))
        zombie = Mock(); zombie.status.return_value = psutil.STATUS_ZOMBIE
        with patch('psutil.Process', return_value=zombie):
            with self.assertRaisesRegex(ValueError, 'clean database exit receipt'):
                DesktopServices(self.state, self.state / 'resources', self.state / 'manifest', 'next', 's' * 48, {})
        self.assertEqual(json.loads(self.services.path.read_text())['services'], [record])
        zombie.terminate.assert_not_called(); zombie.kill.assert_not_called()
        owner.write_text(json.dumps({'project_uuid': 'project', 'clean_shutdown': True}))
        with patch('psutil.Process', return_value=zombie):
            recovered = DesktopServices(self.state, self.state / 'resources', self.state / 'manifest', 'next', 's' * 48, {})
        self.assertEqual(recovered.records(), [])

    def test_busy_second_child_resumes_first_and_never_stops_any(self):
        records = [{'pid': 1}, {'pid': 2}]
        self.services.records = Mock(return_value=records)
        calls = []
        def call(record, operation, body, timeout):
            calls.append((record['pid'], operation))
            if record['pid'] == 2 and operation == 'drain':
                raise ValueError('busy')
            return {'ready': True}
        self.services.call = call
        self.assertFalse(self.services.drain(.01))
        self.assertEqual(calls, [(1, 'drain'), (2, 'drain'), (1, 'resume')])

    def test_health_rejects_wrong_release_session_and_pid(self):
        import psutil
        process = psutil.Process()
        record = {'pid': process.pid, 'created_at': process.create_time(), 'executable': str(Path(process.exe()).resolve()),
                  'session_id': 'session', 'project_uuid': 'project', 'project_path': '/project',
                  'application_version': '1.0', 'source_commit': 'source', 'port': 8766, 'bound': True}
        for key in ('pid', 'session_id', 'application_version', 'source_commit', 'project_path', 'project_uuid'):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps({**record, key: 'different'}).encode()
            with patch('workspace_desktop.urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'health identity'):
                    self.services.call(record, 'health')

    def test_no_capability_is_sent_before_private_child_bind_receipt(self):
        with patch('workspace_desktop.urlopen') as send:
            with self.assertRaisesRegex(ValueError, 'binding'):
                self.services.call({'port': 8766, 'bound': False}, 'health')
            send.assert_not_called()

    def test_prior_living_exact_process_requires_recovery(self):
        import psutil
        process = psutil.Process()
        record = {'pid': process.pid, 'created_at': process.create_time(), 'executable': str(Path(process.exe()).resolve())}
        self.services.path.write_text(json.dumps({'version': 1, 'services': [record]}))
        with self.assertRaisesRegex(ValueError, 'still alive'):
            DesktopServices(self.state, self.state / 'resources', self.state / 'manifest',
                            'new-session', 's' * 48, {})

    def test_transient_database_ack_requires_same_instance_and_absent_runtime(self):
        root = self.state / 'project'
        database = root / 'database'
        database.mkdir(parents=True)
        record = {'project_path': str(root), 'project_uuid': 'project',
                  'instance_uuid': 'instance', 'phase': 'running', 'operation_id': 'operation'}
        self.services.database_operations['operation'] = record
        owner = database / 'native-owner.json'
        owner.write_text(json.dumps({'project_uuid': 'project', 'instance_uuid': 'different', 'clean_shutdown': True}))
        with self.assertRaisesRegex(ValueError, 'clean shutdown'):
            self.services.finish_database_operation('operation')
        owner.write_text(json.dumps({'project_uuid': 'project', 'instance_uuid': 'instance', 'clean_shutdown': True}))
        runtime = database / 'native-runtime.json'
        runtime.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'clean shutdown'):
            self.services.finish_database_operation('operation')
        self.assertEqual(self.services.database_operation_records(), [record])
        runtime.unlink()
        # A running admission cannot disappear just because the pre-start owner
        # was clean. Only the responsible operation's finish acknowledgement can.
        self.assertEqual(self.services.database_operation_records(), [record])
        self.services.finish_database_operation('operation')
        self.assertEqual(self.services.database_operation_records(), [])

    def test_failed_transfer_persists_until_same_native_instance_is_clean(self):
        root = self.state / 'project'
        database = root / 'database'
        database.mkdir(parents=True)
        record = {'project_path': str(root), 'project_uuid': 'project',
                  'instance_uuid': 'instance', 'phase': 'running', 'operation_id': 'operation'}
        self.services.database_operations['operation'] = record
        self.services.finish_database_operation('operation', failed=True)
        self.assertEqual(json.loads(self.services.path.read_text())['database_operations'][0]['phase'], 'failed_shutdown')
        with self.assertRaisesRegex(ValueError, 'clean exit receipt'):
            DesktopServices(self.state, self.state / 'resources', self.state / 'manifest', 'next', 's' * 48, {})
        (database / 'native-owner.json').write_text(json.dumps({'project_uuid': 'project', 'instance_uuid': 'instance', 'clean_shutdown': True}))
        self.assertEqual(self.services.database_operation_records(), [])

    def test_legacy_preflight_rejects_before_child_or_registry_changes(self):
        root = self.state / 'legacy'
        root.mkdir()
        (root / 'catalog.json').write_text(json.dumps({'connection': {'credential_provider': {'kind': 'docker-container-env'}}}))
        with patch('workspace_desktop.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'desktop copy'):
                self.services.open(root, 'project', None, 1)
            spawn.assert_not_called()
        self.assertEqual(self.services.children, {})

    def test_exited_legacy_preflight_does_not_require_native_recovery(self):
        root = self.state / 'legacy'
        root.mkdir()
        identity = '11111111-1111-4111-8111-111111111111'
        (root / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1, 'project_uuid': identity}))
        (root / 'catalog.json').write_text(json.dumps({'format': 'recording-catalog-reference', 'version': 1, 'project_uuid': identity, 'connection': {'credential_provider': {'kind': 'docker-container-env', 'container': 'existing-source'}}}))
        child = Mock()
        child.poll.return_value = 1
        self.services.children['legacy'] = {'record': {'project_path': str(root), 'project_uuid': identity, 'bound': False}, 'process': child}
        self.assertEqual(self.services.records(), [])
        child.kill.assert_not_called()

    def test_dead_legacy_record_with_any_ambiguous_native_evidence_stays_blocked(self):
        identity = '11111111-1111-4111-8111-111111111111'
        for evidence in ('native-owner.json', 'native-credentials.json', 'native-runtime.json', 'service.json', 'mysql/ibdata1', 'managed_database', 'malformed_catalog'):
            with self.subTest(evidence=evidence):
                root = self.state / evidence.replace('/', '-')
                (root / 'database').mkdir(parents=True)
                (root / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1, 'project_uuid': identity}))
                catalog = {'format': 'recording-catalog-reference', 'version': 1, 'project_uuid': identity, 'connection': {'credential_provider': {'kind': 'docker-container-env', 'container': 'existing-source'}}}
                if evidence == 'managed_database': catalog['managed_database'] = {}
                if evidence == 'malformed_catalog': catalog.pop('format')
                (root / 'catalog.json').write_text(json.dumps(catalog))
                if evidence not in {'managed_database', 'malformed_catalog'}:
                    file = root / 'database' / evidence
                    file.parent.mkdir(exist_ok=True)
                    file.write_text('{}')
                child = Mock(); child.poll.return_value = 1
                self.services.children = {'legacy': {'record': {'project_path': str(root), 'project_uuid': identity, 'bound': False}, 'process': child}}
                self.assertTrue(self.services.records()[0]['recovery_required'])
                self.assertFalse(self.services.drain(.01))
                child.kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
