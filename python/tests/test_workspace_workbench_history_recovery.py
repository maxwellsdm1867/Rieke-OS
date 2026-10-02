"""Reproduce stale duplicate origins without touching native or live data."""
import copy
import uuid
import unittest

import test_workspace_workbench_pending as cumulative


class HistoricalProposalRecoveryTests(unittest.TestCase):
    setUp = cumulative.CumulativePendingTests.setUp
    queue = cumulative.CumulativePendingTests.queue
    prepare = cumulative.CumulativePendingTests.prepare
    get_context = cumulative.CumulativePendingTests.get_context

    def test_fresh_proposal_recovers_exact_additions_while_stale_origin_stays_immutable(self):
        original = self.manager.context(self.protocol, self.revision, 'actor-one')
        old_recipe = copy.deepcopy(original['candidate'])
        baseline = original['baseline']
        changed = next(iter(original['previous']))
        self.case.service._fingerprints[changed] = 'c' * 64
        # Simulate an explicitly reconciled main with refreshed metadata, followed
        # by another import proposal. The historical proposal stays immutable.
        preview = self.case.service.explore_preview(baseline['predicate'], baseline['splits'])
        preview['membership'] = [dict(uuid=key, metadata_hash=self.case.service._fingerprints[key])
                                 for key in original['previous']]
        preview['matched_count'] = len(preview['membership'])
        main = self.manager.history.create(preview, self.case.service.sources,
            self.case.service.project_dir / 'catalog.json', 'fixture', parent_revision_uuid=baseline['revision_uuid'])
        self.manager.history.bind(main['revision_uuid'], self.protocol, original['expected_binding_version'],
            'fixture', dict(added=[], removed=[], changed=[changed]), len(original['previous']))
        baselines = self.case.protocol_suggestions.freeze_baselines('actor-one', self.manager.state)
        rerun = self.case.protocol_suggestions.rerun(baselines, self.fixture.source_sha, 'fresh.h5', 'actor-one')
        self.assertEqual(rerun['counts']['created_count'], 1, rerun)
        fresh_revision = rerun['suggestions'][0]['candidate_revision_uuid']
        stale = self.manager.context(self.protocol, self.revision, 'actor-one')
        fresh = self.manager.context(self.protocol, fresh_revision, 'actor-one')
        self.assertFalse(stale['valid_base'])
        self.assertIn(changed, stale['unavailable'])
        self.assertEqual(stale['pending'], fresh['pending'])
        self.assertTrue(fresh['valid_base'])
        self.assertEqual(fresh['pending'], {self.added: 'b' * 64})
        # Preparation correctly refuses the old original. It creates no record.
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        denied = self.case.client.post(self.case.base + '/workbench/prepare', json=dict(
            expected_queue_revision=self.queue()['queue_revision']), headers=self.case.headers)
        self.assertEqual(denied.status_code, 409)
        self.assertIn('unmerged original proposal', denied.get_json()['error'])
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        # Existing per-proposal routes provide explicit, fenced recovery; no
        # historical rewrite, replacement acceptance or implicit union needed.
        root = self.case.base + '/workbench/candidates/' + fresh_revision
        context = self.get_context(root)
        self.assertFalse(context['publication_blocked'])
        context = self.case.client.patch(root + '/draft', json=dict(expected_version=context['draft']['draft_version'],
            expected_candidate_scope_revision=context['candidate_scope_revision'], selection_mode='all', decisions=[]),
            headers=self.case.headers).get_json()
        request = dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode='all')
        proposal = self.case.client.post(root + '/preview', json=request, headers=self.case.headers)
        self.assertEqual(proposal.status_code, 200, proposal.get_json())
        self.assertEqual(proposal.get_json()['accepted_epoch_count'], 1)
        self.assertEqual(proposal.get_json()['retained_epoch_count'], len(original['previous']))
        self.assertEqual(self.manager.history.protocol_binding(self.protocol)['revision_uuid'], main['revision_uuid'])
        request.update({key: proposal.get_json()[key] for key in ('preview_sha256', 'expected_binding_version', 'expected_query_revision')}, operation_uuid=str(uuid.uuid4()))
        accepted = self.case.client.post(root + '/accept', json=request, headers=self.case.headers)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        self.assertEqual(accepted.get_json()['accepted_epoch_uuids'], [self.added])
        self.assertEqual(self.manager.history.get(self.revision)['recipe'], old_recipe)
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        prepared, _ = self.prepare()
        self.assertEqual(prepared['context']['counts']['pending_epochs'], 0)
