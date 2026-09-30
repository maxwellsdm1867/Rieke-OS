"""Scientific identity parity for the bounded catalog optimization."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import workspace_tree as tree
import workspace_predicates as predicates


def fixture():
    rows, details = [], {}
    values = [1, 1.0, True, None, -0.0, 0.0, '1', [1, False]]
    for index, value in enumerate(values):
        identity = f'epoch-{index}'
        rows.append({'epoch_uuid': identity, 'cell_uuid': f'cell-{index//3}', 'cell_label': 'Cell',
            'cell_type': 'ON', 'date': '2026-09-24', 'start_time': '09/24/2026 12:00:00:000000',
            'group_uuid': 'group', 'group_label': 'Control', 'block_uuid': 'block',
            'block_start_time': '09/24/2026 12:00:00:000000',
            'protocol_name': 'edu.washington.riekelab.chris.protocols.VariableHistoryNoiseCurInject'})
        parameters = {'value': value, 'a/b': {'x~z': value}, 'history1': [0, index%2],
                      'history2': [2, 3], 'target': [4, 5], 'isControl': index%2,
                      'segmentTime': 1000, 'frequencyCutoff': 100}
        if index == 3:
            parameters.pop('history1')
        details[identity] = {'parameters': parameters, 'properties': {'comment': 'recorded'},
                            'metadata': {'block': {'parameters': {'frequencyCutoff': 100}}}}
    known = [{'id': 'parameters/value', 'label': 'OLD label', 'category': 'OLD', 'path': 'OLD'},
             {'id': 'parameters/absent', 'label': 'Known absent', 'category': 'Parameters', 'path': 'parameters.absent'}]
    return rows, details, known


def legacy_predicate_catalog(catalog, values):
    """Independent old linear comparison oracle, including bounded truncation."""
    result = copy.deepcopy(catalog)
    for field in result['fields']:
        buckets, types = [], set()
        for current in values.values():
            if field['id'] not in current:
                continue
            value = current[field['id']]
            value_type = predicates.kind(value)
            types.add(value_type)
            found = next((item for item in buckets if predicates.equal(item['value'], value)), None)
            if found is not None:
                found['count'] += 1
            elif len(buckets) <= predicates.MAX_CHOICES:
                buckets.append({'value': copy.deepcopy(value), 'type': value_type, 'count': 1})
        field.update(types=sorted(types), choices=buckets[:predicates.MAX_CHOICES],
                     choices_truncated=len(buckets)>predicates.MAX_CHOICES)
    result.update(operators=list(predicates.OPERATORS), predicate_version=1,
                  limits={'max_depth': predicates.MAX_DEPTH, 'max_nodes': predicates.MAX_NODES, 'max_choices': predicates.MAX_CHOICES})
    return result


class CatalogOptimizationTests(unittest.TestCase):
    def test_catalog_and_values_match_preoptimization_fixture_exactly(self):
        catalog, values = tree.catalog(*fixture())
        # Epoch UUID is a new identity field; existing scientific fields retain the historical oracle.
        self.assertEqual({key: current['epoch'] for key, current in values.items()}, {key: key for key in values})
        legacy_catalog = {**catalog, 'fields': [field for field in catalog['fields'] if field['id'] != 'epoch']}
        legacy_values = {key: {field: value for field, value in current.items() if field != 'epoch'} for key, current in values.items()}
        digest = hashlib.sha256(json.dumps([legacy_catalog, legacy_values], sort_keys=True, allow_nan=False).encode()).hexdigest()
        # Captured from the unoptimized implementation before this change.
        self.assertEqual(digest, '97d7c1e6971e4a563f4caaafb4f0d3d241404a45a23a2279847bc8fe17377df1')
        fields = {item['id']: item for item in catalog['fields']}
        self.assertEqual(fields['parameters/value']['label'], 'Value')
        self.assertEqual(fields['parameters/absent']['label'], 'Known absent')
        self.assertEqual(fields['parameters/absent']['missing_count'], 8)
        self.assertIn('parameters/a~1b/x~0z', fields)

    def test_escaped_ids_are_resolved_once_per_distinct_path(self):
        rows, details, known = fixture()
        with patch.object(tree, 'field_id', wraps=tree.field_id) as resolve:
            tree.catalog(rows, details, known)
        paths = [call.args[0] for call in resolve.call_args_list]
        self.assertEqual(len(paths), len(set(paths)))

    def test_hash_choice_buckets_match_typed_linear_oracle(self):
        values = [1, 1.0, True, False, 0, -0.0, 0.0, None, '1', [1, True], [1.0, True],
                  {'b': [1, False], 'a': None}, {'a': None, 'b': [1.0, False]},
                  2**60, float(2**60), 2**60+1]
        values += list(range(100)) + [1.0, 49, 50, 99]*3
        columns = {str(index): {'value': value} for index, value in enumerate(values)}
        catalog = {'fields': [{'id': 'value'}]}
        expected = legacy_predicate_catalog(catalog, columns)
        actual = predicates.predicate_catalog(catalog, columns)
        self.assertEqual(json.dumps(actual, sort_keys=True), json.dumps(expected, sort_keys=True))
        self.assertEqual(len(actual['fields'][0]['choices']), predicates.MAX_CHOICES)
        self.assertTrue(actual['fields'][0]['choices_truncated'])

    def test_scalar_cache_preserves_exact_json_and_is_bounded(self):
        values = [None, True, False, 1, 1.0, 0, 0.0, -0.0, '', 'null', '<not recorded>',
                  'Unicode µ', 2**70, [1, 1.0], {'b': 2, 'a': 1}, 'x'*513]
        for value in values:
            self.assertEqual(tree.value_key(value), json.dumps(value, sort_keys=True, ensure_ascii=False,
                separators=(',', ':'), allow_nan=False))
        for index in range(5000):
            tree.value_key('bounded-' + str(index))
        self.assertLessEqual(tree._scalar_value_key.cache_info().currsize, 4096)
        with self.assertRaises(ValueError):
            tree.value_key(float('nan'))


if __name__ == '__main__':
    unittest.main()
