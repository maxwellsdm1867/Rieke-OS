"""Source-registration lifecycle and history tests using isolated SQL doubles."""
import copy
import datetime as dt
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

if __package__:
    from . import test_workspace_api as api_tests
else:
    import test_workspace_api as api_tests


class DataStoreTests(unittest.TestCase):
    def setUp(self):
        self.case = api_tests.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.client, self.service = self.case.client, self.case.service
        self.headers = self.case.headers
        self.source = 'a' * 64
        self.base = '/api/data-stores/' + self.source
        self.path = Path(self.service.sources[0]['source_path'])
        self.path.write_bytes(b'disposable test file, never parsed')
        os.utime(self.path, (1600000000, 1600000000))
        self.service.manifests[self.source].update(source_size=self.path.stat().st_size,
            validated_at='2026-09-27T10:00:00+00:00', parser_path='/fixture/parser.py', parser_sha256='c' * 64,
            adapter_version=1, adapter_sha256='d' * 64, metadata_sha256='e' * 64, status='validated')

    def event(self, action, payload, project=None):
        identity = str(uuid.uuid4())
        self.case.events.insert1({'event_uuid': identity,
            'project_uuid': project or self.service.project['project_uuid'],
            'occurred_at': dt.datetime(2026, 9, 27, 11, 0), 'actor': 'fixture', 'action': action, 'payload': payload})
        return identity

    def change(self, action, version, **extra):
        return self.client.post(self.base + '/state', json={
            'action': action, 'expected_version': version, 'reason': 'Fixture lifecycle check', **extra}, headers=self.headers)

    def test_inventory_is_metadata_only_lazy_and_import_time_is_not_validation_or_mtime(self):
        with patch.object(self.service, 'query_result', side_effect=AssertionError('No eager protocol joins')), \
             patch.object(self.case.store, 'export_memberships', side_effect=AssertionError('No eager recipe joins')), \
             patch('h5py.File', side_effect=AssertionError('No trace reads')):
            row = self.client.get('/api/data-stores').get_json()['data_stores'][0]
        self.assertFalse(row['connections_loaded'])
        self.assertIsNone(row['counts']['exports'])
        self.assertIsNone(row['counts']['protocol_workspaces'])
        self.assertEqual((row['counts']['epochs'], row['counts']['cells']), (2, 2))
        self.assertEqual(row['file_status'], 'available')
        self.assertIsNone(row['imported_at'])
        self.assertEqual(row['import_time_basis'], 'not_recorded')
        self.assertEqual(row['validated_at'], '2026-09-27T10:00:00+00:00')
        self.assertNotEqual(row['modified_at'], row['validated_at'])
        self.assertFalse(self.case.data_store_states.rows)
        self.assertFalse(self.case.events.rows)
        self.event('imported', {'source_sha256': self.source})
        imported = self.client.get('/api/data-stores').get_json()['data_stores'][0]
        self.assertEqual(imported['imported_at'], '2026-09-27T11:00:00+00:00')
        detail = self.client.get(self.base).get_json()
        self.assertTrue(detail['connections_loaded'])
        self.assertEqual(detail['protocols'][0]['epoch_count'], 2)
        self.assertEqual(detail['parser']['parser_sha256'], 'c' * 64)

    def test_freeze_unfreeze_archive_restore_are_audited_and_never_change_scientific_data(self):
        before = copy.deepcopy((self.service.rows, self.service.details, self.case.sources.rows))
        file_bytes = self.path.read_bytes()
        frozen = self.change('freeze', 0)
        self.assertEqual(frozen.status_code, 200, frozen.get_json())
        self.assertTrue(frozen.get_json()['state']['frozen'])
        self.assertEqual(frozen.get_json()['state']['actor_kind'], 'local_user')
        self.assertEqual(frozen.get_json()['state']['actor'], os.environ.get('USER', 'local-user'))
        blocked = self.change('archive', 1)
        self.assertEqual(blocked.status_code, 409)
        self.assertIn('Unfreeze', blocked.get_json()['error'])
        self.assertEqual(self.change('unfreeze', 0).status_code, 409)
        # Freeze is not scientific approval and does not block per-protocol tags.
        tagged = self.client.post(self.case.base + '/curation', json=self.case.curation_body(
            {'tags_add': ['still editable']}), headers=self.headers)
        self.assertEqual(tagged.status_code, 200, tagged.get_json())
        self.assertEqual(self.change('unfreeze', 1).status_code, 200)
        archived = self.change('archive', 2)
        self.assertEqual(archived.status_code, 200)
        inventory = self.client.get('/api/data-stores').get_json()
        self.assertEqual(inventory['counts'], {'total': 1, 'active': 0, 'archived': 1, 'frozen': 0, 'query_excluded': 0})
        self.assertEqual(self.client.get(self.case.base).get_json()['counts']['epochs'], 2)
        self.assertEqual(len(self.client.get(self.case.base + '/epochs').get_json()['epochs']), 2)
        exported = self.client.post(self.case.base + '/exports', json={
            'query_revision': self.case.revision()}, headers=self.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        restored = self.change('restore', 3)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.get_json()['state']['version'], 4)
        self.assertFalse(restored.get_json()['state']['archived'])
        self.assertEqual((self.service.rows, self.service.details, self.case.sources.rows), before)
        self.assertEqual(self.path.read_bytes(), file_bytes)
        actions = [event['action'] for event in self.case.events.rows if event['action'].startswith('data_store_')]
        self.assertEqual(actions, ['data_store_frozen', 'data_store_unfrozen', 'data_store_archived', 'data_store_restored'])
        payload = next(event['payload'] for event in self.case.events.rows if event['action'] == 'data_store_frozen')
        self.assertEqual(payload['before']['version'], 0)
        self.assertEqual(payload['after']['version'], 1)
        self.assertEqual(payload['audit']['actor']['kind'], 'local_user')
        self.assertFalse(payload['source_files_changed'])
        self.assertFalse(payload['catalog_membership_changed'])

    def test_bad_source_body_version_or_actor_fail_closed(self):
        for body in ({'action': []}, {'expected_version': True}, {'actor': ''}, {'actor': []},
                     {'reason': ['no']}, {'action': 'delete'}, {'extra': 'unsupported'}):
            with self.subTest(body=body):
                response = self.change('freeze', 0, **body) if 'action' not in body else self.client.post(
                    self.base + '/state', json={'action': 'freeze', 'expected_version': 0, 'reason': '', **body}, headers=self.headers)
                self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(self.client.get('/api/data-stores/' + 'b' * 64).status_code, 400)
        self.assertEqual(self.client.get('/api/data-stores/bad-sha').status_code, 400)
        self.assertEqual(self.client.get(self.base + '/events?limit=101').status_code, 400)
        self.assertEqual(self.client.get(self.base + '/events?offset=-1').status_code, 400)
        self.assertFalse(self.case.data_store_states.rows)
        self.assertFalse(self.case.events.rows)

    def test_event_failure_rolls_back_state_and_an_explicit_actor_is_only_a_claim(self):
        with patch.object(self.case.events, 'insert1', side_effect=RuntimeError('audit unavailable')), \
             self.assertLogs(self.case.app.logger, level='ERROR'):
            failed = self.change('freeze', 0)
        self.assertEqual(failed.status_code, 500)
        self.assertFalse(self.case.data_store_states.rows)
        self.assertFalse(self.case.events.rows)
        claimed = self.change('freeze', 0, actor='Scientist label')
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.get_json()['state']['actor_kind'], 'client_claimed')
        event = self.case.events.rows[-1]
        self.assertEqual(event['actor'], os.environ.get('USER', 'local-user'))
        self.assertEqual(event['payload']['audit']['actor']['kind'], 'client_claimed')
        self.assertFalse(event['payload']['audit']['actor']['authenticated_identity'])
        self.assertIn('RELEASE_LOCK', self.case.connection.queries[-1])

    def test_source_history_links_selected_epochs_not_broad_catalog_scope_and_fetches_new_payload_only(self):
        other = 'b' * 64
        self.service.sources.append({**self.service.sources[0], 'source_sha256': other, 'filename': 'other.h5'})
        self.service.manifests[other] = copy.deepcopy(self.service.manifests[self.source])
        self.service.rows[self.service.ids[1]]['source_sha256'] = other
        self.case.sources.insert1({'source_sha256': other, 'project_uuid': self.service.project['project_uuid']})
        self.service.protocols[self.service.protocol_id]['result']['source_revisions'] = [self.source, other]
        exact = self.event('curation_updated', {'before': {self.service.ids[0]: {'included': True}},
            'after': {self.service.ids[0]: {'included': False}}, 'query_context': {'source_revisions': [self.source, other]}})
        broad = self.event('legacy_query', {'source_revisions': [self.source, other]})
        self.event('imported', {'source_sha256': self.source}, project=str(uuid.uuid4()))
        history = self.client.get(self.base + '/events?limit=1').get_json()
        self.assertEqual([event['event_uuid'] for event in history['events']], [exact])
        self.assertNotIn('payload', history['events'][0])
        self.assertEqual(history['events'][0]['source_link'], {'basis': ['curation_epochs'], 'affected_epoch_count': 1})
        self.assertEqual(self.client.get('/api/data-stores/' + other + '/events').get_json()['events'], [])
        full_before = sum(item['projected'] is None for item in self.case.events.read_log)
        self.client.get(self.base + '/events')
        self.assertEqual(sum(item['projected'] is None for item in self.case.events.read_log), full_before)
        new = self.event('data_store_frozen', {'source_sha256': self.source})
        self.client.get(self.base + '/events')
        payload_read = [item for item in self.case.events.read_log if item['projected'] is None][-1]
        self.assertEqual(payload_read['restrictions'][-1], [{'event_uuid': new}])
        self.assertNotIn(broad, [event['event_uuid'] for event in self.client.get(self.base + '/events').get_json()['events']])
        # Export selects only one source even though snapshot/source scope includes both.
        exported = self.client.post(self.case.base + '/exports', json={'query_revision': self.case.revision(),
            'filters': {'cell_uuid': self.service.cell_ids[0]}}, headers=self.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        source_events = self.client.get(self.base + '/events').get_json()['events']
        self.assertTrue(any(event['action'] == 'dataset_revision_exported' for event in source_events))
        self.assertEqual(self.client.get('/api/data-stores/' + other + '/events').get_json()['events'], [])

    def test_missing_historical_membership_proof_is_reported_and_retried(self):
        missing_dataset = str(uuid.uuid4())
        event_uuid = self.event('dataset_revision_exported', {'dataset_uuid': missing_dataset,
            'source_revisions': [self.source]})
        first = self.client.get(self.base + '/events').get_json()
        self.assertEqual(first['events'], [])
        self.assertEqual(first['attribution']['unresolved_project_history_references'], 1)
        restored = {self.service.ids[0]: [{'dataset_uuid': missing_dataset}]}
        with patch.object(self.case.store, 'export_memberships', return_value=restored):
            second = self.client.get(self.base + '/events').get_json()
        self.assertEqual([event['event_uuid'] for event in second['events']], [event_uuid])
        self.assertEqual(second['attribution']['unresolved_project_history_references'], 0)

    def test_excluded_sources_leave_registered_predicate_and_tree_schema_valid(self):
        before = copy.deepcopy((self.service.rows, self.service.details))
        fields = self.service.predicate_fields()
        dynamic = next(field['id'] for field in fields['fields'] if field['path'] == 'parameters.example')
        predicate = {'field': dynamic, 'operator': 'gte', 'value': 0}
        self.assertEqual(self.service.explore_preview(predicate, dynamic)['matched_count'], 2)
        eligible_revision = self.service.source_scope()['revision']
        self.assertEqual(self.change('freeze', 0).status_code, 200)
        self.assertEqual(self.service.source_scope()['revision'], eligible_revision)
        self.assertEqual(self.change('unfreeze', 1).status_code, 200)
        self.assertEqual(self.change('exclude', 2).status_code, 200)
        with patch('h5py.File', side_effect=AssertionError('Metadata query must not read traces')):
            empty = self.service.explore_preview(predicate, dynamic)
            self.assertEqual((empty['matched_count'], empty['total_source'], empty['total_catalog']), (0, 0, 2))
            self.assertEqual(empty['source_revisions'], [])
            self.assertEqual(empty['tree']['split_order'], [dynamic])
            for ast in ({'all': []}, {'not': {'field': dynamic, 'operator': 'eq', 'value': 9}}):
                self.assertEqual(self.service.explore_preview(ast)['matched_count'], 0)
            schema_field = next(field for field in self.service.predicate_fields()['fields'] if field['id'] == dynamic)
            self.assertEqual(schema_field['types'], ['number'])
            self.assertEqual(schema_field['active_types'], [])
            self.assertEqual(schema_field['choices'], [])
            self.assertEqual(len(self.service.query_result(self.service.protocol_id)['epochs']), 2)
        self.assertNotEqual(self.service.source_scope()['revision'], eligible_revision)
        self.assertEqual(self.change('include', 3).status_code, 200)
        self.assertEqual(self.service.source_scope()['revision'], eligible_revision)
        self.assertEqual(self.service.explore_preview(predicate, dynamic)['matched_count'], 2)
        self.assertEqual((self.service.rows, self.service.details), before)

    def test_source_quantities_count_recorded_metadata_without_trace_reads(self):
        self.service.rows[self.service.ids[0]]['streams'] = [
            {'kind': 'responses'}, {'kind': 'responses'}, {'kind': 'stimuli'}]
        with patch('h5py.File', side_effect=AssertionError('No trace reads')):
            detail = self.case.data_stores.detail(self.source)
        for key, value in {'duration_seconds': 2, 'blocks': 2, 'groups': 2,
                           'responses': 2, 'stimuli': 1, 'cell_types': 1}.items():
            self.assertEqual(detail['counts'][key], value)
        self.assertEqual(detail['cell_types'], [{'name': 'fixture-type', 'cells': 2, 'epochs': 2, 'duration_seconds': 2}])
        self.assertEqual(detail['acquisition_protocols'][0]['responses'], 2)

    def test_propagation_keeps_frozen_hashes_and_restoration_finds_zero_current_links(self):
        predicate = {'field': 'protocol', 'operator': 'eq', 'value': 'example'}
        recipe = {'predicate': predicate, 'splits': 'date,cell', 'source_revisions': [self.source],
                  'epochs': [{'uuid': key, 'metadata_hash': '0' * 64} for key in self.service.ids],
                  'tree_view': {'fields': ['date', 'cell']}, 'name': 'Fixture saved query'}
        binding = {'recipe': recipe, 'version': 1, 'revision_uuid': str(uuid.uuid4())}
        self.service.set_binding_provider(lambda identity: binding)
        state_before = copy.deepcopy((self.case.data_store_states.rows, self.case.events.rows))
        changed = self.case.data_stores.propagation_preview(self.source)['protocols'][0]
        self.assertEqual(set(changed['diff']['changed']), set(self.service.ids))
        self.assertEqual(changed['diff_summary']['delta']['cells'], 0)
        self.assertEqual((self.case.data_store_states.rows, self.case.events.rows), state_before)
        self.case.data_stores.transition(self.source, 'exclude', 0)
        removed = self.case.data_stores.propagation_preview(self.source)['protocols'][0]
        self.assertEqual(removed['next_count'], 0)
        self.assertEqual(removed['diff_summary']['delta']['cells'], -2)
        # Simulate an already applied empty working set, with its predicate kept.
        binding['recipe']['epochs'] = []
        self.assertEqual(self.case.data_stores.propagation_preview(self.source)['protocols'], [])
        self.case.data_stores.transition(self.source, 'include', 1)
        restored = self.case.data_stores.propagation_preview(self.source)['protocols'][0]
        self.assertEqual(restored['previous_count'], 0)
        self.assertEqual(restored['next_count'], 2)
        self.assertEqual(restored['diff_summary']['delta']['acquisition_protocols'], 1)
        self.assertEqual(set(restored['diff']['added']), set(self.service.ids))

    def test_registration_guard_is_project_wide_and_always_released(self):
        import hashlib
        lock = hashlib.sha256(('source-eligibility:' + self.service.project['project_uuid']).encode()).hexdigest()
        connection = self.service.dj.conn()
        with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
            with self.case.data_stores.registration_locks():
                raise RuntimeError('fixture failure')
        self.assertEqual(connection.queries[-2:], [f"SELECT GET_LOCK('{lock}', 10)", f"SELECT RELEASE_LOCK('{lock}')"])
        self.change('archive', 0)
        self.assertIn(f"SELECT GET_LOCK('{lock}', 10)", connection.queries)
        foreign = {'project_uuid': str(uuid.uuid4()), 'source_sha256': self.source,
                   'version': 99, 'archived': False, 'frozen': False, 'updated_at': 'foreign',
                   'actor': 'foreign', 'server_actor': 'foreign', 'reason': 'foreign'}
        self.case.data_store_states.insert1(foreign)
        state = self.case.data_stores.source_states()[self.source]
        self.assertTrue(state['archived'])
        self.assertEqual(state['version'], 1)

    def test_legacy_starter_tree_view_uses_canonical_ui_grouping(self):
        original = self.service.protocols[self.service.protocol_id]['definition']
        original['view']['group_by'] = ['cell.type', 'cell.start_time']
        before = copy.deepcopy(original)
        plan = self.case.data_stores.propagation_preview(self.source)['protocols'][0]
        self.assertEqual(plan['splits'], 'date,cell,block')
        self.assertEqual(plan['preview']['tree']['split_order'], ['date', 'cell', 'block'])
        self.assertEqual(plan['next_count'], 2)
        self.assertEqual(plan['view_adaptation']['original_group_by'], ['cell.type', 'cell.start_time'])
        self.assertEqual(original, before)

    def test_missing_duration_is_unknown_not_zero(self):
        self.service.rows[self.service.ids[0]]['duration_seconds'] = None
        result = self.case.data_stores.detail(self.source)
        self.assertIsNone(result['counts']['duration_seconds'])
        self.assertIsNone(result['acquisition_protocols'][0]['duration_seconds'])
        self.assertIsNone(result['cell_types'][0]['duration_seconds'])
        self.service.rows[self.service.ids[0]]['duration_seconds'] = 0
        self.assertEqual(self.case.data_stores.detail(self.source)['counts']['duration_seconds'], 1)
        self.assertEqual(self.case.data_stores.detail(self.source)['cell_types'][0]['duration_seconds'], 1)

    def test_visibility_and_query_eligibility_are_independent_and_freeze_locks_both(self):
        scope = self.service.source_scope()['revision']
        self.assertEqual(self.change('archive', 0).status_code, 200)
        archived = self.case.data_stores.detail(self.source)['state']
        self.assertTrue(archived['archived'])
        self.assertFalse(archived['query_excluded'])
        self.assertEqual(self.service.source_scope()['revision'], scope)
        self.assertEqual(self.service.explore_preview({'all': []})['matched_count'], 2)
        self.assertEqual(self.change('exclude', 1).status_code, 200)
        excluded_scope = self.service.source_scope()['revision']
        self.assertNotEqual(excluded_scope, scope)
        self.assertEqual(self.change('restore', 2).status_code, 200)
        self.assertEqual(self.service.source_scope()['revision'], excluded_scope)
        self.assertEqual(self.service.explore_preview({'all': []})['matched_count'], 0)
        self.assertEqual(self.change('freeze', 3).status_code, 200)
        for action in ('archive', 'include'):
            self.assertEqual(self.change(action, 4).status_code, 409)
        self.assertEqual(self.change('unfreeze', 4).status_code, 200)
        self.assertEqual(self.change('include', 5).status_code, 200)
        self.assertEqual(self.service.source_scope()['revision'], scope)
        self.assertEqual(self.service.explore_preview({'all': []})['matched_count'], 2)
        transitions = [row['payload'] for row in self.case.events.rows]
        self.assertEqual([row['new_query_eligibility_changed'] for row in transitions],
                         [False, True, False, False, False, True])
