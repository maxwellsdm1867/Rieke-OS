"""Reversible source retirement and atomic protocol updates; no research DB."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

if __package__:
    from . import test_workspace_api as api_tests
else:
    import test_workspace_api as api_tests


class PropagationTests(unittest.TestCase):
    def setUp(self):
        self.case = api_tests.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.client, self.service = self.case.client, self.case.service
        self.headers = self.case.headers
        self.source = 'a' * 64
        self.base = '/api/data-stores/' + self.source
        Path(self.service.sources[0]['source_path']).write_bytes(b'disposable propagation fixture')

    def change(self, action, version):
        response = self.client.post(self.base + '/state', json={
            'action': action, 'expected_version': version, 'reason': 'Propagation test'}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())

    def plan(self):
        response = self.client.post(self.base + '/propagation-preview', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['protocols'][0]

    def apply(self, item):
        return self.client.post(self.base + '/propagate', json={
            'protocol_uuid': item['protocol_uuid'], 'expected_preview_revision': item['expected_preview_revision']},
            headers=self.headers)

    def test_exclusion_removes_from_new_queries_then_propagates_and_inclusion_readds(self):
        original = copy.deepcopy(self.service.rows)
        exported = self.client.post(self.case.base + '/exports', json={
            'query_revision': self.case.revision(), 'review_policy': 'include_unreviewed'}, headers=self.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        old_record = self.case.store.get_dataset_revision(exported.get_json()['dataset_uuid'])
        old_artifact = Path(old_record['artifact_path']).read_bytes()
        self.change('exclude', 0)
        current = self.client.get(self.case.base).get_json()
        self.assertEqual(current['counts']['epochs'], 2)
        self.assertTrue(current['source_eligibility']['propagation_required'])
        query = self.client.post('/api/explore/preview', json={'predicate': {'all': []}, 'splits': 'date'}, headers=self.headers)
        self.assertEqual(query.get_json()['matched_count'], 0)
        blocked = self.client.post(self.case.base + '/exports', json={
            'query_revision': current['query_revision'], 'review_policy': 'include_unreviewed'}, headers=self.headers)
        self.assertEqual(blocked.status_code, 409, blocked.get_json())
        item = self.plan()
        self.assertEqual(item['diff_counts'], {'added': 0, 'removed': 2, 'changed': 0})
        result = self.apply(item)
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual(self.client.get(self.case.base).get_json()['counts']['epochs'], 0)
        self.assertFalse(self.client.get(self.case.base).get_json()['source_eligibility']['propagation_required'])
        recipe = self.case.explorer_history.get(result.get_json()['revision_uuid'])['recipe']
        self.assertEqual(recipe['source_scope']['active_source_revisions'], [])
        self.assertEqual(recipe['source_revisions'], [])
        self.assertEqual(Path(old_record['artifact_path']).read_bytes(), old_artifact)
        self.change('include', 1)
        self.assertEqual(self.client.get(self.case.base).get_json()['counts']['epochs'], 0)
        item = self.plan()
        self.assertEqual(item['diff_counts']['added'], 2)
        restored = self.apply(item)
        self.assertEqual(restored.status_code, 200, restored.get_json())
        self.assertEqual(restored.get_json()['binding_version'], 2)
        self.assertEqual(self.client.get(self.case.base).get_json()['counts']['epochs'], 2)
        self.assertEqual(self.service.rows, original)
        self.assertEqual(Path(old_record['artifact_path']).read_bytes(), old_artifact)

    def test_stale_propagation_token_cannot_overwrite_new_source_state(self):
        self.change('exclude', 0)
        item = self.plan()
        self.change('include', 1)
        before = len(self.case.events.rows)
        response = self.apply(item)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertFalse(self.case.protocol_bindings.rows)
        self.assertFalse(self.case.explorer_revisions.rows)
        self.assertEqual(len(self.case.events.rows), before)

    def test_saved_empty_candidate_is_stale_when_source_universe_changes(self):
        saved = self.client.post('/api/explore/revisions', json={
            'predicate': {'field': 'protocol', 'operator': 'eq', 'value': 'does-not-match'}, 'splits': 'date'}, headers=self.headers)
        self.assertEqual(saved.status_code, 201, saved.get_json())
        self.change('exclude', 0)
        response = self.client.post('/api/explore/revisions/' + saved.get_json()['revision_uuid'] + '/compare-to-protocol',
            json={'protocol_uuid': self.service.protocol_id}, headers=self.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertFalse(self.case.protocol_bindings.rows)

    def test_archiving_list_entry_does_not_change_query_revision_or_membership(self):
        before = self.case.revision()
        self.change('archive', 0)
        self.assertEqual(self.case.revision(), before)
        query = self.client.post('/api/explore/preview', json={'predicate': {'all': []}, 'splits': 'date'}, headers=self.headers)
        self.assertEqual(query.get_json()['matched_count'], 2)
        self.assertFalse(self.client.get(self.case.base).get_json()['source_eligibility']['propagation_required'])

    def test_legacy_tree_adaptation_is_recorded_with_the_new_binding(self):
        self.service.protocols[self.service.protocol_id]['definition']['view']['group_by'] = ['cell.type', 'cell.start_time']
        self.change('exclude', 0)
        item = self.plan()
        self.assertEqual(item['view_adaptation']['applied_group_by'], ['date', 'cell', 'block'])
        response = self.apply(item)
        self.assertEqual(response.status_code, 200, response.get_json())
        recipe = self.case.explorer_history.get(response.get_json()['revision_uuid'])['recipe']
        self.assertEqual(recipe['view_adaptation'], item['view_adaptation'])

    def test_binding_audit_failure_rolls_back_candidate_and_binding(self):
        self.change('exclude', 0)
        item = self.plan()
        before = copy.deepcopy(self.case.events.rows)
        insert = self.case.events.insert1
        def fail_binding(row):
            if row['action'] == 'protocol_dataset_bound':
                raise RuntimeError('Injected binding audit failure')
            insert(row)
        with patch.object(self.case.events, 'insert1', side_effect=fail_binding):
            response = self.apply(item)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.case.events.rows, before)
        self.assertFalse(self.case.protocol_bindings.rows)
        self.assertFalse(self.case.explorer_revisions.rows)
        self.assertEqual(self.client.get(self.case.base).get_json()['counts']['epochs'], 2)
