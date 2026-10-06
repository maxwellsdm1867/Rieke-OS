"""HTTP recovery policy; scheduler doubles do not qualify native persistence."""
import os
import unittest
from unittest.mock import patch

from flask import Flask, jsonify

from disco.recovery import register_mutation_recovery


class RecoveryScheduler:
    """Disposable recovery adapter, with observable backup attempts."""
    def __init__(self):
        self.flushes = 0
        self.failure = None
        self.backup = {'status': 'pending', 'requested_sequence': 7}

    def status(self):
        return dict(self.backup)

    def flush(self):
        self.flushes += 1
        if self.failure:
            self.backup = {'status': 'degraded', 'requested_sequence': 7}
            raise self.failure
        self.backup = {'status': 'current', 'requested_sequence': 7}


class MutationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.testing = True
        self.scheduler = RecoveryScheduler()
        self.desktop = False
        register_mutation_recovery(self.app, self.scheduler, desktop_mode=lambda: self.desktop)
        self.client = self.app.test_client()

    def route(self, endpoint, *, path=None, status=200, payload=None):
        path = path or '/api/' + endpoint
        value = payload if payload is not None else {'changed': False, 'replayed': True}
        def respond():
            response = jsonify(value)
            response.status_code = status
            response.headers['X-Receipt'] = 'retained'
            return response
        self.app.add_url_rule(path, endpoint, respond,
                              methods=['GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE'])
        return path

    def test_annotation_ack_preserves_receipt_and_reports_pending_backup_without_flush(self):
        for endpoint in ('annotation_update', 'annotation_undo'):
            self.route(endpoint, payload={'changed': 2, 'event_uuid': 'exact-event', 'tags': ['λ']})
        for endpoint in ('annotation_update', 'annotation_undo'):
            with self.subTest(endpoint=endpoint):
                response = self.client.post('/api/' + endpoint)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {
                    'changed': 2, 'event_uuid': 'exact-event', 'tags': ['λ'],
                    'persistence': {'database': 'committed', 'backup': {
                        'status': 'pending', 'requested_sequence': 7}}})
                self.assertEqual(response.headers['X-Receipt'], 'retained')
                self.assertEqual(self.scheduler.flushes, 0)

    def test_successful_unknown_writes_flush_even_noop_or_replay_receipts(self):
        self.route('future_write')
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                before = self.scheduler.flushes
                response = self.client.open('/api/future_write', method=method)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {'changed': False, 'replayed': True})
                self.assertEqual(response.headers['X-Receipt'], 'retained')
                self.assertEqual(self.scheduler.flushes, before + 1)

    def test_failed_recovery_reports_saved_without_replacing_database_outcome(self):
        self.route('future_write')
        self.scheduler.failure = OSError('disk full')
        with self.assertLogs(self.app.logger, level='ERROR') as logged:
            response = self.client.post('/api/future_write')
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.get_json(), {
            'error': 'Saved to the database, but the app-state backup failed. '
                     'Check project disk space and permissions before closing the app.',
            'saved': True})
        self.assertIn('App state was saved to SQL but its recovery snapshot failed', logged.output[0])
        self.assertEqual(self.scheduler.flushes, 1)

    def test_group_failure_retains_exact_operation_and_current_backup_status(self):
        for endpoint in ('group_annotation_apply', 'group_annotation_undo'):
            self.route(endpoint)
        self.scheduler.failure = OSError('disk full')
        for endpoint, operation in (
                ('group_annotation_apply', '00000000-0000-4000-8000-000000000071'),
                ('group_annotation_undo', '00000000-0000-4000-8000-000000000072')):
            with self.subTest(endpoint=endpoint):
                with self.assertLogs(self.app.logger, level='ERROR'):
                    response = self.client.post('/api/' + endpoint, json={'operation_uuid': operation})
                self.assertEqual(response.status_code, 507)
                self.assertEqual(response.get_json(), {
                    'error': 'Saved to the database, but the app-state backup failed. '
                             'Check project disk space and permissions before closing the app.',
                    'saved': True, 'code': 'recovery_unconfirmed', 'operation_uuid': operation,
                    'persistence': {'database': 'committed', 'backup': {
                        'status': 'degraded', 'requested_sequence': 7}}})

    def test_read_posts_skip_backup_but_same_endpoints_with_other_write_verbs_flush(self):
        endpoints = (
            'explorer_preview', 'explorer_summaries', 'explorer_summary_cancel',
            'explorer_query_page', 'tree_page', 'matching_epochs', 'annotation_batch_read',
            'curation_batch_read', 'tag_import_preview', 'preview_source_propagation',
            'resolve_search_preset', 'compare_protocol_revision', 'workbench_preview',
            'workbench_tree_page', 'workbench_candidate_summary', 'workbench_selection_summary', 'group_annotation_preview',
            'group_annotation_preview_release')
        for endpoint in endpoints:
            self.route(endpoint)
        for endpoint in endpoints:
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                with self.subTest(endpoint=endpoint, method=method):
                    before = self.scheduler.flushes
                    response = self.client.open('/api/' + endpoint, method=method)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json(), {'changed': False, 'replayed': True})
                    self.assertEqual(self.scheduler.flushes, before + (method != 'POST'))

    def test_desktop_control_reads_mode_each_request_and_requires_exact_path_prefix(self):
        self.route('desktop', path='/api/desktop/control')
        self.route('near_desktop', path='/api/desktopish/control')
        self.route('desktop_root', path='/api/desktop')
        for enabled, path, expected_flushes in (
                (True, '/api/desktop/control', 0),
                (False, '/api/desktop/control', 1),
                (True, '/api/desktop/control', 1),
                (True, '/api/desktopish/control', 2),
                (True, '/api/desktop', 3)):
            with self.subTest(enabled=enabled, path=path):
                self.desktop = enabled
                self.assertEqual(self.client.post(path).status_code, 200)
                self.assertEqual(self.scheduler.flushes, expected_flushes)

    def test_close_and_unmount_skip_only_the_exact_paths(self):
        for endpoint, path in (
                ('close', '/api/project/close'), ('unmount', '/api/projects/unmount'),
                ('near_close', '/api/project/close/extra')):
            self.route(endpoint, path=path)
        for path in ('/api/project/close', '/api/projects/unmount'):
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.client.open(path, method=method).status_code, 200)
                    self.assertEqual(self.scheduler.flushes, 0)
        self.assertEqual(self.client.post('/api/project/close/extra').status_code, 200)
        self.assertEqual(self.scheduler.flushes, 1)


    def test_only_successful_write_statuses_flush_and_other_methods_preserve_responses(self):
        for status in (200, 201, 202, 204, 299, 300, 400, 409, 500, 507):
            self.route('status_' + str(status), status=status)
        for status in (200, 201, 202, 204, 299, 300, 400, 409, 500, 507):
            for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'GET', 'HEAD', 'OPTIONS'):
                with self.subTest(status=status, method=method):
                    before = self.scheduler.flushes
                    response = self.client.open('/api/status_' + str(status), method=method)
                    self.assertEqual(response.status_code, status)
                    expected = int(method in ('POST', 'PUT', 'PATCH', 'DELETE') and status < 300)
                    self.assertEqual(self.scheduler.flushes, before + expected)
                    self.assertEqual(response.headers['X-Receipt'], 'retained')

    def test_annotation_branch_precedes_method_and_desktop_exclusions(self):
        self.route('annotation_update', path='/api/desktop/annotations')
        self.desktop = True
        for method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                response = self.client.open('/api/desktop/annotations', method=method)
                self.assertEqual(response.get_json()['persistence']['database'], 'committed')
                self.assertEqual(self.scheduler.flushes, 0)

    def test_annotation_failure_does_not_claim_commit_or_recovery(self):
        self.route('annotation_update', status=409, payload={'error': 'stale revision'})
        response = self.client.post('/api/annotation_update')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json(), {'error': 'stale revision'})
        self.assertEqual(self.scheduler.flushes, 0)

    def test_annotation_status_error_keeps_existing_exception_propagation(self):
        class UnavailableStatus(RecoveryScheduler):
            def status(self):
                raise RuntimeError('status unavailable')
        app = Flask(__name__)
        app.testing = True
        scheduler = UnavailableStatus()
        app.add_url_rule('/api/annotations', 'annotation_update', lambda: {'changed': 1}, methods=['POST'])
        register_mutation_recovery(app, scheduler, desktop_mode=lambda: False)
        with self.assertRaisesRegex(RuntimeError, 'status unavailable'):
            app.test_client().post('/api/annotations')
        self.assertEqual(scheduler.flushes, 0)


class ApplicationRecoveryRegistrationTests(unittest.TestCase):
    """Real create_app wiring, using the existing disposable group HTTP fixture."""
    def setUp(self):
        from test_workspace_group_recovery import GroupRecoveryHookTests
        self.case = GroupRecoveryHookTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_each_write_checkpoints_once_and_failure_keeps_security_headers(self):
        body = {'operation_uuid': '00000000-0000-4000-8000-000000000081'}
        response = self.case.client.post('/api/annotations/group', json=body, headers=self.case.fixture.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.case.save.call_count, 1, 'Each request must checkpoint exactly once')
        self.case.save.side_effect = OSError('disk full')
        with self.assertLogs(self.case.app.logger, level='ERROR'):
            response = self.case.client.post('/api/annotations/group', json=body, headers=self.case.fixture.headers)
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.get_json()['operation_uuid'], body['operation_uuid'])
        self.assertEqual(self.case.save.call_count, 2)
        self.assertEqual(self.case.writes, 1, 'Exact replay must not repeat the command write')
        # Flask runs after_request callbacks in reverse registration order. The
        # replacement 507 must still pass through the existing headers callback.
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertIn('Accept-Encoding', response.vary)

    def test_application_environment_is_read_again_for_each_request(self):
        self.case.app.add_url_rule('/api/desktop/test-recovery', 'test_desktop_recovery',
                                   lambda: {'ok': True}, methods=['POST'])
        for mode, count in (('1', 0), ('0', 1), ('1', 1)):
            with self.subTest(mode=mode), patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': mode}):
                response = self.case.client.post('/api/desktop/test-recovery', headers=self.case.fixture.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.case.save.call_count, count)


if __name__ == '__main__':
    unittest.main()
