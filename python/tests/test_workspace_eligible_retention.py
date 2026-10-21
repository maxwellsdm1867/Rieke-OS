"""Eligible snapshots preserve scope while avoiding new GC-retained row/set graphs."""
import gc
import tempfile
import unittest
from unittest.mock import patch

from test_workspace_api import FixtureService
from workspace_service import WorkspaceService, publish_frozen


class EligibleRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FixtureService(self.temp.name)
        self.service._explore_publication = 'first'

    def freeze(self):
        for name in ('rows', 'cells', 'protocols', '_fingerprints'):
            setattr(self.service, name, publish_frozen(getattr(self.service, name), rows=name == 'rows'))

    def test_canonical_mutable_rows_keep_snapshot_and_all_set_operations(self):
        rows, ids, scope, universe = self.service._eligible()
        self.assertIsInstance(rows, tuple)
        expected = frozenset(ids)
        for other in (set(), {ids[0]}, set(ids), {'outside'}, {ids[0], 'outside'}):
            self.assertEqual(universe & other, expected & other)
            self.assertEqual(other & universe, other & expected)
            self.assertEqual(universe - other, expected - other)
            self.assertEqual(other - universe, other - expected)
            self.assertEqual(universe | other, expected | other)
            self.assertEqual(universe ^ other, expected ^ other)
            self.assertEqual(universe <= other, expected <= other)
            self.assertEqual(universe >= other, expected >= other)
        self.assertEqual(universe, expected)
        self.assertEqual(set(universe), set(ids))
        self.assertIs(self.service._eligible()[1], ids)
        with self.assertRaises(AttributeError):
            universe.add('outside')
        with self.assertRaises(TypeError):
            universe.mapping['outside'] = None
        self.service.rows = {key: row for key, row in self.service.rows.items() if key != ids[0]}
        self.assertEqual(universe, expected, 'retained snapshot must not follow a republished map')
        self.assertNotIn(ids[0], self.service._eligible()[3])

    def test_frozen_rows_capture_old_map_and_keep_sequence_order_and_slices(self):
        self.freeze()
        old = self.service.rows
        rows, ids, _, universe = self.service._eligible()
        expected = tuple(old[key] for key in ids)
        self.assertEqual(tuple(rows), expected)
        self.assertEqual(rows[-1], expected[-1])
        self.assertEqual(rows[::-1], expected[::-1])
        self.assertEqual(len(rows), len(expected))
        with self.assertRaises(TypeError):
            rows[0] = {}
        replacement = {key: dict(row, cell_label='replacement') for key, row in old.items()}
        self.service.rows = publish_frozen(replacement, rows=True)
        fresh = self.service._eligible()
        self.assertIsNot(fresh[1], ids)
        self.assertIs(rows[0], old[ids[0]])
        self.assertEqual(fresh[0][0]['cell_label'], 'replacement')
        self.assertEqual(universe, set(ids))

    def test_source_and_publication_changes_replace_cached_scope(self):
        before = self.service._eligible()
        self.service._explore_publication = 'second'
        self.assertIsNot(self.service._eligible()[1], before[1])
        source = self.service.sources[0]['source_sha256']
        with patch.object(self.service, 'source_state_provider',
                          lambda: {source: {'archived': False, 'query_excluded': True, 'version': 1}}, create=True):
            current = self.service._eligible()
            self.assertEqual(tuple(current[0]), ())
            self.assertEqual(current[1], ())
            self.assertEqual(current[3], set())
        self.assertEqual(before[3], set(before[1]))

    def test_custom_filter_retains_its_original_order_and_tuple_frozenset_contract(self):
        self.freeze()
        with patch.object(self.service, '_filter_rows', side_effect=lambda rows, filters: list(reversed(rows))):
            rows, ids, _, universe = self.service._eligible()
            self.assertIsInstance(rows, tuple)
            self.assertIsInstance(universe, frozenset)
            self.assertEqual(ids, tuple(reversed(self.service.ids)))

    def test_atomic_universe_does_not_retain_gc_traversable_member_table(self):
        # This is a structural reachability check, not a latency assertion or GC-policy change.
        for frozen in (False, True):
            if frozen:
                self.freeze()
            self.service._explore_publication = str(frozen)
            rows, ids, _, universe = self.service._eligible()
            owners = gc.get_referents(universe)
            self.assertEqual(len(owners), 1)
            self.assertIs(type(owners[0]), dict)
            self.assertFalse(gc.is_tracked(owners[0]), 'atomic membership table must not add a full GC walk')
            self.assertEqual(set(owners[0]), set(ids))
            if frozen:
                direct = gc.get_referents(rows)
                self.assertIn(ids, direct)
                self.assertTrue(any(value is self.service.rows for value in direct))
                self.assertFalse(any(value is row for value in direct for row in self.service.rows.values()),
                                 'lazy sequence must not retain an edge for every row')


if __name__ == '__main__':
    unittest.main()
