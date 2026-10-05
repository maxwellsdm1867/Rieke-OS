"""Current-path public examples; stdlib only, no worker or database starts."""
import threading
import unittest
from unittest.mock import Mock, patch

import disco.backup.backup_scheduler as backup
import workspace_state_snapshot as snapshot


class RecoveryPublicTests(unittest.TestCase):
    def scheduler(self, capture):
        with patch.object(backup.threading, 'Thread'):
            return backup.BackupScheduler(capture, threading.RLock())

    def test_failed_close_retains_pending_and_can_retry(self):
        scheduler = self.scheduler(Mock(side_effect=[OSError('full'), None]))
        scheduler.request()
        with self.assertRaisesRegex(OSError, 'full'):
            scheduler.close()
        self.assertEqual(scheduler.status()['status'], 'degraded')
        self.assertTrue(scheduler.status()['pending'])
        scheduler.close()
        self.assertEqual(scheduler.status()['status'], 'current')

    def test_request_during_capture_is_not_claimed_as_covered(self):
        capture = Mock()
        scheduler = self.scheduler(capture)
        capture.side_effect = scheduler.request
        scheduler.request()
        status = scheduler.flush()
        self.assertEqual((status['requested_sequence'], status['completed_sequence']), (2, 1))
        self.assertTrue(status['pending'])

    def test_flush_captures_even_without_a_queued_edit(self):
        capture = Mock()
        self.scheduler(capture).flush()
        capture.assert_called_once_with()

    def test_restore_orders_dependencies_even_for_sorted_input(self):
        tables = dict.fromkeys(sorted(['workbench_decision', 'protocol_binding',
                                     'explorer_revision', 'workbench_draft', 'curation']))
        self.assertEqual(snapshot.restore_table_order(tables), ['curation',
                         'explorer_revision', 'protocol_binding', 'workbench_draft', 'workbench_decision'])

    def test_receipt_binding_keeps_its_revision_reachable(self):
        roots = snapshot.revision_roots({'workbench_receipt': [
            {'candidate_revision_uuid': 'candidate', 'receipt': {'binding': {'revision_uuid': 'bound'}}}
        ]}, {'p': {'initial_revision_uuid': 'initial'}})
        self.assertEqual(roots, {'candidate', 'bound', 'initial'})
