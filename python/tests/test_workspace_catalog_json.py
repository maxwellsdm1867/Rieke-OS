"""Import JSON policy through the public validator; SQL doubles are not native proof."""
import copy
import json
import math
from types import SimpleNamespace
import unittest

from workspace_catalog_identity import CatalogIdentityConflict, validate_catalog_identity
from python.tests.test_workspace_catalog_identity import fixture

VALUE = 0.15261696363083765
ROUNDED = 0.15261696363083763


def convert(value):
    if type(value) is float and value == VALUE:
        return ROUNDED
    if isinstance(value, dict):
        return {key: convert(child) for key, child in value.items()}
    if isinstance(value, list):
        return [convert(child) for child in value]
    return value


class Witness:
    def __init__(self, conversion=convert):
        self.calls = []
        self.conversion = conversion

    def query(self, sql, args):
        self.calls.append((sql, args))
        assert sql.startswith('SELECT ')
        return SimpleNamespace(fetchone=lambda: tuple(
            json.dumps(self.conversion(json.loads(value))) for value in args))


def example(source_value=None, actual_value=None, *, per_cell=2):
    source, catalog, rows, fetches = fixture(per_cell)
    original = {'nested': [{'value': VALUE}]} if source_value is None else source_value
    actual = convert(original) if actual_value is None else actual_value
    for cell in source['animals'][0]['preparations'][0]['cells']:
        for epoch in cell['epoch_groups'][0]['epoch_blocks'][0]['epochs']:
            epoch['parameters'] = copy.deepcopy(original)
    for row in rows['Epoch']:
        row['parameters'] = copy.deepcopy(actual)
    witness = Witness()
    catalog.schema = SimpleNamespace(connection=witness)
    return source, catalog, rows, fetches, witness


class CatalogJSONPolicyTests(unittest.TestCase):
    def test_default_remains_exact(self):
        source, catalog, _, _, witness = example()
        with self.assertRaises(CatalogIdentityConflict):
            validate_catalog_identity(source, catalog, 7)
        self.assertEqual(witness.calls, [])

    def test_opt_in_requires_server_witness_without_mutating_source_or_catalog(self):
        source, catalog, rows, fetches, witness = example()
        before = copy.deepcopy((source, rows))
        counts = validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual(counts['Epoch'], 4)
        self.assertEqual((source, rows), before)
        self.assertEqual(len(fetches), 10)
        self.assertEqual(len(witness.calls), 1)
        self.assertTrue(all(VALUE == json.loads(value)['nested'][0]['value'] for value in witness.calls[0][1]))

    def test_one_ulp_tamper_not_produced_by_converter_rejects(self):
        source, catalog, _, _, witness = example({'value': VALUE},
            {'value': math.nextafter(VALUE, math.inf)})
        with self.assertRaisesRegex(CatalogIdentityConflict, 'MySQL JSON encoding'):
            validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual(len(witness.calls), 1)

    def test_converter_upgrade_can_reject_old_representation_without_ulp_fallback(self):
        source, catalog, rows, _, witness = example()
        before = copy.deepcopy((source, rows))
        validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        # A hypothetical upgraded converter now preserves the source exactly.
        # Old one-step catalog rounding must not pass on closeness alone.
        witness.conversion = lambda value: value
        with self.assertRaisesRegex(CatalogIdentityConflict, 'MySQL JSON encoding'):
            validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual((source, rows), before)

    def test_three_step_cap_is_not_a_four_step_tolerance(self):
        for steps in (3, 4):
            actual = VALUE
            for _ in range(steps):
                actual = math.nextafter(actual, math.inf)
            source, catalog, _, _, witness = example({'value': VALUE}, {'value': actual})
            witness.conversion = lambda value: {'value': actual}
            if steps == 3:
                validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
            else:
                with self.assertRaises(CatalogIdentityConflict):
                    validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
                self.assertEqual(witness.calls, [])

    def test_types_integers_text_shape_order_and_missing_values_remain_exact(self):
        original = {'value': VALUE, 'flag': True, 'integer': 2**63+1,
                    'text': 'control', 'array': [1, 2], 'null': None}
        for changed in ({'flag': 1}, {'integer': 2**63+2}, {'integer': float(2**63)},
                        {'text': 'changed'}, {'array': [2, 1]}, {'array': [1]},
                        {'null': 'null'}, {'new': 1}):
            source, catalog, _, _, witness = example(original, {**convert(original), **changed})
            with self.subTest(changed=changed), self.assertRaises(CatalogIdentityConflict):
                validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
            self.assertEqual(witness.calls, [])

    def test_integral_float_seed_cannot_change_to_neighbor(self):
        source, catalog, _, _, witness = example({'seed': 42.0},
            {'seed': math.nextafter(42.0, math.inf)})
        with self.assertRaisesRegex(CatalogIdentityConflict, 'MySQL JSON encoding'):
            validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)

    def test_zero_sign_zero_to_nonzero_and_nonfinite_values_reject(self):
        for original, actual in ((-0.0, 0.0), (0.0, 5e-324), (5e-324, 0.0),
                                 (1.0, math.inf), (math.nan, math.nan)):
            source, catalog, _, _, witness = example({'value': original}, {'value': actual})
            with self.subTest(original=original, actual=actual), self.assertRaises(ValueError):
                validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
            self.assertEqual(witness.calls, [])

    def test_parent_and_stream_checks_remain_exact_under_opt_in(self):
        for kind, field, value in (('Epoch', 'parent_id', -1),
                                    ('Response', 'sample_rate', '10000.000000000001'),
                                    ('Response', 'h5path', '/wrong')):
            source, catalog, rows, _, witness = example()
            rows[kind][0][field] = value
            with self.subTest(kind=kind, field=field), self.assertRaises(CatalogIdentityConflict):
                validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)

    def test_long_nested_array_and_escaped_keys_need_one_document_witness(self):
        source, catalog, _, _, witness = example({'quote"\\雪\n': [VALUE]*130}, per_cell=1)
        validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual(len(witness.calls), 1)
        self.assertEqual(len(witness.calls[0][1]), 2)

    def test_document_probes_are_batched_and_anchored_to_original_on_every_recheck(self):
        source, catalog, _, _, witness = example(per_cell=33)
        for _ in range(2):
            validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual([len(args) for sql, args in witness.calls], [32, 32, 2]*2)
        self.assertTrue(all(json.loads(value)['nested'][0]['value'] == VALUE
                            for sql, args in witness.calls for value in args))

    def test_unchanged_documents_do_not_issue_witness_queries(self):
        source, catalog, _, _, witness = example({'value': VALUE}, {'value': VALUE})
        validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual(witness.calls, [])

    def test_float_distance_handles_negative_binade_subnormal_and_max_finite(self):
        for value, direction in ((-VALUE, -math.inf), (2.0, 0.0),
                                 (float.fromhex('0x1.0p-1022'), 0.0),
                                 (float.fromhex('0x1.fffffffffffffp+1023'), 0.0)):
            adjacent = math.nextafter(value, direction)
            source, catalog, _, _, witness = example({'value': value}, {'value': adjacent})
            witness.conversion = lambda document: {'value': adjacent}
            with self.subTest(value=value):
                validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)

    def test_byte_budget_splits_large_documents_before_count_limit(self):
        source, catalog, _, _, witness = example({'value': VALUE, 'text': 'x'*600000}, per_cell=1)
        validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual([len(args) for sql, args in witness.calls], [1, 1])

    def test_incomplete_witness_fails_closed(self):
        source, catalog, _, _, witness = example()
        witness.query = lambda *args: SimpleNamespace(fetchone=lambda: ())
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)

    def test_witness_sql_failure_has_no_close_value_fallback(self):
        source, catalog, rows, _, witness = example()
        before = copy.deepcopy((source, rows))
        def unavailable(*args):
            raise RuntimeError('SQL witness unavailable')
        witness.query = unavailable
        with self.assertRaisesRegex(RuntimeError, 'SQL witness unavailable'):
            validate_catalog_identity(source, catalog, 7, mysql_json_rounding=True)
        self.assertEqual((source, rows), before)


if __name__ == '__main__':
    unittest.main()
