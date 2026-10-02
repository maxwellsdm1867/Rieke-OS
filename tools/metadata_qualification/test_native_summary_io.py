"""Independent ordered native-facet oracle and I/O regression, small fixtures.

No scientific SQL/source writes. Truth imports no application implementation.
"""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from .truth import equal, kind
import workspace_explore_queries as queries


def oracle(identities, records, annotations, fields):
    result = {}
    for field in fields:
        buckets, present, truncated = [], 0, False
        for identity in identities:
            current = ({field: annotations[field].get(identity, [])}
                       if field in annotations else records[identity])
            if field not in current:
                continue
            present += 1
            value = current[field]
            bucket = next((item for item in buckets if equal(item['value'], value)), None)
            if bucket is not None:
                bucket['count'] += 1
            elif len(buckets) == 60:
                truncated = True
            else:
                buckets.append(dict(value=copy.deepcopy(value), type=kind(value), count=1))
        result[field] = dict(values=buckets, present_count=present,
                             missing_count=len(identities)-present, values_truncated=truncated)
    return dict(matched_count=len(identities), summaries=result)


class CountingValues(dict):
    def __init__(self, records):
        super().__init__(records)
        self.reads = []
        self.on_read = lambda: None

    def __getitem__(self, identity):
        self.reads.append(identity)
        self.on_read()
        return super().__getitem__(identity)


class NativeSummaryIOTests(unittest.TestCase):
    def setUp(self):
        self.identities = [str(i) for i in range(80)]
        variants = [1, 1.0, True, None, [], [1, True], {'b': None, 'a': [True, 1]},
                    {'a': [True, 1.0], 'b': None}, 2**54+1, 2**54]
        self.records = {identity: {'rare': index if index < 65 else 0,
                                  'mixed': copy.deepcopy(variants[index % len(variants)])}
                        for index, identity in enumerate(self.identities)}
        self.records['78']['rare'] = 64  # discarded bucket encountered again
        self.records['4'].pop('mixed')  # [] distinct from absence and null
        self.values = CountingValues(self.records)
        self.annotations = {'annotations/epoch/tags': {'1': ['own'], '3': ['inherited', 'own']}}
        self.fields = ['mixed', 'annotations/epoch/tags', 'rare']
        rows = [dict(epoch_uuid=identity, cell_uuid='cell-a' if index < 70 else 'cell-b')
                for index, identity in enumerate(self.identities)]
        self.service = SimpleNamespace(
            _tree_rows=lambda protocol, filters: rows,
            match_predicate=lambda predicate, identities: (predicate, list(identities), {}),
            _registered_tree_fields=lambda: ({'fields': [{'id': key} for key in ['rare', 'mixed']]}, self.values))
        self.context = dict(predicate={'all': []}, protocol_uuid=None, filters={}, scope={}, summary_fields=self.fields)

    def calculate(self, cancelled=lambda: False):
        with patch.object(queries, 'predicate_scope', side_effect=lambda catalog, values: (catalog, values)), \
             patch.object(queries.TagPredicates, 'snapshot', return_value=(self.annotations, {})):
            return queries._native_summaries(self.service, self.context, cancelled)

    def test_ordered_full_response_matches_independent_native_truth(self):
        actual = self.calculate()
        self.assertEqual(list(actual['summaries']), self.fields)
        self.assertEqual(actual, oracle(self.identities, self.records, self.annotations, self.fields))
        self.assertEqual(actual['summaries']['rare']['values'][0]['count'], 15)
        self.assertEqual(actual['summaries']['mixed']['values'][0]['value'], 1)
        self.assertIs(type(actual['summaries']['mixed']['values'][0]['value']), int)
        self.assertTrue(actual['summaries']['rare']['values_truncated'])
        next(bucket['value'] for bucket in actual['summaries']['mixed']['values']
             if isinstance(bucket['value'], list) and bucket['value']).append('mutation')
        self.assertNotIn('mutation', self.records['5']['mixed'])

    def test_each_matched_epoch_reads_values_once_above_disk_lru_capacity(self):
        self.calculate()
        self.assertEqual(self.values.reads, self.identities)

    def test_scope_and_authoritative_match_order_are_preserved(self):
        self.context['scope'] = {'cell_uuid': 'cell-b'}
        self.service.match_predicate = lambda predicate, identities: (predicate, list(reversed(list(identities)))[::2], {})
        expected_ids = ['79', '77', '75', '73', '71']
        actual = self.calculate()
        self.assertEqual(actual, oracle(expected_ids, self.records, self.annotations, self.fields))
        self.assertEqual(self.values.reads, expected_ids)

    def test_annotation_only_and_no_requested_fields_do_not_fetch_metadata(self):
        for fields in [['annotations/epoch/tags'], []]:
            with self.subTest(fields=fields):
                self.context['summary_fields'] = fields
                self.assertEqual(self.calculate(), oracle(self.identities, self.records, self.annotations, fields))
                self.assertEqual(self.values.reads, [])

    def test_empty_match_and_unknown_field_do_not_fetch_metadata(self):
        self.service.match_predicate = lambda predicate, identities: (predicate, [], {})
        self.assertEqual(self.calculate(), oracle([], self.records, self.annotations, self.fields))
        self.context['summary_fields'] = ['unknown']
        with self.assertRaisesRegex(ValueError, 'Unknown native summary field'):
            self.calculate()
        self.assertEqual(self.values.reads, [])

    def test_cancel_before_lookup_and_during_a_row_never_returns_partial_output(self):
        with self.assertRaises(InterruptedError):
            self.calculate(cancelled=lambda: True)
        self.assertEqual(self.values.reads, [])
        flag = [False]
        self.values.on_read = lambda: flag.__setitem__(0, True)
        with self.assertRaises(InterruptedError):
            self.calculate(cancelled=lambda: flag[0])
        self.assertEqual(self.values.reads, ['0'])


if __name__ == '__main__':
    unittest.main()
