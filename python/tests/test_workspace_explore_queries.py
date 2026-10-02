"""Service/HTTP contract checks using disposable acquisition and SQL fixtures."""
import copy
import threading
import unittest
from unittest.mock import patch

try:
    from . import test_workspace_api as api_fixture
    from . import test_workspace_refresh_cache as refresh_fixture
except ImportError:
    import test_workspace_api as api_fixture
    import test_workspace_refresh_cache as refresh_fixture

import workspace_explore_queries as queries


class RequestedSummaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service, self.client = self.fixture.service, self.fixture.client
        self.jobs = self.fixture.app.extensions['metadata_summary_jobs']
        self.addCleanup(self.join)

    def join(self):
        worker = self.jobs.worker
        if worker:
            worker.join(5)
            self.assertFalse(worker.is_alive(), 'Summary worker did not stop')

    def submit(self, **changes):
        body = {'predicate': {'all': []}, 'summary_fields': ['parameters/example'], **changes}
        return self.client.post('/api/explore/summaries', json=body, headers=self.fixture.headers)

    def test_native_bound_datetime_header_has_stable_identity_witness(self):
        import datetime
        import uuid
        row = {'project_uuid': self.service.project['project_uuid'],
               'protocol_uuid': self.service.protocol_id, 'revision_uuid': str(uuid.uuid4()),
               'version': 1, 'bound_at': datetime.datetime(2026, 10, 1, 12, 30)}
        self.fixture.protocol_bindings.insert1(row)
        context = {'protocol_uuid': self.service.protocol_id}
        before = queries.generation(self.service, context)
        saved = self.fixture.protocol_bindings.rows[0]
        saved.update(bound_at=datetime.datetime(2026, 10, 2), actor='audit-only')
        self.assertEqual(before, queries.generation(self.service, context))
        for key, value in [('version', 2), ('revision_uuid', str(uuid.uuid4()))]:
            previous = queries.generation(self.service, context)
            saved[key] = value
            self.assertNotEqual(previous['binding'], queries.generation(self.service, context)['binding'])

    def test_bound_datetime_summary_acknowledgement_polls_with_same_witness(self):
        import datetime
        import uuid
        self.fixture.protocol_bindings.insert1({
            'project_uuid': self.service.project['project_uuid'],
            'protocol_uuid': self.service.protocol_id, 'revision_uuid': str(uuid.uuid4()),
            'version': 1, 'bound_at': datetime.datetime(2026, 10, 1)})
        self.jobs.autostart = False
        with patch.object(self.jobs, '_calculate', return_value={'matched_count': 0, 'summaries': {}}), patch('workspace_explore_queries.typed_scope', return_value=(None, None)):
            response = self.submit(protocol_uuid=self.service.protocol_id, summary_fields=[])
            self.assertEqual(response.status_code, 202, response.get_json())
            ack = response.get_json()
            self.jobs.drive_worker()
        ready = self.jobs.poll(ack['request_id'])
        self.assertEqual(ready['status'], 'ready', ready)
        self.assertEqual(ready['generation'], ack['generation'])

    def test_full_binding_fallback_omits_recipe_and_audit_from_witness(self):
        import datetime
        binding = {'project_uuid': self.service.project['project_uuid'],
                   'protocol_uuid': self.service.protocol_id, 'revision_uuid': 'revision',
                   'version': 3, 'bound_at': datetime.datetime(2026, 10, 1),
                   'recipe': {'unrelated': datetime.datetime(2026, 10, 1)}}
        with patch.object(self.service, 'binding_header_provider', None), patch.object(self.service, 'binding', return_value=binding):
            before = queries.generation(self.service, {'protocol_uuid': self.service.protocol_id})
            binding['bound_at'] = datetime.datetime(2026, 10, 2)
            binding['recipe'] = {'other': object()}
            self.assertEqual(before, queries.generation(self.service, {'protocol_uuid': self.service.protocol_id}))

    def test_multibyte_summary_cannot_publish_above_encoded_response_budget(self):
        self.jobs.autostart = False
        # Same character count: ASCII fits, three-byte Unicode must be refused.
        for character, expected_status in [('a', 'ready'), ('雪', 'failed')]:
            with self.subTest(character=character):
                result = {'matched_count': 1, 'summaries': {'parameters/example': {
                    'values': [{'value': character * (1024 * 1024), 'type': 'string', 'count': 1}],
                    'present_count': 1, 'missing_count': 0, 'values_truncated': False}}}
                with patch.object(self.jobs, '_calculate', return_value=result):
                    submitted = self.submit().get_json()
                    self.jobs.drive_worker()
                response = self.jobs.poll(submitted['request_id'])
                self.assertEqual(response['status'], expected_status)
                if expected_status == 'failed':
                    self.assertNotIn('result', response)
                    self.assertIn('response budget', response['error'])

    def test_registry_complete_types_and_tree_definitions_without_distributions(self):
        response = self.client.get('/api/explore/field-registry')
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        fields = {field['id']: field for field in data['fields']}
        self.assertIn('parameters/example', fields)
        self.assertEqual(fields['parameters/example']['types'], ['number'])
        self.assertIn('curation/' + self.service.protocol_id + '/tags', fields)
        self.assertTrue({'date', 'cell', 'group', 'block'} <= {field['id'] for field in data['tree_fields']})
        self.assertFalse(data['summary_available'])
        self.assertIn('publication', data['generation'])
        for field in data['fields'] + data['tree_fields']:
            self.assertFalse({'choices', 'count', 'distinct_count', 'missing_count', 'examples'} & field.keys())
        self.assertEqual(self.client.get('/api/explore/field-registry?cell_uuid=x').status_code, 400)

    def test_summary_exact_requested_fields_and_empty_scope_are_distinct(self):
        registry = self.client.get('/api/explore/field-registry').get_json()
        response = self.submit(generation=registry['generation'], scope={'cell_uuid': self.service.cell_ids[0]})
        self.assertEqual(response.status_code, 202, response.get_json())
        acknowledgement = response.get_json()
        self.assertEqual(acknowledgement['status'], 'pending')
        self.assertNotIn('result', acknowledgement)
        self.join()
        data = self.client.get('/api/explore/summaries/' + acknowledgement['request_id']).get_json()
        self.assertEqual(data['status'], 'ready', data)
        self.assertEqual(data['generation'], acknowledgement['generation'])
        self.assertEqual(data['result']['matched_count'], 1)
        self.assertEqual(data['result']['summaries'], {'parameters/example': {
            'values': [{'value': 0, 'type': 'number', 'count': 1}], 'present_count': 1,
            'missing_count': 0, 'values_truncated': False}})
        empty = self.submit(scope={'cell_uuid': '00000000-0000-0000-0000-000000000000'}).get_json()
        self.join()
        data = self.jobs.poll(empty['request_id'])
        self.assertEqual(data['result']['matched_count'], 0)
        self.assertEqual(data['result']['summaries']['parameters/example']['values'], [])

    def test_ready_becomes_stale_after_source_exclusion_without_unfiltered_fallback(self):
        request = self.submit().get_json()
        self.join()
        self.service.set_source_state_provider(lambda: {'a' * 64: {'query_excluded': True}})
        data = self.jobs.poll(request['request_id'])
        self.assertEqual(data['status'], 'stale')
        self.assertNotIn('result', data)
        self.assertEqual(data['generation'], request['generation'])

    def test_generation_mismatch_rejected_before_admission(self):
        registry = self.client.get('/api/explore/field-registry').get_json()
        self.service._explore_publication = 'new-publication'
        response = self.submit(generation=registry['generation'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['status'], 'stale')
        self.assertEqual(response.get_json()['generation']['publication'], 'new-publication')
        self.assertFalse(self.jobs.jobs)

    def test_cancel_and_failure_keep_request_identity_and_never_invent_counts(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return {'matched_count': 99, 'summaries': {}}
        from workspace_typed_index import TypedMetadataIndex
        owner, method = (TypedMetadataIndex, 'summaries') if getattr(self.service, 'typed_index', None) else (queries, '_native_summaries')
        with patch.object(owner, method, side_effect=blocked):
            request = self.submit().get_json()
            self.assertTrue(entered.wait(3))
            data = self.client.post('/api/explore/summaries/' + request['request_id'] + '/cancel',
                json={}, headers=self.fixture.headers).get_json()
            self.assertEqual(data['status'], 'cancelled')
            release.set()
            self.join()
        self.assertEqual(self.jobs.poll(request['request_id'])['status'], 'cancelled')
        with patch.object(owner, method, side_effect=RuntimeError('fixture read failed')):
            request = self.submit().get_json()
            self.join()
        data = self.jobs.poll(request['request_id'])
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['request_id'], request['request_id'])
        self.assertIn('fixture read failed', data['error'])
        self.assertNotIn('result', data)

    def test_invalid_requests_reject_id_lists_unknown_fields_and_bad_shapes(self):
        for changes in ({'scope': {'epoch_ids': []}}, {'summary_fields': ['missing/field']},
                        {'summary_fields': ['cell', 'cell']}, {'filters': {'block_uuid': 'x'}},
                        {'scope': {'cell_uuid': 7}}, {'generation': []}):
            with self.subTest(changes=changes):
                self.assertEqual(self.submit(**changes).status_code, 400)
        self.assertFalse(self.jobs.jobs)

    def test_protocol_scope_retains_frozen_binding_membership(self):
        with patch.object(self.service, 'binding', return_value={'recipe': {'epochs': [{'uuid': self.service.ids[1]}]}}):
            context = queries.query_context(self.service, {'predicate': {'all': []}, 'protocol_uuid': self.service.protocol_id})
            predicate, scope = queries.typed_scope(self.service, context)
            self.assertEqual(list(scope['epoch_ids']), [self.service.ids[1]])
            self.assertEqual(scope['sources'], ['a' * 64])
            self.assertEqual(predicate, {'all': [{'all': []}]})

    def test_terminal_job_retention_is_bounded(self):
        for _ in range(queries.MAX_JOBS + 2):
            self.assertEqual(self.submit().status_code, 202)
            self.join()
        self.assertEqual(len(self.jobs.jobs), queries.MAX_JOBS)


class TypedServiceAdapterTests(RequestedSummaryTests):
    def setUp(self):
        super().setUp()
        from pathlib import Path
        from workspace_disk_index import DiskMetadataIndex
        from workspace_typed_lifecycle import prepare
        path = Path(self.fixture.temp.name) / 'cache' / 'metadata' / ('d' * 64 + '.sqlite')
        self.service.details[self.service.ids[0]]['parameters']['optional'] = None
        index = DiskMetadataIndex.build(path, self.service.rows, self.service.details,
            self.service.sources, 'd' * 64, self.service.project['project_uuid'])
        self.service.disk_index = index
        self.service.typed_index, status = prepare(index)
        self.assertEqual(status, 'built')

    def test_custom_filter_policy_retains_authoritative_reader_and_cursor_fence(self):
        original = self.service._filter_rows
        selected = {self.service.ids[0]}
        def custom(rows, filters):
            return [row for row in original(rows, filters) if row['epoch_uuid'] in selected]
        with patch.object(self.service, '_filter_rows', side_effect=custom):
            result = self.service.explore_page({'all': []})
            self.assertEqual([row['epoch_uuid'] for row in result['rows']], [self.service.ids[0]])
            request = self.submit().get_json()
            self.join()
            self.assertEqual(self.jobs.poll(request['request_id'])['result']['matched_count'], 1)
            selected.add(self.service.ids[1])
            first = self.service.explore_page({'all': []}, limit=1)
            selected.remove(self.service.ids[0])
            with self.assertRaises(queries.StaleQuery):
                self.service.explore_page({'all': []}, limit=1, cursor=first['cursor'])

    def test_recorded_null_absence_and_unrequested_summary_remain_distinct(self):
        request = self.submit(summary_fields=['parameters/optional']).get_json()
        self.join()
        result = self.jobs.poll(request['request_id'])['result']
        self.assertNotIn('parameters/example', result['summaries'])
        self.assertEqual(result['summaries']['parameters/optional'], {
            'values': [{'value': None, 'type': 'null', 'count': 1}],
            'present_count': 1, 'missing_count': 1, 'values_truncated': False})
        for operator, identity in [('is_null', self.service.ids[0]), ('missing', self.service.ids[1])]:
            page = self.service.explore_page({'field': 'parameters/optional', 'operator': operator})
            self.assertEqual([row['epoch_uuid'] for row in page['rows']], [identity])

    def test_annotation_generation_changes_stale_native_summary_results(self):
        key = 'curation/' + self.service.protocol_id + '/tags'
        request = self.submit(summary_fields=[key], predicate={'field': key, 'operator': 'contains', 'value': 'checked'}).get_json()
        self.join()
        before = self.jobs.poll(request['request_id'])
        self.assertEqual(before['status'], 'ready', before)
        self.assertEqual(before['result']['matched_count'], 0)
        self.fixture.curation.insert1({'project_uuid': self.service.project['project_uuid'],
            'protocol_uuid': self.service.protocol_id, 'epoch_uuid': self.service.ids[0],
            'tags': ['checked'], 'revision': 1})
        stale = self.jobs.poll(request['request_id'])
        self.assertEqual(stale['status'], 'stale')
        self.assertNotIn('result', stale)

    def test_native_order_duplicate_and_validation_contract_uses_typed_membership(self):
        predicate = {'field': 'parameters/example', 'operator': 'gte', 'value': 0}
        ids = [self.service.ids[1], self.service.ids[0], self.service.ids[1], 'foreign']
        result = self.service._match_metadata_predicate(predicate, ids)
        self.assertEqual(result, self.service.disk_index.match(predicate, ids=ids))
        with self.assertRaisesRegex(ValueError, 'type does not match'):
            self.service._match_metadata_predicate({'field': 'parameters/example', 'operator': 'eq', 'value': 'zero'}, ids)

    def test_generation_bound_page_and_query_cursor_faults(self):
        predicate = {'all': []}
        first = self.service.explore_page(predicate, limit=1)
        self.assertEqual(len(first['rows']), 1)
        self.assertIsInstance(first['cursor'], str)
        second = self.service.explore_page(predicate, limit=1, cursor=first['cursor'])
        self.assertIsNone(second['cursor'])
        self.assertEqual([first['rows'][0], second['rows'][0]], list(self.service.rows.values()))
        with self.assertRaises(queries.StaleQuery):
            self.service.explore_page({'field': 'cell', 'operator': 'eq', 'value': self.service.cell_ids[1]},
                                      limit=1, cursor=first['cursor'])
        with self.assertRaisesRegex(ValueError, 'Malformed metadata cursor'):
            self.service.explore_page(predicate, cursor=first['cursor'] + 'tampered')
        self.service._explore_publication = 'replacement'
        with self.assertRaises(queries.StaleQuery):
            self.service.explore_page(predicate, cursor=first['cursor'])

    def test_global_eligibility_and_frozen_protocol_dataset_are_distinct(self):
        self.service.set_source_state_provider(lambda: {'a' * 64: {'query_excluded': True}})
        self.assertEqual(self.service.explore_page({'all': []})['rows'], [])
        frozen = self.service.explore_page({'all': []}, protocol_uuid=self.service.protocol_id)
        self.assertEqual(frozen['rows'], list(self.service.rows.values()))
        request = self.submit(protocol_uuid=self.service.protocol_id).get_json()
        self.join()
        self.assertEqual(self.jobs.poll(request['request_id'])['result']['matched_count'], 2)

    def test_typed_aggregate_does_not_hold_navigation_lock_or_native_reader(self):
        from workspace_typed_index import TypedMetadataIndex
        entered, release = threading.Event(), threading.Event()
        original = TypedMetadataIndex.summaries
        def blocked(reader, *args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return original(reader, *args, **kwargs)
        with patch.object(TypedMetadataIndex, 'summaries', new=blocked):
            request = self.submit().get_json()
            self.assertTrue(entered.wait(3))
            page = self.client.post('/api/explore/page', json={'predicate': {'all': []}, 'limit': 1},
                                    headers=self.fixture.headers)
            self.assertEqual(page.status_code, 200, page.get_json())
            self.assertEqual(len(page.get_json()['rows']), 1)
            release.set()
            self.join()
        self.assertEqual(self.jobs.poll(request['request_id'])['status'], 'ready')

    def test_annotation_changed_while_typed_summary_runs_refuses_result(self):
        from workspace_typed_index import TypedMetadataIndex
        original = TypedMetadataIndex.summaries
        def changed(reader, *args, **kwargs):
            result = original(reader, *args, **kwargs)
            self.service._explore_publication = 'concurrent-refresh'
            return result
        with patch.object(TypedMetadataIndex, 'summaries', new=changed):
            request = self.submit().get_json()
            self.join()
        result = self.jobs.poll(request['request_id'])
        self.assertEqual(result['status'], 'stale')
        self.assertNotIn('result', result)

    def test_native_details_preserved_and_sidecar_reuse_keeps_verified_generation(self):
        from workspace_typed_lifecycle import prepare
        owner = self.service.typed_index
        same, status = prepare(self.service.disk_index, owner)
        self.assertIs(same, owner)
        self.assertEqual(status, 'reused')
        with queries.typed_reader(self.service) as reader:
            for identity in self.service.ids:
                self.assertEqual(reader.detail(identity), self.service.details[identity])


class PublicationCacheTests(unittest.TestCase):
    def setUp(self):
        self.fixture = refresh_fixture.RefreshCacheTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service

    def test_unchanged_refresh_discards_tree_scope_after_verified_publication(self):
        cache = self.service._tree_page_scope_cache = object()
        before = self.service._explore_publication
        result = self.service.refresh()
        self.assertTrue(result['discovery_indexes_preserved'])
        self.assertIsNone(self.service._tree_page_scope_cache)
        self.assertNotEqual(before, self.service._explore_publication)

    def test_typed_build_failure_does_not_publish_or_discard_prior_generation(self):
        owner, rows, token = self.service.typed_index, self.service.rows, self.service._explore_publication
        cache = self.service._tree_page_scope_cache = object()
        with patch('workspace_typed_lifecycle.prepare', side_effect=RuntimeError('typed build interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'typed build interrupted'):
                self.service.refresh()
        self.assertIs(self.service.typed_index, owner)
        self.assertIs(self.service.rows, rows)
        self.assertIs(self.service._tree_page_scope_cache, cache)
        self.assertEqual(self.service._explore_publication, token)
        self.service.refresh()
        self.assertEqual(self.service.last_refresh['typed_metadata_index'], 'reused')

    def test_rebuild_pins_old_native_and_typed_assets_for_existing_readers(self):
        owner = self.service.typed_index
        self.fixture.add_source('three')
        self.service.refresh()
        self.assertIsNot(self.service.typed_index, owner)
        self.assertTrue(owner.reader.path.exists())
        self.assertTrue(owner.native.path.exists())
        with owner.clone() as reader:
            self.assertEqual(reader.count(), 2)
        self.assertEqual(self.service.typed_index.reader.count(), 3)

    def test_failed_verification_preserves_published_rows_cache_and_token(self):
        cache = self.service._tree_page_scope_cache = object()
        rows, before = self.service.rows, self.service._explore_publication
        self.fixture.evaluator.side_effect = ValueError('verification failed')
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            self.service.refresh()
        self.assertIs(self.service.rows, rows)
        self.assertIs(self.service._tree_page_scope_cache, cache)
        self.assertEqual(self.service._explore_publication, before)


if __name__ == '__main__':
    unittest.main()
