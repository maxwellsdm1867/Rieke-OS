"""Typed source predicate truth tables and resource bounds, without any SQL."""
import copy
import unittest

from workspace_predicates import evaluate, predicate_catalog, validate
from workspace_tree import catalog


class PredicateTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'epoch_uuid': str(index), 'protocol_name': 'A' if index < 3 else 'B',
                      'start_time': '09/24/2026 12:00:00:000000'} for index in range(6)]
        params = [{'cutoff': 100.0, 'label': 'control', 'flags': [1, True]},
                  {'cutoff': 200.0, 'label': 'drug', 'flags': ['1']},
                  {'cutoff': 400.0, 'label': 'wash', 'flags': []},
                  {'cutoff': None, 'label': ''}, {}, {'cutoff': 100.0, 'label': 'drug'}]
        self.details = {row['epoch_uuid']: {'parameters': value} for row, value in zip(self.rows, params)}
        self.catalog, self.values = catalog(self.rows, self.details)

    def ids(self, predicate):
        return evaluate(predicate, self.catalog, self.values)[1]

    @staticmethod
    def leaf(field, operator, value=None):
        return {'field': field, 'operator': operator, **({} if operator in {'exists', 'missing', 'is_null'} else {'value': value})}

    def test_nested_all_any_not_preserve_precedence(self):
        protocol = self.leaf('protocol', 'eq', 'A')
        cutoff = {'any': [self.leaf('parameters/cutoff', 'eq', 100), self.leaf('parameters/cutoff', 'eq', 200)]}
        self.assertEqual(self.ids({'all': [protocol, cutoff]}), ['0', '1'])
        self.assertEqual(self.ids({'any': [protocol, self.leaf('parameters/cutoff', 'eq', 100)]}), ['0', '1', '2', '5'])
        self.assertEqual(self.ids({'not': {'any': [protocol, self.leaf('parameters/cutoff', 'is_null')]}}), ['4', '5'])
        self.assertEqual(self.ids({'all': []}), ['0', '1', '2', '3', '4', '5'])
        self.assertEqual(self.ids({'any': []}), [])

    def test_missing_null_and_negative_operators_are_explicit(self):
        field = 'parameters/cutoff'
        self.assertEqual(self.ids(self.leaf(field, 'exists')), ['0', '1', '2', '3', '5'])
        self.assertEqual(self.ids(self.leaf(field, 'missing')), ['4'])
        self.assertEqual(self.ids(self.leaf(field, 'is_null')), ['3'])
        self.assertEqual(self.ids(self.leaf(field, 'eq', None)), ['3'])
        self.assertEqual(self.ids(self.leaf(field, 'ne', 100)), ['1', '2', '3'])
        self.assertEqual(self.ids({'not': self.leaf(field, 'eq', 100)}), ['1', '2', '3', '4'])
        self.assertEqual(self.ids(self.leaf(field, 'not_in', [100, 200])), ['2', '3'])
        self.assertEqual(self.ids(self.leaf(field, 'in', [100, 200])), ['0', '1', '5'])

    def test_numeric_comparison_does_not_coerce_booleans_or_strings(self):
        field = 'parameters/cutoff'
        for operator, expected in [('gt', ['1', '2']), ('gte', ['0', '1', '2', '5']),
                                   ('lt', []), ('lte', ['0', '5'])]:
            self.assertEqual(self.ids(self.leaf(field, operator, 100)), expected)
        for value in ('100', True, float('nan'), float('inf'), 10 ** 400, 2**53 + 1):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                self.ids(self.leaf(field, 'eq', value))
        self.assertEqual(self.ids(self.leaf('parameters/flags', 'contains', True)), ['0'])
        self.assertEqual(self.ids(self.leaf('parameters/flags', 'contains', '1')), ['1'])
        self.assertEqual(self.ids(self.leaf('parameters/label', 'contains', 'rug')), ['1', '5'])
        self.assertEqual(self.ids(self.leaf('parameters/flags', 'eq', [1, True])), ['0'])
        self.assertEqual(self.ids(self.leaf('parameters/flags', 'eq', [True, 1])), [])

    def test_invalid_shapes_unknown_fields_and_excessive_resources_fail_closed(self):
        invalid = [None, [], {}, {'all': [], 'any': []}, {'not': []}, {'all': {}},
                   self.leaf('parameters/Cutoff', 'eq', 100), self.leaf('parameters/cutoff', 'LIKE', '%'),
                   {'field': 'protocol', 'operator': 'eq'},
                   {'field': 'protocol', 'operator': 'exists', 'value': None},
                   self.leaf('protocol', 'in', 'A'), self.leaf('protocol', 'gt', 1),
                   self.leaf('protocol', 'eq', 'x' * 4097),
                   self.leaf('parameters/cutoff', 'in', list(range(101))),
                   {'all': [self.leaf('protocol', 'eq', 'A')] * 129}]
        nested = self.leaf('protocol', 'eq', 'A')
        for _ in range(10):
            nested = {'not': nested}
        invalid.append(nested)
        for predicate in invalid:
            with self.subTest(predicate=str(predicate)[:80]), self.assertRaises(ValueError):
                validate(predicate, self.catalog, self.values)

    def test_typed_choices_are_bounded_and_missing_is_not_a_null_choice(self):
        before = copy.deepcopy((self.catalog, self.values))
        result = predicate_catalog(self.catalog, self.values)
        cutoff = next(field for field in result['fields'] if field['id'] == 'parameters/cutoff')
        self.assertEqual(cutoff['types'], ['null', 'number'])
        self.assertEqual(next(choice['count'] for choice in cutoff['choices'] if choice['value'] == 100), 2)
        self.assertEqual(sum(choice['count'] for choice in cutoff['choices']), 5)
        self.assertEqual(cutoff['missing_count'], 1)
        large = {str(index): {'protocol': str(index)} for index in range(100)}
        bounded = predicate_catalog({'fields': [{'id': 'protocol'}]}, large)['fields'][0]
        self.assertEqual(len(bounded['choices']), 50)
        self.assertTrue(bounded['choices_truncated'])
        self.assertEqual((self.catalog, self.values), before)


if __name__ == '__main__':
    unittest.main()
