"""Owned authority adapter preserves production capture/rollback/refusal semantics."""
from types import SimpleNamespace
import unittest

from benchmarks.workflow.publication_fixture import install_authority, journal_transactions
import test_workspace_api as api_fixture


class PublicationAuthorityFixtureTests(unittest.TestCase):
    def setUp(self):
        self.case = api_fixture.WorkspaceAPITests(); self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        fixture = SimpleNamespace(case=self.case, addCleanup=self.addCleanup)
        self.journal = journal_transactions(fixture)
        self.tracker = install_authority(fixture, self.case.app, self.journal, install_state=True)
        self.project = self.case.service.project['project_uuid']
        self.protocol = self.case.service.protocol_id

    def row(self, identity='epoch-one'):
        return {'project_uuid': self.project, 'protocol_uuid': self.protocol, 'epoch_uuid': identity,
                'included': True, 'tags': [], 'review_state': 'unreviewed', 'metadata_fingerprint': 'b' * 64}

    def test_complete_capture_deduplicates_update_old_and_new_keys(self):
        before = self.tracker.token()
        with self.case.connection.transaction:
            self.case.curation.insert1(self.row())
            self.case.curation.update1({**self.row(), 'included': False})
        with self.tracker.capture(before) as plan:
            self.assertTrue(plan.complete)
            self.assertEqual(plan.keys['curation'], [(self.project, self.protocol, 'epoch-one')])
            self.assertEqual(plan.watermark['generation'], 3)
            self.assertFalse(self.case.curation.to_dicts()[0]['included'])
            plan.verify()
        self.assertEqual(self.tracker.token(), plan.watermark)

    def test_rollback_restores_feed_clock_and_after_images(self):
        before = self.tracker.token()
        with self.assertRaisesRegex(RuntimeError, 'rollback'):
            with self.case.connection.transaction:
                self.case.curation.insert1(self.row())
                raise RuntimeError('rollback')
        self.assertEqual(self.tracker.token(), before)
        self.assertEqual(self.case.curation.to_dicts(), [])
        with self.tracker.capture(before) as plan:
            self.assertTrue(plan.complete)
            self.assertEqual(plan.keys['curation'], [])

    def test_initial_and_limited_capture_never_claim_complete_delta(self):
        before = self.tracker.token()
        with self.tracker.capture() as plan:self.assertFalse(plan.complete)
        with self.case.connection.transaction:
            self.case.curation.insert1(self.row('one'))
            self.case.curation.insert1(self.row('two'))
        with self.tracker.capture(before, limit=1) as plan:self.assertFalse(plan.complete)

    def test_fixed_ring_retention_refuses_an_older_watermark(self):
        from disco.backup.recovery_generation import RECOVERY_WINDOW
        before = self.tracker.token()
        with self.case.connection.transaction:
            self.case.curation.insert1(self.row())
            for number in range(RECOVERY_WINDOW // 2):
                self.case.curation.update1({**self.row(), 'included': bool(number % 2)})
        with self.tracker.capture(before) as plan:self.assertFalse(plan.complete)
        feed = self.case.app.extensions['benchmark_recovery_authority']['feed']
        self.assertEqual(len(feed), RECOVERY_WINDOW)

    def test_declared_layout_uses_saved_view_owner_without_membership_changes(self):
        from benchmarks.workflow.publication_fixture import declare_saved_layout
        import copy
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        fixture = SimpleNamespace(case=self.case)
        receipt = declare_saved_layout(fixture, self.case.app)
        self.assertEqual(receipt['split_order'], ['date', 'cell', 'block'])
        self.assertFalse(receipt['membership_changed'])
        self.assertEqual(self.case.protocol_bindings.rows, before)
        self.assertEqual(self.case.app.extensions['tree_layouts'].read(self.protocol)['version'], 1)

    def test_changed_clock_refuses_and_rolls_back_capture(self):
        before = self.tracker.token()
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            with self.tracker.capture(before) as plan:
                self.case.curation.insert1(self.row())
                plan.verify()
        self.assertEqual(self.case.curation.to_dicts(), [])
        with self.tracker.capture(before) as plan:self.assertFalse(plan.complete)


class PublicationFixtureModeTests(unittest.TestCase):
    def test_workflow_comparison_refuses_mixed_admissions(self):
        from unittest.mock import patch
        from tools import benchmark_workflow
        with patch.object(benchmark_workflow, 'load_receipt', side_effect=[
                {'suite': 'app', 'prepared_publication': False},
                {'suite': 'app', 'prepared_publication': True}]):
            with self.assertRaisesRegex(ValueError, 'publication fixture modes'):
                benchmark_workflow.compare(None, None, None)


if __name__ == '__main__':unittest.main()
