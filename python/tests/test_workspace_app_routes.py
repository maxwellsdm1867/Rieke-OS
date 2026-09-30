"""Local update checks and transfer job lifecycle without touching user data."""
import threading
import os
import time
import types
import unittest
from unittest.mock import Mock, patch
from flask import Flask
from workspace_app_routes import register_app_routes


class AppRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        register_app_routes(app)
        self.client = app.test_client()
        self.headers = {'X-Workspace-Request': '1'}

    def post(self, path, body, **kwargs):
        return self.client.post(path, json=body, headers=self.headers, **kwargs)

    def test_update_check_rejects_foreign_origin_and_remote_clients(self):
        path = '/api/app/updates/check'
        self.assertEqual(self.client.post(path, json={}).status_code, 403)
        self.assertEqual(self.client.post(path, json={}, headers={**self.headers, 'Origin': 'https://evil.test'}).status_code, 403)
        self.assertEqual(self.post(path, {}, environ_overrides={'REMOTE_ADDR': '192.0.2.1'}).status_code, 403)
        self.assertEqual(self.post(path, {'url': 'https://evil.test'}).status_code, 400)

    def test_status_and_check_distinguish_missing_releases(self):
        module = types.SimpleNamespace(installation_status=lambda **kw: {'state': 'unchecked'},
                                      check_for_updates=lambda **kw: {'state': 'unavailable'})
        with patch.dict('sys.modules', workspace_updates=module):
            self.assertEqual(self.client.get('/api/app/updates').json['state'], 'unchecked')
            self.assertEqual(self.post('/api/app/updates/check', {}).json['state'], 'unavailable')

    def test_manual_retry_bypasses_cache_and_install_requires_capability(self):
        from unittest.mock import Mock
        check = Mock(return_value={'state': 'error'})
        module = types.SimpleNamespace(installation_status=lambda **kw: {'can_stage': False},
                                      check_for_updates=check, stage_release=Mock())
        with patch.dict('sys.modules', workspace_updates=module):
            response = self.post('/api/app/updates/check', {'force': True})
            self.assertTrue(check.call_args.kwargs['force'])
            self.assertEqual(self.post('/api/app/updates/stage', {}).status_code, 403)
            response = self.client.post('/api/app/updates/stage', json={}, headers={**self.headers,
                'X-Rieke-Update-Token': response.json['update_token']})
            self.assertEqual(response.status_code, 409)
            module.stage_release.assert_not_called()

    def test_managed_check_downloads_automatically_once_without_blocking(self):
        finish = threading.Event()
        started = threading.Event()
        def stage(**kwargs):
            started.set()
            finish.wait(3)
            return {'version': '0.2.0', 'state': 'staged'}
        stage_mock = Mock(side_effect=lambda *args, **kwargs: stage(**kwargs))
        status = {'state': 'update_available', 'available': '0.2.0', 'can_stage': True}
        module = types.SimpleNamespace(check_for_updates=Mock(return_value=status), stage_release=stage_mock)
        with patch.dict('sys.modules', workspace_updates=module), patch.dict(os.environ, RIEKE_INSTALLATION_ROOT='/installation'):
            try:
                response = self.post('/api/app/updates/check', {})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(started.wait(1))
                self.assertEqual(response.json['download']['state'], 'running')
                self.post('/api/app/updates/check', {})
                self.assertEqual(stage_mock.call_count, 1)
            finally:
                finish.set()
            for _ in range(100):
                result = self.client.get('/api/app/updates/download').json
                if result['state'] != 'running': break
                time.sleep(.01)
            self.assertEqual(result['state'], 'complete')
            self.post('/api/app/updates/check', {})
            self.assertEqual(stage_mock.call_count, 1)

    def test_automatic_download_requires_managed_trust_and_fresh_unstaged_release(self):
        base = {'state': 'update_available', 'available': '0.2.0', 'can_stage': True}
        module = types.SimpleNamespace(check_for_updates=Mock(), stage_release=Mock())
        with patch.dict('sys.modules', workspace_updates=module), patch.dict(os.environ, RIEKE_INSTALLATION_ROOT='/installation'):
            for status in ({**base, 'can_stage': False}, {**base, 'check_error': 'Offline'},
                           {**base, 'staged_version': '0.2.0'}, {**base, 'state': 'up_to_date'}):
                module.check_for_updates.return_value = status
                self.assertEqual(self.post('/api/app/updates/check', {}).status_code, 200)
            module.stage_release.assert_not_called()
        with patch.dict('sys.modules', workspace_updates=module), patch.dict(os.environ):
            os.environ.pop('RIEKE_INSTALLATION_ROOT', None)
            module.check_for_updates.return_value = base
            self.post('/api/app/updates/check', {})
            module.stage_release.assert_not_called()

    def test_transfer_serializes_jobs_and_reports_success_only_after_completion(self):
        release = threading.Event()
        module = types.SimpleNamespace(prepare_project=lambda *args: (release.wait(3), {'verified': True})[1], restore_project=lambda *args: {})
        with patch.dict('sys.modules', workspace_portability=module):
            body = {'directory': '/source', 'destination': '/destination'}
            response = self.post('/api/projects/prepare-transfer', body)
            self.assertEqual(response.status_code, 202)
            path = '/api/projects/transfers/' + response.json['job_id']
            try:
                self.assertEqual(self.client.get(path).json['state'], 'running')
                self.assertEqual(self.post('/api/projects/restore-transfer', body).status_code, 409)
            finally:
                release.set()
            for _ in range(100):
                result = self.client.get(path).json
                if result['state'] != 'running': break
                time.sleep(.01)
            self.assertEqual(result['state'], 'complete')
            self.assertTrue(result['result']['verified'])

    def test_relocation_requires_local_explicit_paths_and_reports_destination(self):
        move = Mock(return_value={'project_uuid': 'fixture', 'directory': '/preferred/study',
            'previous_directory': '/received/study', 'moved': True})
        module = types.SimpleNamespace(relocate_project=move)
        path = '/api/projects/relocate'
        body = {'directory': '/received/study', 'destination': '/preferred/study'}
        with patch.dict('sys.modules', workspace_portability=module), patch('workspace_startup_registry.remember_project_path') as remember:
            self.assertEqual(self.client.post(path, json=body).status_code, 403)
            self.assertEqual(self.client.post(path, json=body, headers={**self.headers, 'Origin': 'https://foreign.test'}).status_code, 403)
            self.assertEqual(self.post(path, body, environ_overrides={'REMOTE_ADDR': '192.0.2.1'}).status_code, 403)
            for invalid in ({}, {'directory': 'relative', 'destination': '/preferred/study'},
                            {**body, 'overwrite': True}, {**body, 'destination': 2}):
                self.assertEqual(self.post(path, invalid).status_code, 400)
            move.assert_not_called()
            result = self.post(path, body)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['directory'], '/preferred/study')
            self.assertTrue(result.json['moved'])
            move.assert_called_once_with('/received/study', '/preferred/study')
            remember.assert_called_once_with('/preferred/study', previous_directory='/received/study')

    def test_verified_restore_registers_exact_destination(self):
        restored = {'directory': '/independent/restored study', 'verified': True}
        module = types.SimpleNamespace(restore_project=Mock(return_value=restored), prepare_project=Mock())
        with patch.dict('sys.modules', workspace_portability=module), patch('workspace_startup_registry.remember_project_path') as remember:
            response = self.post('/api/projects/restore-transfer', {'directory': '/received/copy',
                'destination': '/independent/restored study'})
            path = '/api/projects/transfers/' + response.json['job_id']
            for _ in range(100):
                result = self.client.get(path).json
                if result['state'] != 'running':
                    break
                time.sleep(.01)
            self.assertEqual(result['state'], 'complete')
            remember.assert_called_once_with('/independent/restored study')

    def test_relocation_failure_is_actionable_and_never_reports_success(self):
        module = types.SimpleNamespace(relocate_project=Mock(side_effect=ValueError('Close the project before moving its folder')))
        with patch.dict('sys.modules', workspace_portability=module):
            result = self.post('/api/projects/relocate', {'directory': '/source', 'destination': '/destination'})
            self.assertEqual(result.status_code, 400)
            self.assertIn('Close the project', result.json['error'])
            self.assertNotIn('moved', result.json)

    def test_completed_restore_is_reported_when_local_index_cannot_save(self):
        restored = {'directory': '/completed/restored study', 'verified': True}
        module = types.SimpleNamespace(restore_project=Mock(return_value=restored), prepare_project=Mock())
        with patch.dict('sys.modules', workspace_portability=module), patch('workspace_startup_registry.remember_project_path', side_effect=OSError('Profile disk is full')):
            response = self.post('/api/projects/restore-transfer', {'directory': '/received/copy',
                'destination': restored['directory']})
            path = '/api/projects/transfers/' + response.json['job_id']
            for _ in range(100):
                result = self.client.get(path).json
                if result['state'] != 'running':
                    break
                time.sleep(.01)
        self.assertEqual(result['state'], 'complete')
        self.assertTrue(result['result']['verified'])
        self.assertIn('registry_warning', result['result'])

    def test_transfer_failure_and_invalid_paths_never_report_success(self):
        def fail(*args): raise ValueError('Stop the project service first')
        module = types.SimpleNamespace(prepare_project=fail, restore_project=fail)
        with patch.dict('sys.modules', workspace_portability=module):
            self.assertEqual(self.post('/api/projects/prepare-transfer', {'directory': 'relative', 'destination': '/output'}).status_code, 400)
            response = self.post('/api/projects/prepare-transfer', {'directory': '/source', 'destination': '/output'})
            for _ in range(100):
                result = self.client.get('/api/projects/transfers/' + response.json['job_id']).json
                if result['state'] != 'running': break
                time.sleep(.01)
            self.assertEqual(result['state'], 'failed')
            self.assertIn('Stop the project', result['error'])


if __name__ == '__main__': unittest.main()
