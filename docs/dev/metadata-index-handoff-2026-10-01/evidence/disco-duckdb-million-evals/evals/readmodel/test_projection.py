"""Meaningful paired-engine semantics checks; no production app or user data."""
import csv
import json
import tempfile
from pathlib import Path
import unittest

from projection import (AnalyticalProjection, CORE, NAMES, PROTOCOL_UUID,
                        fixture_row, generate_csv, identity)


class PairedProjectionTests(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix='disco-projection-sanity-')
        self.root = Path(self.owner.name)
        self.csv = self.root / 'fixture.csv'
        generate_csv(self.csv, 1000)
        self.engines = [AnalyticalProjection(engine, self.root / engine)
                        for engine in ('sqlite', 'duckdb')]
        for engine in self.engines:
            engine.build(self.csv)

    def tearDown(self):
        for engine in self.engines:
            engine.close()
        self.owner.cleanup()

    def paired(self, method, **arguments):
        outputs = [getattr(engine, method)(**arguments) for engine in self.engines]
        self.assertEqual(outputs[0], outputs[1])
        # Python equality masks True == 1 and integer == float. The API sends
        # JSON, so enforce exact canonical wire types, too.
        self.assertEqual(json.dumps(outputs[0], sort_keys=True, allow_nan=False),
                         json.dumps(outputs[1], sort_keys=True, allow_nan=False))
        return outputs[0]

    def test_every_page_exact_order_and_cursor(self):
        expected = sorted((fixture_row(i, 1000) for i in range(1000)),
                          key=lambda row: (row[NAMES.index('date')], row[NAMES.index('start_time')], row[0]))
        actual, cursor = [], None
        while True:
            output = self.paired('page', cursor=cursor)
            for row in output['items']:
                for field in ('contrast', 'seed', 'stimTime', 'currentMean'):
                    self.assertIs(type(row[field + '_present']), bool)
            actual.extend(item['epoch_uuid'] for item in output['items'])
            cursor = output['next_cursor']
            if cursor is None:
                break
        self.assertEqual(actual, [row[0] for row in expected])
        self.assertEqual(len(set(actual)), 1000)

    def test_parent_tree_details_facets_and_tags(self):
        root = self.paired('tree_children', level='cell')
        self.assertEqual(root['total'], 10)
        self.assertEqual([item['count'] for item in root['items']], [100] * 10)
        child = self.paired('tree_children', level='block', parent={'cell_uuid': identity(1000)})
        self.assertEqual(child['total'], 5)
        self.assertEqual([item['count'] for item in child['items']], [20] * 5)
        self.assertEqual([item['key'] for item in child['items']], [identity(2000 + i) for i in range(5)])
        block_cursor, blocks = None, []
        while True:
            output = self.paired('tree_children', level='block', limit=3, cursor=block_cursor)
            blocks.extend(item['key'] for item in output['items'])
            block_cursor = output['next_cursor']
            if block_cursor is None:
                break
        self.assertEqual(blocks, [identity(2000 + i) for i in range(50)])
        filtered = self.paired('preview', filters={'contrast': .3}, facet_fields=('contrast', 'seed'))
        self.assertEqual(filtered['count'], 200)
        self.assertTrue(filtered['facets']['seed']['has_more'])
        self.assertEqual(len(filtered['facets']['seed']['items']), 60)
        detail = self.paired('detail', epoch_uuid=identity(3))
        self.assertEqual(detail['parameters'], {'contrast': .3, 'seed': 3, 'stimTime': 1000, 'currentMean': 0})
        self.assertEqual(detail['protocol_uuid'], PROTOCOL_UUID)
        tag = self.paired('tag_page', ids=[identity(i) for i in range(20)], filters={'contrast': .3})
        self.assertEqual([row['synthetic_index'] for row in tag['items']], [3, 8, 13, 18])

    def test_lazy_point_iteration_and_persistent_reopen(self):
        for engine in self.engines:
            self.assertEqual(len(engine.lazy_rows), 1000)
            self.assertEqual(len(engine.lazy_cells), 10)
            self.assertEqual(list(engine.lazy_rows), [identity(i) for i in range(1000)])
            self.assertIn(identity(1), engine.lazy_rows)
            self.assertNotIn(identity(-99), engine.lazy_rows)
            self.assertEqual(engine.lazy_rows[identity(1)]['metadata_hash'], 'b' * 64)
            self.assertEqual(engine.lazy_cells[identity(1000)]['label'], 'Cell0')
            engine.checkpoint()
        expected = self.engines[0].page()
        for engine in self.engines:
            reopened = AnalyticalProjection(engine.engine, engine.db_path)
            try:
                self.assertEqual(reopened.page(), expected)
            finally:
                reopened.close()

    def test_missing_null_and_numeric_kind_flags_are_distinct(self):
        for engine in self.engines:
            for i, kind, present, value in [(0, 'missing', 0, None), (1, 'null', 1, None),
                                            (2, 'integer', 1, 1), (3, 'float', 1, .3)]:
                engine.execute('UPDATE epochs SET contrast_kind=?,contrast_present=?,contrast=? WHERE epoch_uuid=?',
                               [kind, present, value, identity(i)])
            if engine.engine == 'sqlite':
                engine.connection.commit()
        self.assertEqual(self.paired('preview', filters={'contrast': {'kind': 'missing'}})['count'], 1)
        self.assertEqual(self.paired('preview', filters={'contrast': {'kind': 'null'}})['count'], 1)
        self.assertEqual(self.paired('preview', filters={'contrast': {'kind': 'integer', 'value': 1}})['count'], 1)
        self.assertEqual(self.paired('preview', filters={'contrast': .3})['count'], 200)
        self.assertNotIn('contrast', self.paired('detail', epoch_uuid=identity(0))['parameters'])
        self.assertIsNone(self.paired('detail', epoch_uuid=identity(1))['parameters']['contrast'])
        integer_flag = self.paired('detail', epoch_uuid=identity(2))
        self.assertEqual(integer_flag['parameter_states']['contrast']['kind'], 'integer')
        # The fixed contrast column is DOUBLE. Its kind marker survives, but
        # the original JSON integer primitive does not: values return as 1.0.
        # This is an explicit prototype limitation, not semantic equivalence
        # for arbitrary production JSON metadata.
        self.assertIs(type(integer_flag['parameters']['contrast']), float)
        self.assertEqual(json.dumps(integer_flag['parameters']['contrast']), '1.0')


if __name__ == '__main__':
    unittest.main()
