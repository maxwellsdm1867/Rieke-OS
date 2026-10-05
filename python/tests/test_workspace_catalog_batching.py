"""Complete native catalog parity and measured batching regression controls.

Small disposable fixtures qualify semantics and SQL work, not UI latency or
the preserved real-million replay. No scientific source files are required.
"""
import copy
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import disco.metadata.disk_index as disk
import disco.navigation.predicates as predicates
import disco.navigation.tree as tree
from disco.metadata.tests.test_workspace_disk_index import fixture


def serialized(value):
    # Python equality alone hides bool/int and integer/float representation changes.
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class CatalogBatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def build(self, rows, details, sources):
        index = disk.DiskMetadataIndex.build(Path(self.temp.name)/'index.sqlite',
            rows, details, sources, 'generation', 'project')
        self.addCleanup(index.close)
        return index

    @contextmanager
    def trace(self, index):
        statements = []
        original = index._connect

        @contextmanager
        def traced(ids=None):
            with original(ids) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with patch.object(index, '_connect', traced):
            yield statements

    def test_complete_parity_for_ordered_scopes_typed_aliases_and_joints(self):
        # Retains the preserved experiment's cross-chunk semantic fixture.
        rows, details, sources = fixture(271, True)
        mixed = [1, 1.0, True, False, -0.0, 0.0, None, 'µ 雪', '__missing__',
                 [1, True], {'µ': [1.0, False]}]
        for number, row in enumerate(rows):
            params = details[row['epoch_uuid']]['parameters']
            params['typed'] = mixed[number % len(mixed)]
            params['alias'] = params['typed']
            if number % 4:
                params['partial'] = None if number % 3 else '雪'
            # Protocol axes that coincide must retain their separate meanings.
            params['history2'] = params['target']
            if number % 7 == 0:
                params.pop('history1')
            if number % 19 == 0:
                row['cell_uuid'] = None
        index = self.build(rows, details, sources)
        registered, _ = tree.catalog(rows, details, sources=sources)
        joint = tree.joint_id(['parameters/typed', 'parameters/partial'])
        known = registered['fields'] + [tree.joint_definition(joint,
            {field['id']: field for field in registered['fields']})]
        by_id = {row['epoch_uuid']: row for row in rows}
        scopes = [None, [row['epoch_uuid'] for row in rows][::-1],
                  [row['epoch_uuid'] for row in rows[::3]][::-1],
                  ['epoch-3', 'epoch-3', 'unknown', 'epoch-1'], [], ['unknown']]
        for ids in scopes:
            with self.subTest(ids='full' if ids is None else len(ids)):
                ordered = list(by_id) if ids is None else list(dict.fromkeys(
                    identity for identity in ids if identity in by_id))
                selected = [by_id[identity] for identity in ordered]
                expected, projected = tree.catalog(selected, details,
                    known_fields=known, sources=sources)
                expected, _ = tree.materialize_combinations(expected, projected, [joint])
                self.assertEqual(serialized(index.catalog(ids, known)), serialized(expected))
                plain, values = tree.catalog(selected, details,
                    known_fields=registered['fields'], sources=sources)
                self.assertEqual(serialized(index.predicate_catalog(ids)),
                    serialized(predicates.predicate_catalog(plain, values)))

    def test_new_fields_beyond_observed_union_are_batched_without_restriction(self):
        rows, details, sources = fixture(8)
        for number, row in enumerate(rows):
            details[row['epoch_uuid']]['parameters'].update(
                {f'future{field}': number % 2 for field in range(150)})
        index = self.build(rows, details, sources)
        known, _ = tree.catalog(rows, details, sources=sources)
        ids = ['epoch-5', 'epoch-1', 'epoch-2']
        with self.trace(index) as statements:
            actual = index.catalog(ids, known['fields'])
        expected, _ = tree.catalog([rows[5], rows[1], rows[2]], details,
                                  known_fields=known['fields'], sources=sources)
        self.assertEqual(serialized(actual), serialized(expected))
        self.assertEqual(sum(field['id'].startswith('parameters/future')
                             for field in actual['fields']), 150)
        aggregates = [sql for sql in statements if 'GROUP BY ev.field_no' in sql]
        self.assertEqual(len(aggregates), 2)  # Statistics and within-cell variation.
        self.assertFalse(any('WHERE f.field_id=' in sql for sql in statements))

    def test_subset_plan_and_full_generation_automatic_plan_use_actual_membership(self):
        rows, details, sources = fixture(12)
        index = self.build(rows, details, sources)
        known = index.catalog()['fields']
        all_ids = [row['epoch_uuid'] for row in rows][::-1]
        for ids, expected_join in ((None, 'JOIN'), (all_ids, 'JOIN'),
                (['foreign'] + all_ids + all_ids, 'JOIN'),
                (['epoch-4', 'foreign', 'epoch-4', 'epoch-1'], 'CROSS JOIN'),
                ([], 'CROSS JOIN')):
            with self.subTest(ids=ids):
                with self.trace(index) as statements:
                    index.catalog(ids, known)
                aggregates = [sql for sql in statements if 'GROUP BY ev.field_no' in sql]
                self.assertEqual(len(aggregates), 2)
                for sql in aggregates:
                    self.assertIn('FROM scope s ' + expected_join + ' epoch_values', sql)
                    self.assertEqual('CROSS JOIN' in sql, expected_join == 'CROSS JOIN')

    def test_suggestions_reuse_scoped_connection_and_joint_projections(self):
        rows, details, sources = fixture(40, True)
        index = self.build(rows, details, sources)
        known = index.catalog()['fields']
        ids = ['epoch-9', 'epoch-1', 'epoch-7', 'epoch-2']
        with patch.object(index, '_connect', wraps=index._connect) as connect:
            with patch.object(index, 'values', wraps=index.values) as values:
                actual = index.catalog(ids, known)
        # One catalog scope and one joint projection scope; ordinary suggestions
        # must not open scopes or decode/reencode columns independently.
        self.assertEqual(connect.call_count, 2)
        values.assert_called_once_with(ids=ids, fields=[tree.HISTORY_JOINT])
        expected, _ = tree.catalog([rows[9], rows[1], rows[7], rows[2]], details,
                                  known_fields=known, sources=sources)
        self.assertEqual(serialized(actual), serialized(expected))

    def test_null_is_recorded_but_does_not_create_within_cell_variation(self):
        rows, details, sources = fixture(8)
        for number, row in enumerate(rows):
            details[row['epoch_uuid']]['parameters'] = {
                'nullAndValue': None if number % 2 else 1,
                'numericRepresentation': 1 if number % 2 else 1.0}
        index = self.build(rows, details, sources)
        fields = {field['id']: field for field in index.catalog()['fields']}
        null_field = fields['parameters/nullAndValue']
        self.assertEqual((null_field['null_count'], null_field['missing_count']), (4, 0))
        self.assertFalse(null_field['varies_within_cell'])
        self.assertTrue(fields['parameters/numericRepresentation']['varies_within_cell'])

    def test_unrestricted_view_and_explicit_table_preserve_native_reader_order(self):
        rows, details, sources = fixture(40)
        index = self.build(rows, details, sources)
        with index._connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT type FROM sqlite_temp_master WHERE name='scope'").fetchone()[0], 'view')
            self.assertEqual([row[0] for row in connection.execute(
                'SELECT epoch_uuid FROM scope JOIN epochs USING(epoch_id) ORDER BY ordinal')],
                [row['epoch_uuid'] for row in rows])
        ids = ['epoch-9', 'foreign', 'epoch-2', 'epoch-9']
        with index._connect(ids) as connection:
            self.assertEqual(connection.execute(
                "SELECT type FROM sqlite_temp_master WHERE name='scope'").fetchone()[0], 'table')
            self.assertEqual(list(connection.execute(
                'SELECT ordinal,epoch_uuid FROM scope JOIN epochs USING(epoch_id) ORDER BY ordinal')),
                [(0, 'epoch-9'), (2, 'epoch-2')])
        expected_ids = [row['epoch_uuid'] for row in rows]
        self.assertEqual(list(index.values()), expected_ids)
        self.assertEqual(list(index.fingerprints()), expected_ids)
        self.assertEqual(list(index.rows()), expected_ids)
        self.assertEqual(list(index.details), expected_ids)
        self.assertEqual(list(index.source_projection('source')['rows']), expected_ids)
        self.assertEqual(index.match({'all': []})[1], expected_ids)
        self.assertEqual(list(index.values(ids)), ['epoch-9', 'epoch-2'])
        self.assertEqual(list(index.fingerprints(ids)), ['epoch-9', 'epoch-2'])

    def test_cached_catalog_is_fresh_and_checks_current_generation(self):
        rows, details, sources = fixture(8)
        index = self.build(rows, details, sources)
        expected = copy.deepcopy(index.catalog())
        changed = index.catalog()
        changed['fields'].clear()
        self.assertEqual(index.catalog(), expected)
        index.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            index.catalog()


if __name__ == '__main__':
    unittest.main()
