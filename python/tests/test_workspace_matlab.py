"""MAT v5 round trips against real loader fields, with no research writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import numpy as np
from scipy.io import loadmat

from workspace_matlab import build_matlab_export
from workspace_recipes import capture_query, prepare_export, seal
if __package__:
    from .test_workspace_api import FixtureService
else:
    from test_workspace_api import FixtureService


def seq(value):
    return [value] if isinstance(value, dict) else list(value)


def epochs(data):
    return [epoch for exp in seq(data['experiments']) for cell in seq(exp['cells'])
            for group in seq(cell['epoch_groups']) for block in seq(group['epoch_blocks'])
            for epoch in seq(block['epochs'])]


class MatlabExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FixtureService(self.temp.name)
        self.source_uuid = str(uuid.uuid4())
        self.service.sources[0].update(experiment_uuid=self.source_uuid,
            metadata={'uuid': self.source_uuid, 'label': 'Fixture recording', 'rig_type': 'PATCH'})
        for index, key in enumerate(self.service.ids):
            row = self.service.rows[key]
            stream_uuid = str(uuid.uuid4())
            stimulus_uuid = str(uuid.uuid4())
            row['streams'] = [
                {'uuid': stream_uuid, 'device': 'Amp1', 'kind': 'responses', 'sample_rate': 10000,
                 'sample_rate_units': 'Hz', 'units': 'pA', 'sample_count': 200,
                 'h5_path': '/epoch-' + key + '/responses/amp'},
                {'uuid': stimulus_uuid, 'device': 'Amp1', 'kind': 'stimuli', 'sample_rate': None,
                 'sample_rate_units': None, 'units': None, 'sample_count': None,
                 'h5_path': '/epoch-' + key + '/stimuli/amp'}]
            detail = self.service.details[key]
            detail['metadata'] = {'cell': {'uuid': row['cell_uuid']}, 'group': {'uuid': row['group_uuid']},
                'block': {'uuid': row['block_uuid'], 'parameters': {'cutoff': 100}},
                'epoch': {'uuid': key, 'label': 'Epoch',
                    'responses': {'Amp1': {'uuid': stream_uuid, 'sampleRate': 10000}},
                    'stimuli': {'Amp1': {'uuid': stimulus_uuid, 'stimulusID': 'Recorded.Generator', 'units': 'V'}},
                    'attributes': {'ticks': 639258608779858225}}}
        result = self.service.query_result(self.service.protocol_id)
        snapshot = capture_query(self.service.protocols[self.service.protocol_id]['definition'], result,
                                 str(Path(self.temp.name) / 'catalog.json'))
        self.recipe = prepare_export(snapshot, self.service.ids, destination='matlab',
            review_policy='include_unreviewed', actor='fixture', options={'split_order': 'parameters/example,cell'})
        self.records = [{'epoch_uuid': key, 'curation': {'included': True, 'tags': ['check'], 'revision': 2}}
                        for key in self.service.ids]

    def test_matlab_struct_roundtrip_preserves_exact_hierarchy_ids_units_and_lazy_refs(self):
        before = copy.deepcopy((self.service.rows, self.service.details))
        with patch('h5py.File', side_effect=AssertionError('Lazy export must not read traces')):
            result = build_matlab_export(self.service, self.recipe, Path(self.temp.name) / 'export', epoch_records=self.records)
        data = loadmat(result['mat_path'], simplify_cells=True)
        self.assertEqual(data['format_version'], '1.0')
        self.assertEqual(data['experiments']['h5_uuid'], self.source_uuid)
        exported = epochs(data)
        self.assertEqual({epoch['h5_uuid'] for epoch in exported}, set(self.service.ids))
        self.assertEqual([epoch['h5_uuid'] for epoch in exported], result['epoch_order'])
        for epoch in exported:
            row = self.service.rows[epoch['h5_uuid']]
            response = epoch['responses']
            self.assertEqual(response['h5_uuid'], row['streams'][0]['uuid'])
            self.assertEqual(response['units'], 'pA')
            self.assertEqual(response['sample_rate'], 10000)
            self.assertEqual(response['h5_file'], self.service.sources[0]['source_path'])
            self.assertEqual(response['source_sha256'], row['source_sha256'])
            self.assertEqual(response['h5_path'], row['streams'][0]['h5_path'])
            self.assertEqual(np.size(response['data']), 0)
            self.assertEqual(epoch['stimuli']['units'], 'V')
            self.assertEqual(np.size(epoch['stimuli']['sample_rate']), 0)
            self.assertEqual(epoch['tags']['tag'], 'check')
            exact = json.loads(epoch['source_metadata_json'])
            self.assertEqual(exact['metadata']['epoch']['attributes']['ticks'], 639258608779858225)
        self.assertEqual(json.loads(data['metadata']['recipe_json']), self.recipe)
        self.assertEqual(result['split_mapping'][0]['field'], 'parameters/example')
        self.assertIn("launchWorkspaceTree(fullfile(exportFolder, 'recordings.mat'), {'parameters/example', 'cell'})", Path(result['launch_script_path']).read_text())
        self.assertEqual((self.service.rows, self.service.details), before)
        script = Path(result['launch_script_path']).read_text()
        helper = Path(result['mat_path']).with_name('launchWorkspaceTree.m').read_text()
        self.assertIn("'LoadUserMetadata', 'none'", helper)
        self.assertIn("'selection.ugm'", helper)
        self.assertIn('loadUserMetadata', helper)
        self.assertIn(result['matlab_command'], Path(result['mat_path']).with_name('tree_layout.m').read_text())
        # checked buildTreeFromEpicData indexes struct arrays, not cell arrays.
        raw = loadmat(result['mat_path'])
        self.assertIsNotNone(raw['experiments'].dtype.names)
        self.assertIsNotNone(raw['experiments']['cells'][0, 0].dtype.names)

    def test_epoch_sequence_is_chronological_with_uuid_ties_not_hierarchy_order(self):
        physical = sorted(self.service.ids, key=lambda key: self.service.rows[key]['cell_uuid'])
        for key, stamp in zip(physical, ['09/24/2026 18:13:32:038154','09/24/2026 18:13:32:038153']):
            self.service.rows[key]['start_time'] = stamp
        result = build_matlab_export(self.service, self.recipe, Path(self.temp.name) / 'sequenced')
        data = loadmat(result['mat_path'], simplify_cells=True)
        self.assertEqual(result['epoch_order'], physical)
        self.assertEqual(json.loads(data['metadata']['epoch_sequence_json']), physical[::-1])
        # Equal timestamps have a stable UUID tie-break, regardless of cell IDs.
        for row in self.service.rows.values():
            row['start_time'] = '09/24/2026 18:13:32:038153'
        tied = build_matlab_export(self.service, self.recipe, Path(self.temp.name) / 'tied')
        self.assertEqual(json.loads(loadmat(tied['mat_path'], simplify_cells=True)['metadata']['epoch_sequence_json']), sorted(self.service.ids))

    def test_matlab_value_order_matches_web_numeric_missing_and_typed_values(self):
        from workspace_matlab import _grouping_order, _grouping_value
        from workspace_recipes import build_tree
        from workspace_tree import catalog, value_key
        values=[25,100,'25',[1,2],None,True,'<not recorded>']
        rows=[];details={}
        for index,value in enumerate(values):
            identity=str(uuid.uuid4());rows.append({'epoch_uuid':identity,'cell_uuid':'cell','start_time':'2026-09-24'})
            details[identity]={'parameters':{'value':value},'properties':{},'metadata':{}}
        identity=str(uuid.uuid4());rows.append({'epoch_uuid':identity,'cell_uuid':'cell','start_time':'2026-09-24'})
        details[identity]={'parameters':{},'properties':{},'metadata':{}}
        _,field_values=catalog(rows,details)
        tree=build_tree(rows,'parameters/value',field_values)
        expected=['<not recorded>' if child['missing'] else value_key(child['value']) for child in tree['children']]
        self.assertEqual(_grouping_order(rows,field_values,['parameters/value'])[0]['values'],expected)
        self.assertEqual(expected[:2],['25','100'])
        self.assertEqual(expected[-1],'<not recorded>')
        self.assertIn('"<not recorded>"',expected)
        self.assertEqual(_grouping_value({'group label':None},'group label'),'<not recorded>')
        self.assertEqual(_grouping_value({'parameters/value':None},'parameters/value'),'null')


    def test_subset_is_exact_and_no_frozen_tags_means_no_live_curation_lookup(self):
        recipe = copy.deepcopy(self.recipe)
        recipe['epochs'] = recipe['epochs'][:1]
        recipe = seal({key: value for key, value in recipe.items() if key != 'content_sha256'})
        result = build_matlab_export(self.service, recipe, Path(self.temp.name) / 'subset')
        self.assertEqual([epoch['h5_uuid'] for epoch in epochs(loadmat(result['mat_path'], simplify_cells=True))],
                         [recipe['epochs'][0]['uuid']])
        self.assertTrue(any('No frozen protocol tags' in warning for warning in result['warnings']))
        with self.assertRaisesRegex(ValueError, 'already exist'):
            build_matlab_export(self.service, recipe, Path(self.temp.name) / 'subset')

    def test_typed_grouping_and_unsupported_matlab_names_preserve_exact_metadata(self):
        for index, key in enumerate(self.service.ids):
            self.service.details[key]['parameters'] = {'example': 1 if index == 0 else '1',
                                                       '_private name': 42}
        result = build_matlab_export(self.service, self.recipe, Path(self.temp.name) / 'typed', epoch_records=self.records)
        exported = epochs(loadmat(result['mat_path'], simplify_cells=True))
        self.assertEqual({epoch['workspaceGrouping']['g001'] for epoch in exported}, {'1', '"1"'})
        self.assertEqual(json.loads(exported[0]['source_metadata_json'])['parameters']['_private name'], 42)
        self.assertTrue(result['warnings'])

    def test_changed_metadata_bad_membership_and_hierarchy_fail_before_writing(self):
        out = Path(self.temp.name) / 'failed'
        self.service._fingerprints[self.service.ids[0]] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            build_matlab_export(self.service, self.recipe, out)
        self.assertFalse(out.exists())
        self.service._fingerprints[self.service.ids[0]] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'exactly match'):
            build_matlab_export(self.service, self.recipe, out, epoch_records=self.records[:1])
        self.service.details[self.service.ids[0]]['metadata']['cell']['uuid'] = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, 'hierarchy UUID'):
            build_matlab_export(self.service, self.recipe, out)
        self.assertFalse(out.exists())

    def test_parameter_flattening_collision_fails_instead_of_overwriting(self):
        self.service.details[self.service.ids[0]]['parameters'] = {'a': {'b': 1}, 'a_b': 2, 'example': 1}
        with self.assertRaisesRegex(ValueError, 'collide'):
            build_matlab_export(self.service, self.recipe, Path(self.temp.name) / 'collision')

    def test_multiple_sources_preserve_each_experiment_and_stream_file(self):
        other = copy.deepcopy(self.service.sources[0])
        other.update(source_sha256='c' * 64, source_path='/fixture/second.h5', experiment_uuid=str(uuid.uuid4()))
        other['metadata']['uuid'] = other['experiment_uuid']
        self.service.sources.append(other)
        self.service.rows[self.service.ids[1]]['source_sha256'] = other['source_sha256']
        recipe = copy.deepcopy(self.recipe)
        recipe['source_revisions'].append(other['source_sha256'])
        recipe = seal({key: value for key, value in recipe.items() if key != 'content_sha256'})
        result = build_matlab_export(self.service, recipe, Path(self.temp.name) / 'multiple')
        data = loadmat(result['mat_path'], simplify_cells=True)
        self.assertEqual(len(seq(data['experiments'])), 2)
        for exp in seq(data['experiments']):
            expected = next(source for source in self.service.sources if source['experiment_uuid'] == exp['h5_uuid'])
            epoch = epochs({'experiments': exp})[0]
            self.assertEqual(epoch['responses']['h5_file'], expected['source_path'])
            self.assertEqual(epoch['stimuli']['h5_file'], expected['source_path'])
        self.assertEqual(set(result['epoch_order']), set(self.service.ids))
