"""Joint tree levels preserve exact typed metadata tuples and membership."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from scipy.io import loadmat
from workspace_tree import (catalog, joint_id, joint_components, HISTORY_JOINT, HISTORY_COMPONENTS,
                            materialize_combinations, value_key)
from workspace_recipes import build_tree, parse_splits, seal
from workspace_matlab import build_matlab_export
if __package__:
    from . import test_workspace_tree as tree_tests
    from . import test_workspace_matlab as matlab_tests
    from .test_workspace_api import FixtureService
else:
    import test_workspace_tree as tree_tests
    import test_workspace_matlab as matlab_tests
    from test_workspace_api import FixtureService


class JointGroupingTests(unittest.TestCase):
    def fixture(self, parameters):
        return tree_tests.DynamicTreeTests().fixture(parameters)

    def test_three_parameters_form_one_level_only_when_all_match_including_constant_h2(self):
        a={'history1':[0,500],'history2':[0,0],'target':[0,300]}
        rows,details=self.fixture([a,copy.deepcopy(a),{**a,'history2':[1,0]},{**a,'history1':[100,500]},{**a,'target':[0,400]}])
        before=copy.deepcopy((rows,details))
        fields,values=catalog(rows,details)
        joint=next(field for field in fields['fields'] if field['id']==HISTORY_JOINT)
        self.assertEqual(joint['components'],HISTORY_COMPONENTS)
        self.assertEqual(joint['category'],'Combinations')
        tree=build_tree(rows,HISTORY_JOINT,values,{field['id'] for field in fields['fields']})
        self.assertEqual(len(tree['children']),4)
        self.assertEqual(sorted(child['count'] for child in tree['children']),[1,1,1,2])
        self.assertTrue(all('epoch_uuids' in child and 'children' not in child for child in tree['children']))
        self.assertEqual(set(tree_tests.members(tree)),{row['epoch_uuid'] for row in rows})
        self.assertEqual((rows,details),before)
        constant_rows,constant_details=self.fixture([a,{**a,'history1':[200,500]}])
        constant_catalog,_=catalog(constant_rows,constant_details)
        self.assertIn(HISTORY_JOINT,{field['id'] for field in constant_catalog['fields']})
        h2=next(field for field in constant_catalog['fields'] if field['id']=='parameters/history2')
        self.assertFalse(h2['varying'])

    def test_missing_null_false_empty_arrays_and_types_never_collapse(self):
        cases=[{'a':value,'b':0} for value in (None,False,0,'0','',[],[1,2],[2,1],'<not recorded>')]
        cases += [{'b':0},{'b':1}]
        rows,details=self.fixture(cases)
        fields,values=catalog(rows,details)
        identity=joint_id(['parameters/a','parameters/b'])
        original=copy.deepcopy((fields,values))
        expanded,data=materialize_combinations(fields,values,[identity])
        tree=build_tree(rows,identity,data,{field['id'] for field in expanded['fields']})
        self.assertEqual(len(tree['children']),len(cases))
        self.assertTrue(all(not child['missing'] for child in tree['children']))
        missing=[child for child in tree['children'] if not child['value'][0]['present']]
        self.assertEqual(len(missing),2)
        self.assertEqual({child['value'][1]['value'] for child in missing},{0,1})
        self.assertEqual((fields,values),original)

    def test_identifier_encoding_strict_validation_and_numeric_tuple_order(self):
        parts=['parameters/a+b','parameters/Case%2F, arrow→']
        encoded=joint_id(parts)
        self.assertEqual(encoded,'joint/' + '+'.join(quote(field,safe="~()*!.'-") for field in parts))
        self.assertNotIn(',',encoded)
        self.assertEqual(joint_components(encoded,parts),parts)
        self.assertEqual(parse_splits(encoded,parts),[encoded])
        for invalid in ('joint/cell', 'joint/cell+cell','joint/cell+unknown',
                        'joint/parameters%2fhistory1+cell',joint_id(['cell','parameters/History1'])):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                parse_splits(invalid,{'cell','parameters/history1'})
        with self.assertRaises(ValueError):joint_id(['cell',HISTORY_JOINT])
        with self.assertRaises(ValueError):joint_id([str(index) for index in range(7)])
        rows,details=self.fixture([{'a':100,'b':0},{'a':25,'b':0}])
        fields,values=catalog(rows,details)
        combo=joint_id(['parameters/a','parameters/b'])
        tree=build_tree(rows,combo,values,{field['id'] for field in fields['fields']})
        self.assertEqual([child['value'][0]['value'] for child in tree['children']],[25,100])

    def test_service_materializes_requested_combinations_and_keeps_predicates_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            service=FixtureService(folder)
            for index,key in enumerate(service.ids):
                service.details[key]['parameters']={'history1':[index*100,500],'history2':[0,0],'target':[0,300]}
            ordinary=service.tree_fields(None)
            combo=joint_id(['parameters/history1','group label'])
            self.assertNotIn(combo,{field['id'] for field in ordinary['fields']})
            before=copy.deepcopy((service.rows,service.details,service._fingerprints))
            with patch('h5py.File',side_effect=AssertionError('No waveform reads')):
                expanded=service.tree_fields(service.protocol_id,splits=combo)
                self.assertIn(combo,{field['id'] for field in expanded['fields']})
                tree=service.tree(service.protocol_id,splits=combo)
                self.assertEqual(tree['levels'][0]['components'],['parameters/history1','group label'])
                self.assertEqual(tree['children'][0]['components'][0]['display_value'],'Mean 0 · SD 500')
                self.assertEqual(tree['children'][0]['components'][0]['field'],'parameters/history1')
                named=service.tree(service.protocol_id,splits=joint_id(['cell','block']))
                for branch in named['children']:
                    cell,block=branch['components']
                    self.assertIn('2026-09-24 · Cell',cell['display_value'])
                    self.assertTrue(block['display_value'].startswith('Block · '))
                    self.assertIn(cell['value'],service.cells)
                    self.assertNotEqual(cell['value'],cell['display_value'])
                preview=service.explore_preview({'all':[]},combo)
                self.assertEqual(preview['matched_count'],2)
                self.assertIn(combo,{field['id'] for field in preview['catalog']['fields']})
                self.assertFalse(any(field['id'].startswith('joint/') for field in service.predicate_fields()['fields']))
                with self.assertRaisesRegex(ValueError,'recorded field'):
                    service.explore_preview({'field':HISTORY_JOINT,'operator':'exists'},HISTORY_JOINT)
            self.assertEqual((service.rows,service.details,service._fingerprints),before)
            self.assertNotIn(combo,{field['id'] for field in service.tree_fields(None)['fields']})

    def test_joint_definition_survives_empty_subset_and_incomplete_components_are_visible(self):
        rows,details=self.fixture([{'history1':[0,1],'history2':[0,0],'target':[0,2]}, {'history1':[0,1],'target':None}])
        full,_=catalog(rows,details)
        empty,values=catalog([],details,full['fields'])
        definition=next(field for field in empty['fields'] if field['id']==HISTORY_JOINT)
        self.assertEqual(definition['components'],HISTORY_COMPONENTS)
        self.assertEqual(build_tree([],HISTORY_JOINT,values,{field['id'] for field in empty['fields']})['count'],0)
        with tempfile.TemporaryDirectory() as folder:
            service=FixtureService(folder)
            for key,data in zip(service.ids,details.values()): service.details[key]['parameters']=data['parameters']
            tree=service.tree(service.protocol_id,splits=HISTORY_JOINT)
            self.assertEqual(tree['levels'][0]['missing_epochs'],1)
            incomplete=next(child for child in tree['children'] if child['has_missing_components'])
            self.assertEqual(incomplete['components'][1]['display_value'],'Not recorded')
            self.assertEqual(incomplete['components'][2]['display_value'],'null (recorded)')

    def test_matlab_freezes_composite_id_values_order_and_exact_membership(self):
        case=matlab_tests.MatlabExportTests();case.setUp();self.addCleanup(case.doCleanups)
        for index,key in enumerate(case.service.ids):
            case.service.details[key]['parameters']={'history1':[25 if index else 100,500],'history2':[0,0],'target':[0,300]}
        recipe=copy.deepcopy(case.recipe);recipe['options']['split_order']=HISTORY_JOINT
        recipe=seal({key:value for key,value in recipe.items() if key!='content_sha256'})
        result=build_matlab_export(case.service,recipe,Path(case.temp.name)/'composite',epoch_records=case.records)
        data=loadmat(result['mat_path'],simplify_cells=True)
        mapping=json.loads(data['metadata']['split_mapping_json'])
        self.assertEqual(mapping[0]['field'],HISTORY_JOINT)
        values=[json.loads(epoch['workspaceGrouping']['g001']) for epoch in matlab_tests.epochs(data)]
        self.assertTrue(all(len(value)==3 and value[1]=={'present':True,'value':[0,0]} for value in values))
        self.assertEqual({epoch['h5_uuid'] for epoch in matlab_tests.epochs(data)},set(case.service.ids))
        order=json.loads(data['metadata']['split_value_order_json'])[0]['values']
        self.assertEqual([json.loads(value)[0]['value'][0] for value in order],[25,100])
        self.assertIn("{{'parameters/history1', 'parameters/history2', 'parameters/target'}}",Path(result['launch_script_path']).read_text())
        self.assertEqual(mapping[0]['components'],HISTORY_COMPONENTS)
        display=json.loads(data['metadata']['split_display_json'])
        self.assertEqual(display[0]['field'],HISTORY_JOINT)
        self.assertIn('History',display[0]['label'])
        self.assertNotIn('present',display[0]['values'][0]['label'])

class JointHTTPTests(unittest.TestCase):
    def test_generic_joint_save_export_and_restore_keep_ids_and_component_definitions(self):
        if __package__:
            from . import test_workspace_api as api_tests
        else:
            import test_workspace_api as api_tests
        case=api_tests.WorkspaceAPITests();case.setUp();self.addCleanup(case.doCleanups)
        combo=joint_id(['date','parameters/example'])
        before=copy.deepcopy((case.service.rows,case.service.details))
        fields=case.client.get(case.base+'/tree-fields',query_string={'splits':combo})
        self.assertEqual(fields.status_code,200,fields.get_json())
        self.assertIn(combo,{field['id'] for field in fields.get_json()['fields']})
        preview=case.client.post('/api/explore/preview',headers=case.headers,json={'predicate':{'all':[]},'splits':combo})
        self.assertEqual(preview.status_code,200,preview.get_json())
        self.assertEqual(preview.get_json()['tree']['levels'][0]['components'],['date','parameters/example'])
        saved=case.client.post('/api/explore/revisions',headers=case.headers,json={'predicate':{'all':[]},'splits':combo,'name':'Joint fixture'})
        self.assertEqual(saved.status_code,201,saved.get_json())
        self.assertEqual(saved.get_json()['recipe']['splits'],combo)
        exported=case.client.post(case.base+'/exports',headers=case.headers,json={'query_revision':case.revision(),'split_order':combo})
        self.assertEqual(exported.status_code,201,exported.get_json())
        package=case.client.get(exported.get_json()['download_url']).get_json()
        self.assertEqual(package['recipe']['options']['tree_view']['fields'][0]['components'],['date','parameters/example'])
        self.assertEqual({row['epoch_uuid'] for row in package['epochs']},set(case.service.ids))
        reused=case.client.get('/api/exports/'+exported.get_json()['dataset_uuid']+'/reuse').get_json()
        self.assertEqual(reused['split_order'],combo)
        rejected=case.client.post('/api/explore/preview',headers=case.headers,json={'predicate':{'field':combo,'operator':'exists'},'splits':combo})
        self.assertEqual(rejected.status_code,400)
        self.assertEqual((case.service.rows,case.service.details),before)
