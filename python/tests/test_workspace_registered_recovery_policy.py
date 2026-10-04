"""Real registration/recovery linkage, with disposable DB and response doubles.

Handlers are replaced after production URL registration, leaving its map intact. These
tests establish HTTP completion policy, not scientific transactions or replay.
Native-schema composition/header ordering has separate existing coverage in
test_workspace_mutation_outcomes.ApplicationRecoveryRegistrationTests.
"""
from functools import partial
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from flask import jsonify

import test_workspace_api as api_fixture
from workspace_api import create_app
from workspace_lifecycle import register_project_lifecycle
from workspace_mutation_outcomes import register_mutation_recovery


# Literal registration expectations, independent of the production exemption set.
READ_POSTS = (
    ('explorer_preview', '/api/explore/preview'),
    ('explorer_summaries', '/api/explore/summaries'),
    ('explorer_summary_cancel', '/api/explore/summaries/<request_id>/cancel'),
    ('explorer_query_page', '/api/explore/page'),
    ('tree_page', '/api/tree-pages'),
    ('matching_epochs', '/api/explore/epochs'),
    ('annotation_batch_read', '/api/annotations/read'),
    ('curation_batch_read', '/api/protocols/<protocol_uuid>/curation/read'),
    ('tag_import_preview', '/api/annotations/import/preview'),
    ('preview_source_propagation', '/api/data-stores/<source_sha256>/propagation-preview'),
    ('resolve_search_preset', '/api/search-presets/resolve'),
    ('compare_protocol_revision', '/api/explore/revisions/<revision_uuid>/compare-to-protocol'),
    ('workbench_preview', '/api/protocols/<protocol>/workbench/candidates/<revision>/preview'),
    ('workbench_tree_page', '/api/protocols/<protocol>/workbench/candidates/<revision>/tree/page'),
    ('workbench_candidate_summary', '/api/protocols/<protocol>/workbench/candidates/<revision>/summary'),
    ('group_annotation_preview', '/api/annotations/group-preview'),
    ('group_annotation_preview_release', '/api/annotations/group-preview-release'),
)
ANNOTATIONS = (
    ('annotation_update', '/api/annotations'),
    ('annotation_undo', '/api/annotations/undo'),
)
GROUPS = (
    ('group_annotation_apply', '/api/annotations/group'),
    ('group_annotation_undo', '/api/annotations/group/<operation_uuid>/undo'),
)
# These are representative defaults, not an exhaustive application command list.
DEFAULT_WRITES = (
    ('run_search_query', '/api/explore/run', 'POST'),
    ('annotation_profile_create', '/api/annotation-profiles', 'POST'),
    ('annotation_profile_select', '/api/annotation-profiles/selected', 'POST'),
    ('curate', '/api/protocols/<protocol_uuid>/curation', 'POST'),
    ('tag_import_apply', '/api/annotations/import/apply', 'POST'),
    ('workbench_patch', '/api/protocols/<protocol>/workbench/candidates/<revision>/draft', 'PATCH'),
    ('workbench_accept', '/api/protocols/<protocol>/workbench/candidates/<revision>/accept', 'POST'),
    ('workbench_prepare', '/api/protocols/<protocol>/workbench/prepare', 'POST'),
    ('save_preferences', '/api/project-preferences', 'PUT'),
    ('export', '/api/protocols/<protocol_uuid>/exports', 'POST'),
    ('candidate_export', '/api/explore/revisions/<revision_uuid>/exports', 'POST'),
    ('workbench_incoming_export', '/api/protocols/<protocol>/workbench/candidates/<revision>/exports', 'POST'),
    ('workbench_accept_export', '/api/protocols/<protocol>/workbench/receipts/<operation>/exports', 'POST'),
)


class Scheduler:
    def __init__(self):
        self.flushes = 0
        self.fail = False

    def status(self):
        return {'status': 'degraded' if self.fail else 'pending', 'requested_sequence': 7}

    def flush(self):
        self.flushes += 1
        if self.fail:
            raise OSError('disposable backup failure')


class RegisteredRecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        env = patch.dict(os.environ, {
            'RIEKE_PREFERENCES_DIR': str(Path(state.name) / 'preferences'),
            'RIEKE_PROJECT_INDEX': str(Path(state.name) / 'project-index.json'),
            'RIEKE_DESKTOP_MODE': '0',
        })
        env.start()
        self.addCleanup(env.stop)
        self.fixture = api_fixture.WorkspaceAPITests()
        self.addCleanup(self.fixture.doCleanups)
        # Reuse the existing tables/project fixture, retaining every production
        # registration function, including group annotations. A harmless shared
        # store enables the real conditional annotation/tag registrations.
        with patch.object(api_fixture, 'create_app', partial(create_app, shared_annotations=Mock())):
            self.fixture.setUp()
        self.app = self.fixture.app
        self.assertNotIn('backup_scheduler', self.app.extensions)
        # No native schema or scheduler thread is constructed. Install the real
        # completion adapter once; separate tests cover native create_app wiring.
        self.scheduler = Scheduler()
        register_mutation_recovery(self.app, self.scheduler, desktop_mode=lambda: False)
        # A different verb can resolve to an overlapping dynamic rule. Keep all
        # handler bodies inert, including unexpected matches, before dispatch.
        for endpoint in self.app.view_functions:
            self.respond(endpoint)
        self.client = self.app.test_client()

    def registered(self, endpoint, path, methods=('POST',)):
        rules = [rule for rule in self.app.url_map.iter_rules() if rule.endpoint == endpoint]
        self.assertIn((path, frozenset(methods)), {
            (rule.rule, frozenset(rule.methods - {'HEAD', 'OPTIONS'})) for rule in rules
        }, f'Production registration drift: {endpoint} {path}')
        rule = next(rule for rule in rules if rule.rule == path)
        values = {name: '00000000-0000-4000-8000-000000000071' for name in rule.arguments}
        # Use the asserted literal rule rather than choosing a different alias.
        for name, value in values.items():
            path = path.replace('<' + name + '>', value)
        return path

    def respond(self, endpoint, status=200):
        def neutral_response(**_route_arguments):
            response = jsonify(changed=False, event_uuid='retained-event')
            response.status_code = status
            response.headers['X-Receipt'] = 'retained'
            return response
        self.app.view_functions[endpoint] = neutral_response

    def send(self, path, method='POST', **kwargs):
        return self.client.open(path, method=method, headers=self.fixture.headers, **kwargs)

    def test_every_registered_read_post_skips_backup(self):
        for endpoint, rule in READ_POSTS:
            with self.subTest(endpoint=endpoint):
                path = self.registered(endpoint, rule)
                self.respond(endpoint, 202 if endpoint == 'explorer_summaries' else 200)
                before = self.scheduler.flushes
                response = self.send(path, json={})
                self.assertEqual(response.status_code, 202 if endpoint == 'explorer_summaries' else 200)
                self.assertEqual(response.get_json(), {'changed': False, 'event_uuid': 'retained-event'})
                self.assertEqual(self.scheduler.flushes, before)

    def test_read_post_put_routing_includes_overlapping_preset_update(self):
        for endpoint, rule in READ_POSTS:
            with self.subTest(endpoint=endpoint):
                path = self.registered(endpoint, rule)
                before = self.scheduler.flushes
                response = self.send(path, method='PUT', json={})
                if endpoint == 'resolve_search_preset':
                    # The literal POST path is also a dynamic PUT preset path.
                    # This tests routing policy, not the real handler's UUID validation.
                    matched, values = self.app.url_map.bind('localhost').match(path, method='PUT')
                    self.assertEqual((matched, values), ('search_presets', {'preset_uuid': 'resolve'}))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.scheduler.flushes, before + 1)
                else:
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(self.scheduler.flushes, before)

    def test_registered_annotations_report_pending_backup_without_flush(self):
        for endpoint, rule in ANNOTATIONS:
            with self.subTest(endpoint=endpoint):
                path = self.registered(endpoint, rule)
                self.respond(endpoint)
                response = self.send(path, json={})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {
                    'changed': False, 'event_uuid': 'retained-event',
                    'persistence': {'database': 'committed', 'backup': {
                        'status': 'pending', 'requested_sequence': 7}},
                })
                self.assertEqual(response.headers['X-Receipt'], 'retained')
                self.assertEqual(self.scheduler.flushes, 0)

    def test_registered_default_writes_flush_once_even_for_no_change(self):
        rows = DEFAULT_WRITES + tuple((endpoint, rule, 'POST') for endpoint, rule in GROUPS)
        for endpoint, rule, method in rows:
            with self.subTest(endpoint=endpoint):
                path = self.registered(endpoint, rule, (method,))
                status = 201 if endpoint == 'annotation_profile_create' else 200
                self.respond(endpoint, status)
                before = self.scheduler.flushes
                response = self.send(path, method=method, json={})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.get_json(), {'changed': False, 'event_uuid': 'retained-event'})
                self.assertEqual(self.scheduler.flushes, before + 1)
                self.assertEqual(response.headers['X-Receipt'], 'retained')

    def test_mixed_method_and_alias_registration_preserves_method_specific_flush(self):
        for rule, methods in (
                ('/api/search-presets', ('GET', 'POST')),
                ('/api/search-presets/<preset_uuid>', ('GET', 'PUT'))):
            path = self.registered('search_presets', rule, methods)
            self.respond('search_presets')
            for method in methods:
                with self.subTest(rule=rule, method=method):
                    before = self.scheduler.flushes
                    self.assertEqual(self.send(path, method=method, json={}).status_code, 200)
                    self.assertEqual(self.scheduler.flushes, before + int(method != 'GET'))

    def test_registered_group_undo_failure_uses_inverse_body_uuid_not_original_path_uuid(self):
        endpoint, rule = GROUPS[1]
        path = self.registered(endpoint, rule)
        self.respond(endpoint)
        self.scheduler.fail = True
        inverse = '00000000-0000-4000-8000-000000000072'
        self.assertNotIn(inverse, path)
        with self.assertLogs(self.app.logger, level='ERROR'):
            response = self.send(path, json={'operation_uuid': inverse})
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.get_json(), {
            'error': 'Saved to the database, but the app-state backup failed. '
                     'Check project disk space and permissions before closing the app.',
            'saved': True, 'code': 'recovery_unconfirmed', 'operation_uuid': inverse,
            'persistence': {'database': 'committed', 'backup': {
                'status': 'degraded', 'requested_sequence': 7}},
        })
        self.assertEqual(self.scheduler.flushes, 1)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_real_close_and_unmount_registrations_skip_even_with_query_strings(self):
        # Register source-mode close without constructing native project services.
        # Replace its handler before dispatch: no draining/shutdown is executed.
        register_project_lifecycle(self.app, busy=lambda: False, stop_database=Mock())
        for endpoint, rule in (
                ('close_project', '/api/project/close'),
                ('project_unmount', '/api/projects/unmount')):
            path = self.registered(endpoint, rule)
            self.respond(endpoint, 202)
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.send(path + '?policy_probe=1', json={}).status_code, 202)
                self.assertEqual(self.scheduler.flushes, 0)


if __name__ == '__main__':
    unittest.main()
