"""Response-local summary reuse preserves full output and custom read order."""
import copy
from collections import UserDict
import unittest
from unittest.mock import patch
import uuid

from disco.operation_timing import capture_timings
from workspace_service import WorkspaceService, _FrozenProtocolBinding
import test_workspace_api as api_tests


class ProtocolSummaryTests(unittest.TestCase):
    def setUp(self):
        self.case = api_tests.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service = self.case.service
        self.protocol = self.service.protocol_id

    def measured(self, read):
        with capture_timings() as records:
            result = read()
        calls = [item for item in records if item['module'] == 'workspace_service'
                 and item['operation'] == 'query_result']
        self.assertTrue(all(item['outcome'] == 'ok' for item in calls))
        return result, len(calls)

    def legacy(self, filters=None):
        with patch.object(self.service, 'filtered_rows', wraps=self.service.filtered_rows):
            return self.measured(lambda: self.service.protocol(self.protocol, filters))

    def test_full_summary_matches_legacy_with_one_query_and_independent_counts(self):
        self.service.protocols[self.protocol]['result']['epochs'].reverse()
        expected, old_calls = self.legacy()
        actual, calls = self.measured(lambda: self.service.protocol(self.protocol))
        self.assertEqual(actual, expected)
        self.assertEqual((old_calls, calls), (4, 1))
        actual['counts']['epochs'] = -1
        self.assertEqual(actual['total_counts']['epochs'], 2)
        self.assertEqual(self.service.protocol(self.protocol), expected)

    def test_ordinary_filter_parity_including_empty_and_normalized_identity(self):
        self.service.rows[self.service.ids[0]]['cell_type'] = 'first-type'
        for filters in ({}, {'cell_type': ''}, {'cell_type': 'first-type'},
                        {'cell_type': 'absent'}, {'group_label': 'Recorded group'},
                        {'epoch_uuid': self.service.ids[0].upper()},
                        {'cell_uuid': self.service.cell_ids[1]}):
            with self.subTest(filters=filters):
                expected, old_calls = self.legacy(filters)
                actual, calls = self.measured(lambda: self.service.protocol(self.protocol, filters))
                self.assertEqual(actual, expected)
                self.assertEqual((old_calls, calls), (4, 1))
        for filters in ({'cell_uuid': 'invalid'}, {'cell_type': 1}, []):
            with self.subTest(filters=filters):
                with self.assertRaises(ValueError):
                    self.service.protocol(self.protocol, filters)

    def bind_one_epoch(self):
        created = self.case.client.post('/api/explore/revisions', json={
            'predicate': {'all': [{'field': 'parameters/example', 'operator': 'eq', 'value': 0}]},
            'splits': 'cell', 'name': 'One epoch'}, headers=self.case.headers)
        self.assertEqual(created.status_code, 201, created.get_json())
        root = '/api/explore/revisions/' + created.get_json()['revision_uuid']
        compared = self.case.client.post(root + '/compare-to-protocol', json={
            'protocol_uuid': self.protocol}, headers=self.case.headers).get_json()
        applied = self.case.client.post(root + '/apply-to-protocol', json={
            'protocol_uuid': self.protocol,
            'expected_binding_version': compared['expected_binding_version'],
            'expected_query_revision': compared['expected_query_revision']}, headers=self.case.headers)
        self.assertEqual(applied.status_code, 200, applied.get_json())

    def test_bound_membership_is_read_fresh_and_missing_members_refused(self):
        self.bind_one_epoch()
        expected, _ = self.legacy()
        actual, calls = self.measured(lambda: self.service.protocol(self.protocol))
        self.assertEqual(actual, expected)
        self.assertEqual(calls, 1)
        self.assertEqual(actual['counts']['epochs'], 1)
        self.case.protocol_bindings.rows[0]['version'] += 1
        fresh = self.service.protocol(self.protocol)
        self.assertEqual(fresh['binding']['version'], actual['binding']['version'] + 1)
        del self.service.rows[self.service.ids[0]]
        with self.assertRaisesRegex(ValueError, 'unavailable epochs'):
            self.service.protocol(self.protocol)

    def add_protocol(self):
        other = str(uuid.uuid4())
        self.service.protocols[other] = copy.deepcopy(self.service.protocols[self.protocol])
        self.service.protocols[other]['result']['epochs'] = [
            {'uuid': self.service.ids[1], 'metadata_hash': 'b' * 64}]
        return other

    def test_other_protocol_membership_stays_fresh(self):
        other = self.add_protocol()
        expected, old_calls = self.legacy()
        actual, calls = self.measured(lambda: self.service.protocol(self.protocol))
        self.assertEqual(actual, expected)
        self.assertEqual((old_calls, calls), (5, 2))
        self.assertIn(other, actual['cells'][1]['protocol_uuids'])
        self.service.protocols[other]['result']['epochs'] = []
        self.assertNotIn(other, self.service.protocol(self.protocol)['cells'][1]['protocol_uuids'])

    def test_instance_read_overrides_keep_legacy_calls(self):
        names = ('protocol', 'query_result', 'filtered_rows', '_filter_rows', '_decorate',
                 '_curation', '_counts', '_cell_summary', '_ready', 'validate_metadata_filters', 'binding')
        for name in names:
            with self.subTest(name=name):
                with patch.object(self.service, name, wraps=getattr(self.service, name)) as custom:
                    _, calls = self.measured(lambda: self.service.protocol(self.protocol))
                    self.assertEqual(calls, 4)
                    self.assertGreater(custom.call_count, 0)

    def test_class_read_override_keeps_legacy_calls_and_exception(self):
        original = WorkspaceService.query_result
        calls = []
        def custom(service, protocol):
            calls.append(protocol)
            return original(service, protocol)
        with patch.object(WorkspaceService, 'query_result', custom):
            self.service.protocol(self.protocol)
        self.assertEqual(calls, [self.protocol] * 4)
        with patch.object(WorkspaceService, '_ready', side_effect=RuntimeError('custom readiness')):
            with self.assertRaisesRegex(RuntimeError, 'custom readiness'):
                self.service.protocol(self.protocol)

    def test_custom_maps_and_missing_curation_attribute_keep_legacy_readers(self):
        for name in ('rows', 'cells', 'protocols'):
            with self.subTest(name=name):
                with patch.object(self.service, name, UserDict(getattr(self.service, name))):
                    _, calls = self.measured(lambda: self.service.protocol(self.protocol))
                    self.assertEqual(calls, 4)
        del self.service.curation_provider
        with patch.object(self.service, '_curation', return_value={}):
            result, calls = self.measured(lambda: self.service.protocol(self.protocol))
        self.assertEqual(calls, 4)
        self.assertEqual(result['counts']['epochs'], 2)

    def test_public_cell_summary_still_invokes_custom_none_protocol_reader(self):
        self.service.protocols[None] = {}
        original = self.service.query_result
        calls = []
        def custom(protocol):
            calls.append(protocol)
            return {'epochs': []} if protocol is None else original(protocol)
        with patch.object(self.service, 'query_result', side_effect=custom):
            self.assertEqual(self.service._cell_summary([]), [])
        self.assertEqual(calls, [self.protocol, None])

    def test_curation_provider_keeps_independent_reads_and_output(self):
        calls = []
        def provider(protocol, fingerprints):
            calls.append((protocol, fingerprints))
            return {self.service.ids[0]: {'included': False, 'review_state': 'approved'}}
        self.service.curation_provider = provider
        result, reads = self.measured(lambda: self.service.protocol(self.protocol))
        self.assertEqual(len(calls), 2)
        self.assertEqual(reads, 6)
        self.assertEqual(result['counts']['included'], 1)
        self.assertEqual(result['counts']['reviewed'], 1)

    def test_custom_binding_mutation_keeps_legacy_snapshot_sequence(self):
        calls = []
        def provider(protocol):
            calls.append(protocol)
            if len(calls) == 1:
                self.service.protocols[protocol]['result']['epochs'].pop()
            return None
        self.service.binding_provider = provider
        result = self.service.protocol(self.protocol)
        self.assertEqual(calls, [self.protocol] * 4)
        self.assertEqual(result['counts']['epochs'], 2)
        self.assertEqual(result['total_counts']['epochs'], 1)

    def test_frozen_target_does_not_hide_custom_foreign_reader(self):
        other = self.add_protocol()
        calls = []
        def foreign(protocol):
            calls.append(protocol)
            return None
        self.service.binding_provider = _FrozenProtocolBinding(self.protocol, None, foreign)
        _, reads = self.measured(lambda: self.service.protocol(self.protocol))
        self.assertEqual(reads, 5)
        self.assertEqual(calls, [other])

    def test_annotation_filters_keep_legacy_reads(self):
        result, calls = self.measured(lambda: self.service.protocol(self.protocol, {'tag': 'absent'}))
        self.assertEqual(calls, 4)
        self.assertEqual(result['counts']['epochs'], 0)
        self.assertEqual(result['total_counts']['epochs'], 2)

    def test_http_summary_and_page_keep_independent_state_reads(self):
        with patch.object(self.service, 'filtered_rows', wraps=self.service.filtered_rows):
            expected, old_calls = self.measured(lambda: self.case.client.get(self.case.base).get_json())
        actual, calls = self.measured(lambda: self.case.client.get(self.case.base).get_json())
        self.assertEqual(actual, expected)
        self.assertEqual((old_calls, calls), (7, 4))
        page, page_calls = self.measured(lambda: self.case.client.get(self.case.base + '/epochs').get_json())
        self.assertEqual(page_calls, 2)
        self.assertEqual(page['query_revision'], actual['query_revision'])
        self.assertEqual({row['epoch_uuid'] for row in page['epochs']}, set(self.service.ids))

    def test_interrupted_pin_still_refused(self):
        self.service.protocols[self.protocol]['definition']['initial_revision_uuid'] = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            self.service.protocol(self.protocol)


if __name__ == '__main__':
    unittest.main()
