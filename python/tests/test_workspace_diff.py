import copy
import unittest

from workspace_diff import summarize_diff


class MembershipSummaryTests(unittest.TestCase):
    def row(self, cell, protocol='A', duration=1.0):
        return {'cell_uuid': cell, 'cell_label': cell, 'cell_type': 'recorded type',
                'date': '2026-09-24', 'start_time': '09/24/2026 12:00:00:000000',
                'protocol_name': protocol, 'duration_seconds': duration}

    def test_extra_epochs_in_existing_cell_are_not_new_cells(self):
        rows = {'a': self.row('Cell1'), 'b': self.row('Cell2'), 'c': self.row('Cell1', 'B', 2.5)}
        original = copy.deepcopy(rows)
        summary = summarize_diff(rows, {'a': 'x', 'b': 'x'}, {'a': 'x', 'b': 'x', 'c': 'y'})
        self.assertEqual(summary['current'], {'epochs': 2, 'cells': 2, 'acquisition_protocols': 1, 'duration_seconds': 2.0})
        self.assertEqual(summary['proposed'], {'epochs': 3, 'cells': 2, 'acquisition_protocols': 2, 'duration_seconds': 4.5})
        self.assertEqual(summary['delta'], {'epochs': 1, 'cells': 0, 'acquisition_protocols': 1, 'duration_seconds': 2.5})
        changes = summary['cell_changes']
        self.assertEqual(changes['counts'], {'added': 0, 'removed': 0, 'updated': 1})
        updated = changes['updated'][0]
        self.assertEqual((updated['cell_uuid'], updated['previous_epoch_count'], updated['proposed_epoch_count']), ('Cell1', 1, 2))
        self.assertEqual((updated['epochs_added'], updated['epochs_removed'], updated['epochs_changed']), (1, 0, 0))
        self.assertEqual(rows, original)

    def test_new_and_removed_cells_and_metadata_changes_are_distinct(self):
        rows = {'a': self.row('Cell1'), 'b': self.row('Cell2'), 'c': self.row('Cell3', 'B')}
        summary = summarize_diff(rows, {'a': 'x', 'b': 'x'}, {'a': 'changed', 'c': 'x'})
        self.assertEqual(summary['delta']['cells'], 0)  # One new and one removed, not no cell changes.
        changes = summary['cell_changes']
        self.assertEqual(changes['counts'], {'added': 1, 'removed': 1, 'updated': 1})
        self.assertEqual(changes['added'][0]['cell_uuid'], 'Cell3')
        self.assertEqual(changes['removed'][0]['cell_uuid'], 'Cell2')
        self.assertEqual(changes['removed'][0]['epoch_count'], 1)
        self.assertEqual(changes['removed'][0]['proposed_epoch_count'], 0)
        self.assertEqual(changes['updated'][0]['epochs_changed'], 1)
        new = summarize_diff(rows, {'a': 'x'}, {'a': 'x', 'c': 'x'})
        self.assertEqual(new['delta']['cells'], 1)
        self.assertEqual(new['delta']['acquisition_protocols'], 1)

    def test_detail_cap_never_truncates_aggregate_counts(self):
        rows = {str(i): self.row('Cell' + str(i), 'Protocol' + str(i % 3)) for i in range(105)}
        summary = summarize_diff(rows, {}, dict.fromkeys(rows, 'hash'))
        self.assertEqual(summary['proposed']['cells'], 105)
        self.assertEqual(summary['proposed']['epochs'], 105)
        self.assertEqual(summary['proposed']['acquisition_protocols'], 3)
        self.assertEqual(summary['cell_changes']['counts']['added'], 105)
        self.assertEqual(len(summary['cell_changes']['added']), 100)
        self.assertTrue(summary['cell_changes']['truncated']['added'])
        self.assertFalse(summary['cell_changes']['truncated']['updated'])

    def test_unavailable_metadata_and_invalid_bounds_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            summarize_diff({}, {'missing': 'hash'}, {})
        for limit in (0, 101, True, 1.1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                summarize_diff({}, {}, {}, limit)
