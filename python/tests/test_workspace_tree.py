"""Metadata-only grouping invariants; no source recording or database access."""
import copy
import tempfile
import unittest
from unittest.mock import patch
import uuid

from workspace_recipes import build_tree, parse_splits
from workspace_tree import catalog, field_id, value_key, HISTORY_JOINT
if __package__:
    from .test_workspace_api import FixtureService
else:
    from test_workspace_api import FixtureService


def members(node):
    if 'epoch_uuids' in node:
        return list(node['epoch_uuids'])
    return [key for child in node.get('children', []) for key in members(child)]


class DynamicTreeTests(unittest.TestCase):
    def test_description_fields_are_recorded_scoped_and_do_not_change_fingerprints(self):
        with tempfile.TemporaryDirectory() as folder:
            service = FixtureService(folder)
            service.sources[0]['metadata'] = {'notes': [], 'start_time': '09/24/2026 12:00:00:000000',
                'attributes': {'purpose': None, 'startTimeDotNetDateTimeOffsetTicks': 639258608779858225},
                'properties': {'lab': 'Recorded lab'}}
            first, second = service.ids
            service.details[first]['metadata']['cell'] = {'label': 'Cell1', 'comment': 'stable', 'keywords': ['ON', 'control']}
            service.details[first]['metadata']['block'] = {'parameters': {'frequencyCutoff': 100}}
            service.details[first]['metadata']['epoch'].update(start_time=service.rows[first]['start_time'])
            service.details[first]['properties']['bathTemperature'] = 29.1
            before = copy.deepcopy((service.details, service.rows, service._fingerprints, service.sources))
            with patch('h5py.File', side_effect=AssertionError('Metadata discovery must not read waveforms')):
                fields = {field['id']: field for field in service.predicate_fields()['fields']}
                self.assertEqual(fields['metadata/experiment/attributes/purpose']['null_count'], 2)
                self.assertEqual(fields['metadata/cell/comment']['missing_count'], 1)
                self.assertEqual(fields['metadata/cell/keywords']['types'], ['array'])
                self.assertEqual(fields['properties/bathTemperature']['label'], 'Epoch · Bath temperature')
                self.assertIn('metadata/block/parameters/frequencyCutoff', fields)
                self.assertNotIn('metadata/experiment/attributes/startTimeDotNetDateTimeOffsetTicks', fields)
                self.assertFalse({'included', 'includeInAnalysis', 'keywords'} & fields.keys())
                result = service.explore_preview({'all': [
                    {'field': 'metadata/experiment/attributes/purpose', 'operator': 'is_null'},
                    {'field': 'metadata/cell/keywords', 'operator': 'contains', 'value': 'ON'}]},
                    splits='metadata/experiment/properties/lab,metadata/cell/label')
                self.assertEqual([row['uuid'] for row in result['membership']], [first])
                self.assertEqual(result['tree']['children'][0]['value'], 'Recorded lab')
            self.assertEqual((service.details, service.rows, service._fingerprints, service.sources), before)

    def test_experiment_fields_never_leak_between_sources_or_make_missing_values_null(self):
        rows, details = self.fixture([{}, {}])
        rows[0]['source_sha256'], rows[1]['source_sha256'] = 'a', 'b'
        sources = [{'source_sha256': 'a', 'metadata': {'attributes': {'purpose': 'flash'}, 'notes': []}},
                   {'source_sha256': 'b', 'metadata': {'attributes': {}}}]
        result, values = catalog(rows, details, sources=sources)
        field = next(field for field in result['fields'] if field['id'] == 'metadata/experiment/attributes/purpose')
        self.assertEqual((field['missing_count'], field['null_count']), (1, 0))
        self.assertEqual(values[rows[0]['epoch_uuid']]['metadata/experiment/attributes/purpose'], 'flash')
        self.assertNotIn('metadata/experiment/attributes/purpose', values[rows[1]['epoch_uuid']])
        self.assertEqual(values[rows[0]['epoch_uuid']]['metadata/experiment/notes'], [])

    def fixture(self, parameters):
        rows, details = [], {}
        for index, values in enumerate(parameters):
            identity = str(uuid.uuid4())
            rows.append({'epoch_uuid': identity, 'cell_uuid': 'cell-' + str(index % 2),
                'cell_type': 'recorded type', 'group_uuid': 'group', 'group_label': 'Control',
                'start_time': '09/24/2026 12:00:00:000000', 'block_uuid': 'block',
                'protocol_name': 'RecordedProtocol'})
            details[identity] = {'parameters': values, 'properties': {}, 'metadata': {'group': {
                'properties': {'externalSolutionAdditions': '[;NBQX (10uM);]'}}}}
        return rows, details

    def test_reordering_preserves_exact_membership_and_rejects_duplicate_epochs(self):
        rows, details = self.fixture([{'frequencyCutoff': 10}, {'frequencyCutoff': 2}, {},
                                     {'frequencyCutoff': 10}, {'frequencyCutoff': None}])
        before = copy.deepcopy((rows, details))
        fields, values = catalog(rows, details)
        allowed = {field['id'] for field in fields['fields']}
        for order in ('cell, parameters/frequencyCutoff', 'parameters/frequencyCutoff, cell', ''):
            tree = build_tree(rows, order, values, allowed)
            self.assertEqual(set(members(tree)), {row['epoch_uuid'] for row in rows})
            self.assertEqual(len(members(tree)), len(rows))
            self.assertEqual(tree['count'], len(rows))
        self.assertEqual((rows, details), before)
        with self.assertRaisesRegex(ValueError, 'Duplicate epoch'):
            build_tree(rows + rows[:1], 'cell', values, allowed)

    def test_numeric_string_boolean_array_missing_and_null_remain_distinct(self):
        parameters = [{'value': value} for value in (10, 2, 1, '1', True, [1, 2], None, '')] + [{}]
        rows, details = self.fixture(parameters)
        fields, values = catalog(rows, details)
        field = next(field for field in fields['fields'] if field['id'] == 'parameters/value')
        self.assertEqual((field['distinct_count'], field['null_count'], field['missing_count']), (8, 1, 1))
        tree = build_tree(rows, 'parameters/value', values)
        children = tree['children']
        self.assertEqual([child['value'] for child in children[:3]], [1, 2, 10])
        self.assertEqual(len(children), 9)
        typed = {(child['missing'], value_key(child['value'])): child for child in children}
        for key in ((False, '1'), (False, '"1"'), (False, 'true'), (False, '[1,2]'),
                    (False, 'null'), (True, 'null'), (False, '""')):
            self.assertEqual(typed[key]['count'], 1)
        self.assertTrue(children[-1]['missing'])

    def test_case_sensitive_and_escaped_parameter_paths_do_not_collide(self):
        rows, details = self.fixture([{'currentSD': 5, 'currentsd': 10,
            'a/b': 1, 'a': {'b': 2}, 'a~b': 3, 'cut,off→x': 4}])
        fields, values = catalog(rows, details)
        allowed = {field['id'] for field in fields['fields']}
        special = field_id(('parameters', 'cut,off→x'))
        self.assertIn('parameters/a~1b', allowed)
        self.assertIn('parameters/a/b', allowed)
        self.assertIn('parameters/a~0b', allowed)
        self.assertNotIn(',', special)
        self.assertNotIn('→', special)
        self.assertEqual(parse_splits('Cell, parameters/currentSD, parameters/currentsd', allowed),
                         ['cell', 'parameters/currentSD', 'parameters/currentsd'])
        self.assertEqual(parse_splits(special, allowed), [special])
        for invalid in ('parameters/CurrentSD', 'parameters/absent', 'cell, CELL'):
            with self.assertRaises(ValueError):
                parse_splits(invalid, allowed)
        self.assertEqual(build_tree(rows, special, values)['children'][0]['value'], 4)

    def test_catalog_uses_recorded_conditions_and_omits_sample_vectors(self):
        rows, details = self.fixture([{'shortArray': [1, 2], 'longTrace': list(range(33))}, {}])
        result, values = catalog(rows, details)
        ids = {field['id'] for field in result['fields']}
        self.assertIn('parameters/shortArray', ids)
        self.assertNotIn('parameters/longTrace', ids)
        self.assertFalse({'drug', 'phase', 'control'} & ids)
        for datum in values.values():
            self.assertEqual(datum['group label'], 'Control')
            self.assertEqual(datum['metadata/group/properties/externalSolutionAdditions'], '[;NBQX (10uM);]')
        self.assertEqual({preset['id'] for preset in result['presets']}, {'recording', 'conditions'})
        details[rows[0]['epoch_uuid']]['parameters'].update(frequencyCutoff=414, currentMean=0, currentSD=10)
        presets = catalog(rows, details)[0]['presets']
        self.assertEqual({preset['id'] for preset in presets}, {'recording', 'conditions', 'frequency', 'current', 'noise'})
        known = {field['id'] for field in catalog(rows, details)[0]['fields']}
        self.assertTrue(all(set(preset['fields']) <= known for preset in presets))

    def test_service_summary_and_filtered_absent_field_use_full_catalog_without_io(self):
        with tempfile.TemporaryDirectory() as folder:
            service = FixtureService(folder)
            service.details[service.ids[0]]['parameters']['frequencyCutoff'] = 414
            service.rows[service.ids[0]]['epoch_number'] = 1
            service.rows[service.ids[1]]['epoch_number'] = 1
            with patch('h5py.File', side_effect=AssertionError('No trace IO allowed')), \
                 patch('recording_workspace.connect', side_effect=AssertionError('No DB access allowed')):
                full = service.tree_fields(service.protocol_id)
                self.assertEqual(full['total'], 2)
                self.assertIn('frequency', {preset['id'] for preset in full['presets']})
                tree = service.tree(service.protocol_id, splits='parameters/frequencyCutoff, cell')
                self.assertEqual(tree['levels'][0]['groups'], 2)
                self.assertEqual(tree['levels'][0]['missing_epochs'], 1)
                self.assertEqual(tree['levels'][1]['groups'], 2)
                self.assertEqual(set(members(tree)), set(service.ids))
                filters = {'cell_uuid': service.cell_ids[1]}
                subset = service.tree_fields(service.protocol_id, filters)
                cutoff = next(field for field in subset['fields'] if field['id'] == 'parameters/frequencyCutoff')
                self.assertEqual((cutoff['count'], cutoff['missing_count'], cutoff['distinct_count']), (1, 1, 0))
                grouped = service.tree(service.protocol_id, filters, splits='parameters/frequencyCutoff')
                self.assertEqual(grouped['children'][0]['label'], 'Not recorded')
                self.assertEqual(members(grouped), service.ids[1:])
                empty = service.tree(service.protocol_id, {'cell_type': 'absent'}, splits='parameters/frequencyCutoff')
                self.assertEqual(empty['count'], 0)
                self.assertEqual(empty['children'], [])
                self.assertEqual(service.validate_tree_splits(service.protocol_id, 'parameters/frequencyCutoff'),
                                 ['parameters/frequencyCutoff'])

    def test_suggestions_exclude_constants_nulls_seeds_and_duplicate_value_columns(self):
        rows, details = self.fixture([{
            'constant': 5, 'allNull': None, 'seed': index, 'uniqueMeasurement': index,
            'currentSD': index % 2, 'currentMean': index % 2,
        } for index in range(20)])
        before = copy.deepcopy((rows, details))
        result, _ = catalog(rows, details)
        fields = {field['id']: field for field in result['fields']}
        suggested = set(result['suggestions'])
        self.assertIn('parameters/currentSD', suggested)
        self.assertNotIn('parameters/currentMean', suggested)  # Identical typed values are one suggestion.
        self.assertIn('parameters/currentMean', fields)  # Still available in the complete field picker.
        for field in ('parameters/constant', 'parameters/allNull', 'parameters/seed', 'parameters/uniqueMeasurement'):
            self.assertNotIn(field, suggested)
            self.assertIsNone(fields[field]['suggested_rank'])
        self.assertFalse(fields['parameters/allNull']['varying'])
        self.assertEqual(fields['parameters/allNull']['recorded_distinct_count'], 0)
        self.assertEqual(fields['parameters/allNull']['null_count'], 20)
        self.assertTrue(fields['parameters/seed']['high_cardinality'])
        self.assertTrue(fields['parameters/uniqueMeasurement']['high_cardinality'])
        self.assertEqual([fields[key]['suggested_rank'] for key in result['suggestions']],
                         list(range(len(result['suggestions']))))
        self.assertLessEqual(len(result['suggestions']), 6)
        self.assertEqual((rows, details), before)

    def test_suggestions_preserve_missing_vs_null_and_never_infer_conditions(self):
        parameters = [{'aValue': index % 2, 'bValue': index % 2, 'seed': index % 2}
                      for index in range(12)]
        del parameters[0]['aValue']
        parameters[0]['bValue'] = None
        rows, details = self.fixture(parameters)
        result, values = catalog(rows, details)
        fields = {field['id']: field for field in result['fields']}
        self.assertIn('parameters/aValue', result['suggestions'])
        self.assertIn('parameters/bValue', result['suggestions'])
        self.assertNotIn('parameters/seed', result['suggestions'])  # Identity-like seed excluded even at two values.
        self.assertEqual(fields['parameters/aValue']['missing_count'], 1)
        self.assertEqual(fields['parameters/bValue']['null_count'], 1)
        self.assertIn('1 missing stay visible', fields['parameters/aValue']['suggestion_reason'])
        tree = build_tree(rows, 'parameters/aValue', values)
        missing = next(node for node in tree['children'] if node['missing'])
        self.assertEqual(missing['epoch_uuids'], [rows[0]['epoch_uuid']])
        self.assertEqual(len(members(tree)), len(rows))
        self.assertEqual(set(members(tree)), {row['epoch_uuid'] for row in rows})
        self.assertFalse({'drug', 'phase', 'treatment'} & fields.keys())
        self.assertEqual(values[rows[0]['epoch_uuid']]['group label'], 'Control')
        self.assertEqual(values[rows[0]['epoch_uuid']]['metadata/group/properties/externalSolutionAdditions'],
                         '[;NBQX (10uM);]')

    def test_recording_protocol_suggested_only_when_recorded_protocol_actually_varies(self):
        rows, details = self.fixture([{} for _ in range(8)])
        self.assertNotIn('protocol', catalog(rows, details)[0]['suggestions'])
        for row in rows[4:]:
            row['protocol_name'] = 'AnotherRecordedProtocol'
        result, _ = catalog(rows, details)
        self.assertEqual(result['suggestions'][0], 'protocol')
        protocol = next(field for field in result['fields'] if field['id'] == 'protocol')
        self.assertEqual(protocol['recorded_distinct_count'], 2)
        self.assertTrue(protocol['varying'])

    def test_project_explorer_includes_unassigned_epochs_without_protocol_or_source_access(self):
        with tempfile.TemporaryDirectory() as folder:
            service = FixtureService(folder)
            outside = str(uuid.uuid4())
            service.rows[outside] = {**copy.deepcopy(service.rows[service.ids[0]]),
                'epoch_uuid': outside, 'group_label': 'Unassigned group', 'protocol_name': 'UnassignedProtocol'}
            service.details[outside] = {'parameters': {'unassignedSetting': 7}, 'properties': {}, 'metadata': {}}
            before = copy.deepcopy((service.rows, service.details))
            with patch.object(service, 'query_result', side_effect=AssertionError('No saved query required')), \
                 patch.object(service, 'filtered_rows', side_effect=AssertionError('No protocol query required')), \
                 patch('h5py.File', side_effect=AssertionError('No waveform read allowed')), \
                 patch('recording_workspace.connect', side_effect=AssertionError('No database connection allowed')):
                full = service.tree_fields(None)
                self.assertEqual(full['total'], 3)
                self.assertIn('parameters/unassignedSetting', {field['id'] for field in full['fields']})
                tree = service.tree(None, splits='protocol, cell')
                self.assertEqual(set(members(tree)), set(service.ids) | {outside})
                filtered = service.tree(None, {'group_label': 'Unassigned group'}, splits='parameters/unassignedSetting')
                self.assertEqual(members(filtered), [outside])
                self.assertEqual(filtered['children'][0]['value'], 7)
                absent = service.tree(None, {'group_label': 'Recorded group'}, splits='parameters/unassignedSetting')
                self.assertEqual(set(members(absent)), set(service.ids))
                self.assertTrue(absent['children'][0]['missing'])
            self.assertEqual((service.rows, service.details), before)

    def test_tree_preview_counts_unique_cells_and_sums_recorded_duration(self):
        rows = [
            {'epoch_uuid': 'a', 'cell_uuid': 'cell-a', 'block_uuid': 'block-1', 'duration_seconds': 0.5},
            {'epoch_uuid': 'b', 'cell_uuid': 'cell-a', 'block_uuid': 'block-2', 'duration_seconds': 1.5},
            {'epoch_uuid': 'c', 'cell_uuid': 'cell-b', 'block_uuid': 'block-2', 'duration_seconds': 2.0},
        ]
        tree = build_tree(rows, 'block,cell')
        self.assertEqual((tree['count'], tree['cell_count'], tree['duration_seconds']), (3, 2, 4.0))
        self.assertEqual([(child['count'], child['cell_count'], child['duration_seconds'])
                         for child in tree['children']], [(1, 1, 0.5), (2, 2, 3.5)])
        self.assertEqual(set(members(tree)), {'a', 'b', 'c'})
        rows[0]['duration_seconds'] = None
        self.assertIsNone(build_tree(rows, 'cell')['duration_seconds'])

    def test_history_suggestions_prioritize_recorded_pairs_and_separate_controls(self):
        rows, details = self.fixture([{
            'history1':[100*(i%3),500], 'history1Mean':100*(i%3),'history1SD':500,
            'history2':[0,0], 'history2Mean':0,'history2SD':0,
            'target':[0,300+100*(i%2)], 'targetMean':0,'targetSD':300+100*(i%2),
            'isControl':int(i%10==0),'segmentTime':1000+1000*(i%2),
            'blockRepeatCount':5+5*(i%2),'numberOfTrialsInRun':1+4*(i%2),
            'centerOffset':[i%2,10],'sequenceShuffleSeed':i%2,
        } for i in range(30)])
        for row in rows:row['protocol_name']='edu.washington.riekelab.chris.protocols.VariableHistoryNoiseCurInject'
        before=copy.deepcopy((rows,details))
        result,values=catalog(rows,details)
        self.assertEqual(result['protocol_family'],'history-noise')
        self.assertEqual(result['suggestions'][:3],['parameters/isControl',HISTORY_JOINT,'parameters/segmentTime'])
        fields={f['id']:f for f in result['fields']}
        self.assertFalse(fields['parameters/history2']['varying'])
        self.assertNotIn('parameters/history2',result['suggestions'])
        for key in ('blockRepeatCount','numberOfTrialsInRun','centerOffset','sequenceShuffleSeed'):
            self.assertEqual(fields['parameters/'+key]['grouping_role'],'technical')
            self.assertNotIn('parameters/'+key,result['suggestions'])
        layout=result['suggested_layout']['fields']
        self.assertEqual(layout,['date','cell type','cell','parameters/isControl',HISTORY_JOINT,'parameters/segmentTime','block'])
        tree=build_tree(rows,','.join(layout),values,{f['id'] for f in result['fields']})
        self.assertEqual(set(members(tree)),{r['epoch_uuid'] for r in rows})
        self.assertEqual((rows,details),before)

    def test_mean_noise_keeps_mean_and_sd_as_distinct_named_axes_even_if_correlated(self):
        rows,details=self.fixture([{'frequencyCutoff':25 if i%2 else 100,'currentMean':i%2,'currentSD':i%2,
                                   'seed':i,'numberOfAverages':10+10*(i%2)} for i in range(20)])
        for row in rows:row['protocol_name']='VariableMeanNoiseCurInject'
        result,_=catalog(rows,details)
        self.assertEqual(result['suggestions'][:3],['parameters/frequencyCutoff','parameters/currentMean','parameters/currentSD'])
        self.assertNotIn('parameters/numberOfAverages',result['suggestions'])
        self.assertEqual(result['suggested_layout']['fields'][:3],['date','cell type','cell'])

    def test_history_tree_labels_preserve_typed_pair_values(self):
        with tempfile.TemporaryDirectory() as folder:
            service=FixtureService(folder)
            for index,key in enumerate(service.ids):
                service.rows[key]['protocol_name']='VariableHistoryNoiseCurInject'
                service.details[key]['parameters'].update(history1=[100,500],isControl=index)
            result=service.tree(service.protocol_id,splits='parameters/isControl,parameters/history1')
            self.assertEqual([n['label'] for n in result['children']],['0 · History sequence','1 · Target-only control'])
            self.assertIn("{'parameters/isControl', 'parameters/history1'}",result['matlab_command'])
            for node in result['children']:
                self.assertEqual(node['children'][0]['value'],[100,500])
                self.assertEqual(node['children'][0]['label'],'Mean 100 · SD 500')


    def test_close_history_values_do_not_get_identical_rounded_branch_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            service=FixtureService(folder)
            for index,key in enumerate(service.ids):
                service.rows[key]['protocol_name']='VariableHistoryNoiseCurInject'
                service.details[key]['parameters']['history1']=[100.000001+index*0.000001,500]
            result=service.tree(service.protocol_id,splits='parameters/history1')
            labels=[node['label'] for node in result['children']]
            self.assertEqual(len(set(labels)),2)
            self.assertTrue(all('pA' not in label for label in labels))


if __name__ == '__main__':
    unittest.main()
