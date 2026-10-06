"""Full-change proposal public HTTP workflows on isolated transactional doubles."""
import copy
import uuid
import unittest
from unittest.mock import patch

import test_workspace_workbench as workbench_tests


class ReplacementTests(unittest.TestCase):
    setUp = workbench_tests.WorkbenchTests.setUp
    get_context = workbench_tests.WorkbenchTests.get_context
    save = workbench_tests.WorkbenchTests.save
    accepted_request = workbench_tests.WorkbenchTests.accepted_request
    accept = workbench_tests.WorkbenchTests.accept

    def propose(self, predicate=None):
        predicate = predicate or {'field': 'parameters/example', 'operator': 'eq', 'value': 0}
        saved = self.case.client.post('/api/explore/revisions', json=dict(predicate=predicate, splits='cell', name='Narrow'), headers=self.case.headers)
        self.assertEqual(saved.status_code, 201, saved.get_json())
        revision = saved.get_json()['revision_uuid']
        root = '/api/explore/revisions/' + revision
        compared = self.case.client.post(root + '/compare-to-protocol', json=dict(protocol_uuid=self.protocol), headers=self.case.headers).get_json()
        body = dict(protocol_uuid=self.protocol, operation_uuid=str(uuid.uuid4()),
            **{key: compared[key] for key in ('expected_binding_version', 'expected_query_revision')})
        response = self.case.client.post(root + '/propose-to-protocol', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json(), root, body

    def replacement_request(self, proposal):
        root = '/api' + proposal['root']
        response = self.case.client.get(root + '/replacement-preview')
        self.assertEqual(response.status_code, 200, response.get_json())
        value = response.get_json()
        return root, value, dict(operation_uuid=str(uuid.uuid4()), confirm_removals=True,
            **{key: value[key] for key in ('expected_candidate_scope_revision', 'expected_binding_version', 'expected_query_revision', 'preview_sha256')})

    def test_predicate_submission_is_inert_and_acceptance_removes_exact_members_with_replay(self):
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        proposal, source_root, submit_body = self.propose()
        self.assertEqual(self.case.protocol_bindings.rows, before)
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        self.assertEqual(len(queue['replacement_reviews']), 1)
        self.assertGreater(queue['pending_epoch_count'], 0)
        repeat = self.case.client.post(source_root + '/propose-to-protocol', json=submit_body, headers=self.case.headers)
        self.assertEqual(repeat.get_json(), proposal)
        root, value, body = self.replacement_request(proposal)
        self.assertEqual(value['diff_counts'], dict(added=1, removed=1, changed=0))
        self.assertEqual(value['diff_summary']['cell_changes']['counts'], dict(added=1, removed=1, updated=0))
        refused = self.case.client.post(root + '/replacement-accept', json={**body, 'confirm_removals': False}, headers=self.case.headers)
        self.assertEqual(refused.status_code, 400, refused.get_json())
        self.assertEqual(self.case.protocol_bindings.rows, before)
        accepted = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        count = len(self.case.events.rows)
        with patch.object(self.manager, 'proposal', side_effect=ValueError('Unavailable candidate')):
            repeated = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(repeated.get_json(), accepted.get_json())
        self.assertEqual(len(self.case.events.rows), count)
        binding = self.case.explorer_history.protocol_binding(self.protocol)
        self.assertEqual(binding['revision_uuid'], proposal['candidate_revision_uuid'])
        self.assertEqual(len(binding['recipe']['epochs']), value['next_count'])
        changed = self.case.client.post(root + '/replacement-accept', json={**body, 'confirm_removals': False}, headers=self.case.headers)
        self.assertEqual(changed.status_code, 409)

    def test_remove_all_and_legacy_additive_bypass_refused(self):
        proposal, _, _ = self.propose({'field': 'parameters/example', 'operator': 'eq', 'value': 999})
        root, value, body = self.replacement_request(proposal)
        self.assertEqual(value['next_count'], 0)
        self.assertTrue(value['compatibility']['compatible'])
        self.assertEqual(self.case.client.get(root + '/context').status_code, 400)
        legacy = self.case.client.post('/api/explore/revisions/' + proposal['candidate_revision_uuid'] + '/apply-to-protocol',
            json=dict(protocol_uuid=self.protocol, expected_binding_version=value['expected_binding_version'], expected_query_revision=value['expected_query_revision']), headers=self.case.headers)
        self.assertEqual(legacy.status_code, 400)
        accepted = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        self.assertEqual(self.case.explorer_history.protocol_binding(self.protocol)['recipe']['epochs'], [])

    def test_stale_baseline_rejects_and_does_not_rebase_removal_over_new_additions(self):
        proposal, _, _ = self.propose()
        root, _, body = self.replacement_request(proposal)
        self.assertEqual(self.accept(self.accepted_request()).status_code, 200)
        refused = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(refused.status_code, 409, refused.get_json())
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        self.assertEqual(queue['replacement_reviews'][0]['status'], 'superseded')
        self.assertEqual(queue['replacement_pending_count'], 0)
        self.assertEqual(queue['replacement_pending_epoch_count'], 0)

    def test_h5_removal_only_is_replacement_not_covered_or_cumulative(self):
        suggestion = self.case.suggestion_rows.rows[0]['summary']
        candidate = self.case.explorer_history.get(self.revision)['recipe']
        base = self.case.explorer_history.protocol_binding(self.protocol)['recipe']
        frozen = dict(predicate=base['predicate'], splits=base['splits'], membership=base['epochs'][:1], matched_count=1,
            total_source=len(self.case.service.rows), metadata_fingerprint_version=2, source_scope=candidate['source_scope'],
            source_revisions=candidate['source_revisions'], tree=dict(split_order=base['tree_view']['fields']))
        record = self.case.explorer_history.create(frozen, self.case.service.sources, self.case.service.project_dir / 'catalog.json',
            'fixture', parent_revision_uuid=base['revision_uuid'])
        suggestion.update(candidate_revision_uuid=record['revision_uuid'], diff_counts=dict(added=0, removed=1, changed=0))
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        self.assertEqual(queue['candidates'], [])
        self.assertEqual(queue['replacement_reviews'][0]['status'], 'pending')
        self.assertEqual(queue['pending_epoch_count'], 0)
        self.assertEqual(queue['replacement_pending_epoch_count'], 1)
        self.assertEqual(queue['replacement_pending_count'], 1)
        self.assertEqual(queue['total_pending_epoch_count'], 1)
        self.assertEqual(queue['replacement_pending_cell_count'], 1)
        summary = self.case.client.get('/api/workbench/summary').get_json()['workbench_counts'][0]
        self.assertEqual(summary['pending_cell_count'], 1)

    def test_accept_audit_failure_rolls_back_binding_and_receipt(self):
        proposal, _, _ = self.propose()
        root, _, body = self.replacement_request(proposal)
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        receipts = copy.deepcopy(self.tables[2].rows)
        with patch.object(self.manager, '_event', side_effect=RuntimeError('injected audit failure')):
            response = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.case.protocol_bindings.rows, before)
        self.assertEqual(self.tables[2].rows, receipts)
        retry = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(retry.status_code, 200, retry.get_json())

    def test_changed_fingerprint_and_wrong_actor_fail_closed(self):
        proposal, _, _ = self.propose()
        root, _, body = self.replacement_request(proposal)
        candidate = self.case.explorer_history.get(proposal['candidate_revision_uuid'])['recipe']
        identity = candidate['epochs'][0]['uuid']
        old = self.case.service._fingerprints[identity]
        self.case.service._fingerprints[identity] = 'c' * 64
        response = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 409)
        self.case.service._fingerprints[identity] = old
        accepted = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        with patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'actor-two'}):
            response = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 409)

    def test_old_cumulative_snapshot_cannot_bypass_full_change_origin(self):
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        prepared = self.case.client.post(self.case.base + '/workbench/prepare',
            json=dict(expected_queue_revision=queue['queue_revision']), headers=self.case.headers)
        self.assertEqual(prepared.status_code, 201, prepared.get_json())
        # Simulate a legacy prepared scope whose original proposal must now be
        # routed to full-change review. Its sealed recipe/provenance is unchanged.
        self.case.suggestion_rows.rows[0]['summary']['diff_counts']['removed'] = 1
        context = self.case.client.get('/api' + prepared.get_json()['root'] + '/context')
        self.assertEqual(context.status_code, 409, context.get_json())

    def test_source_and_shared_annotation_change_invalidate_preview(self):
        shared = workbench_tests.WorkbenchTests.coverage_annotations(self)
        proposal, _, _ = self.propose()
        root, _, body = self.replacement_request(proposal)
        source = self.case.service.rows[self.added]['source_sha256']
        self.case.data_store_states.insert1(dict(project_uuid=self.manager.project, source_sha256=source,
            query_excluded=True, archived=False, frozen=False, version=1, updated_at=None,
            actor='actor-one', server_actor='actor-one', reason='test'))
        response = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.case.data_store_states.rows.clear()
        shared = self.case.service.shared_annotations
        with patch.object(shared, 'snapshot', return_value={**shared.snapshot(), 'revision': 'changed-shared-tags'}):
            response = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())

    def test_predicate_only_change_installs_method_for_next_h5_rerun(self):
        self.assertEqual(self.accept(self.accepted_request()).status_code, 200)
        predicate = {'all': [{'field': 'protocol', 'operator': 'eq', 'value': 'example'}]}
        proposal, _, _ = self.propose(predicate)
        root, value, body = self.replacement_request(proposal)
        self.assertEqual(value['diff_counts'], dict(added=0, removed=0, changed=0))
        summary = self.case.client.get('/api/workbench/summary').get_json()['workbench_counts'][0]
        self.assertEqual(summary['pending_cell_count'], 0)
        self.assertEqual(summary['pending_proposal_count'], 1)
        response = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.case.explorer_history.protocol_binding(self.protocol)['recipe']['predicate'], predicate)
        self.fixture.source_sha = 'd' * 64
        self.fixture.add_recording()
        baselines = self.case.protocol_suggestions.freeze_baselines('actor-one', self.manager.state)
        with patch.object(self.case.service, 'explore_preview', wraps=self.case.service.explore_preview) as query:
            result = self.case.protocol_suggestions.rerun(baselines, self.fixture.source_sha, 'next.h5', 'actor-one')
        self.assertEqual(query.call_args.args[0], predicate)
        self.assertEqual(result['counts']['created_count'], 1, result)
        self.assertEqual(result['suggestions'][0]['diff_counts'], dict(added=1, removed=0, changed=0))

    def test_unbound_starter_freezes_current_membership_before_queuing_predicate(self):
        self.case.protocol_bindings.rows.clear()
        before = self.case.client.get(self.case.base).get_json()['counts']['epochs']
        proposal, _, _ = self.propose()
        binding = self.case.explorer_history.protocol_binding(self.protocol)
        self.assertEqual(len(binding['recipe']['epochs']), before)
        self.assertNotEqual(binding['revision_uuid'], proposal['candidate_revision_uuid'])
        self.assertEqual(self.case.client.get(self.case.base).get_json()['counts']['epochs'], before)
        self.assertEqual(proposal['proposal']['baseline_revision_uuid'], binding['revision_uuid'])

    def test_full_change_and_proposal_receipts_refuse_incoming_export_cleanly(self):
        proposal, _, _ = self.propose()
        root, _, body = self.replacement_request(proposal)
        accepted = self.case.client.post(root + '/replacement-accept', json=body, headers=self.case.headers)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        for operation in (proposal['operation_uuid'], body['operation_uuid']):
            receipt_root = self.case.base + '/workbench/receipts/' + operation
            context = self.case.client.get(receipt_root + '/export-context')
            self.assertEqual(context.status_code, 400, context.get_json())
            self.assertIn('additive acceptance receipt', context.get_json()['error'])
            exported = self.case.client.post(receipt_root + '/exports', json=dict(
                expected_export_scope_revision='not-an-export-scope', format='reference-json',
                operation_uuid=str(uuid.uuid4())), headers=self.case.headers)
            self.assertEqual(exported.status_code, 400, exported.get_json())
        self.assertEqual(self.case.protocol_bindings.rows, before)
        self.assertFalse(self.case.datasets.rows)
