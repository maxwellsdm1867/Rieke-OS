"""Paged metadata grouping has exactly the full-tree identities and typed keys."""
import copy
import json
import tempfile
import unittest
import uuid
from contextlib import nullcontext
from threading import RLock
from unittest.mock import patch

from flask import Flask
from workspace_tree_pages import TreePages, StaleTreePage, register_tree_page_routes
from workspace_tree import joint_id, value_key
from test_workspace_api import FixtureService


class TreePageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.service = FixtureService(self.temp.name)
        template = copy.deepcopy(self.service.rows[self.service.ids[0]])
        self.service.rows = {}; self.service.details = {}; self.service._fingerprints = {}
        parameters = [{'value':value, 'other':[1,2]} for value in (10,2,1,'1',True,[1,2],None,'')]
        parameters += [{'other':[1,2]}, {'value':1,'other':[1,3]}]
        for index, params in enumerate(parameters):
            key = str(uuid.UUID(int=index+1))
            self.service.rows[key] = {**template,'epoch_uuid':key,'epoch_number':index+1,
                'start_time':f'09/24/2026 12:00:{9-index:02d}:000000',
                'duration_seconds':None if index==0 else 1}
            self.service.details[key] = {'parameters':params,'properties':{},'metadata':{}}
            self.service._fingerprints[key] = 'b'*64
        self.service.protocols[self.service.protocol_id]['result']['epochs'] = [
            {'uuid':key,'metadata_hash':'b'*64} for key in self.service.rows]
        self.pager = TreePages(self.service)

    def collect(self, request):
        root = self.pager.page(request)
        leaves, paths = [], []
        def walk(page):
            if page['kind']=='epochs':
                leaves.extend(row['epoch_uuid'] for row in page['epochs'])
            else:
                for branch in page['branches']:
                    paths.append((branch['missing'],value_key(branch['value'])))
                    walk(self.pager.page({**request,'path':branch['path'],'revision':root['revision']}))
            if page['has_more']:
                walk(self.pager.page({**request,'path':page['path'],'offset':page['offset']+page['limit'],
                                     'revision':root['revision']}))
        walk(root)
        return leaves, paths

    def test_all_typed_branches_pages_preserve_exact_membership_and_labels(self):
        body = {'protocol_uuid':self.service.protocol_id,'splits':'parameters/value','limit':2}
        before = copy.deepcopy((self.service.rows,self.service.details))
        with patch('h5py.File',side_effect=AssertionError('No waveform access')):
            root = self.pager.page(body)
            identities, paths = self.collect(body)
        self.assertEqual(root['total'],9)
        self.assertEqual([branch['value'] for branch in root['branches']],[1,2])
        self.assertEqual(len(identities),10)
        self.assertEqual(set(identities),set(self.service.rows))
        self.assertIn((True,'null'),paths); self.assertIn((False,'null'),paths)
        self.assertIn((False,'true'),paths); self.assertIn((False,'"1"'),paths)
        self.assertIsNone(root['duration_seconds'])
        self.assertEqual((self.service.rows,self.service.details),before)
        self.assertNotIn('epoch_uuids',json.dumps(root))

    def test_composite_components_and_sequential_layout_have_same_membership(self):
        combined = joint_id(['parameters/value','parameters/other'])
        root = self.pager.page({'splits':combined})
        self.assertEqual(root['levels'][0]['components'],['parameters/value','parameters/other'])
        self.assertEqual(root['total'],10)
        self.assertTrue(all(len(branch['components'])==2 for branch in root['branches']))
        first,_ = self.collect({'splits':combined})
        second,_ = self.collect({'splits':'parameters/other,parameters/value'})
        self.assertEqual(set(first),set(second))
        self.assertTrue(any(branch['has_missing_components'] for branch in root['branches']))

    def test_anchor_returns_exact_chronological_leaf_page_and_ancestors(self):
        identity = str(uuid.UUID(int=2))
        result = self.pager.page({'splits':'cell','anchor_uuid':identity,'limit':3})
        self.assertEqual(result['kind'],'epochs')
        self.assertEqual(result['anchor']['index'],8)
        self.assertEqual(result['offset'],6)
        self.assertIn(identity,[row['epoch_uuid'] for row in result['epochs']])
        self.assertEqual(result['path'],result['ancestors'][0]['path'])
        self.assertIn('Cell1',result['ancestors'][0]['label'])
        flat = self.pager.page({'splits':'','anchor_uuid':identity,'limit':3})
        self.assertEqual(flat['path'],[])
        self.assertEqual(flat['anchor']['index'],8)

    def test_anchor_locates_parent_branch_page_beyond_first_page(self):
        root = self.pager.page({'splits':'parameters/value','limit':100})
        offsets = []
        for identity in self.service.rows:
            leaf = self.pager.page({'splits':'parameters/value','anchor_uuid':identity,'limit':2})
            ancestor = leaf['ancestors'][0]
            index = next(i for i,b in enumerate(root['branches']) if b['key']==ancestor['key'])
            self.assertEqual(ancestor['parent_offset'],index // 2 * 2)
            parent = self.pager.page({'splits':'parameters/value','offset':ancestor['parent_offset'],'limit':2,'revision':leaf['revision']})
            self.assertIn(ancestor['key'],[b['key'] for b in parent['branches']])
            offsets.append(ancestor['parent_offset'])
        self.assertGreater(max(offsets),0)

    def test_stale_metadata_layout_eligibility_and_invalid_continuations_fail_closed(self):
        root = self.pager.page({'splits':'cell'})
        continuation = {'splits':'cell','revision':root['revision'],'path':root['branches'][0]['path']}
        self.service._fingerprints[next(iter(self.service.rows))] = 'c'*64
        with self.assertRaises(StaleTreePage): self.pager.page(continuation)
        for body in ({'splits':'no-such-field'},{'limit':True},{'limit':101},{'offset':-1},
                     {'path':['a'*64]},{'path':'bad'},{'revision':'bad'}, {'extra':True},
                     {'protocol_uuid':self.service.protocol_id,'predicate':{'all':[]}}):
            with self.subTest(body=body),self.assertRaises(ValueError):self.pager.page(body)
        fresh=self.pager.page({'splits':'cell'})
        with self.assertRaises(StaleTreePage):self.pager.page({'splits':'date','revision':fresh['revision']})
        with self.assertRaises(KeyError):self.pager.page({'splits':'cell','anchor_uuid':str(uuid.uuid4())})
        with self.assertRaises(KeyError):self.pager.page({'splits':'cell','path':['a'*64],'revision':fresh['revision']})

    def test_source_predicate_is_respected_before_not_and_grouping(self):
        result = self.pager.page({'splits':'','predicate':{'not':{'field':'parameters/value','operator':'eq','value':1}}})
        self.assertEqual(result['total'],8)
        self.assertNotIn(str(uuid.UUID(int=3)),[row['epoch_uuid'] for row in result['epochs']])
        self.service.set_source_state_provider(lambda: {'a'*64:{'query_excluded':True}})
        excluded = self.pager.page({'splits':'parameters/value','predicate':{'all':[]}})
        self.assertEqual(excluded['total_epochs'],0)
        self.assertEqual(excluded['branches'],[])
        bound = self.pager.page({'protocol_uuid':self.service.protocol_id,'splits':''})
        self.assertEqual(bound['total_epochs'],10)

    def test_disk_adapter_reads_only_navigation_columns_and_preserves_missing(self):
        from unittest.mock import Mock
        from workspace_predicates import evaluate
        catalog,values = self.service._registered_tree_fields()
        class Index:
            calls=[]
            def catalog(inner):return catalog
            def values(inner,ids=None,fields=None):
                inner.calls.append((ids,fields))
                return {key:{field:value for field,value in values[key].items() if field in fields} for key in ids}
            def match(inner,predicate,ids=None):
                registered = {**catalog,'fields':[field for field in catalog['fields'] if not field['id'].startswith('joint/')]}
                return evaluate(predicate,registered,{key:values[key] for key in ids})
        self.service.disk_index=Index()
        with patch.object(self.service,'_tree_fields',side_effect=AssertionError('No full in-memory catalog')):
            root=self.pager.page({'splits':'cell,parameters/value'})
            self.assertEqual(self.service.disk_index.calls[-1][1],['cell'])
            leaf_groups=self.pager.page({'splits':'cell,parameters/value','path':root['branches'][0]['path'],'revision':root['revision']})
            self.assertEqual(self.service.disk_index.calls[-1][1],['cell','parameters/value'])
            self.assertEqual(leaf_groups['total'],9)
            filtered=self.pager.page({'splits':'','predicate':{'field':'parameters/value','operator':'eq','value':1}})
            self.assertEqual(filtered['total'],2)
            combined=joint_id(['parameters/value','parameters/other'])
            result=self.pager.page({'splits':combined})
            self.assertEqual(result['total'],10)
            self.assertEqual(self.service.disk_index.calls[-1][1],['parameters/other','parameters/value'])

    def test_real_disk_index_pages_match_in_memory_tree_exactly(self):
        from pathlib import Path
        from workspace_disk_index import DiskMetadataIndex
        combined=joint_id(['parameters/value','parameters/other'])
        bodies=[{'splits':'parameters/value','limit':3},
                {'splits':combined,'limit':2},
                {'splits':'cell,parameters/value','anchor_uuid':str(uuid.UUID(int=9))},
                {'splits':'','predicate':{'not':{'field':'parameters/value','operator':'eq','value':1}}}]
        expected=[self.pager.page(body) for body in bodies]
        expected_members=self.collect({'splits':combined,'limit':2})
        index=DiskMetadataIndex.build(Path(self.temp.name)/'metadata.sqlite',list(self.service.rows.values()),
            self.service.details,self.service.sources,'fixture-generation',self.service.project['project_uuid'])
        self.service.disk_index=index
        with patch.object(self.service,'_tree_fields',side_effect=AssertionError('No eager fallback')):
            for body,wanted in zip(bodies,expected):
                self.assertEqual(self.pager.page(body),wanted)
            self.assertEqual(self.collect({'splits':combined,'limit':2}),expected_members)

    def test_many_branches_render_only_requested_representatives(self):
        from benchmark_workspace_metadata import synthetic_service
        service,_ = synthetic_service(2000)
        pager = TreePages(service)
        with patch.object(service,'_render_tree',wraps=service._render_tree) as render:
            first = pager.page({'splits':'parameters/seed','limit':7})
            second = pager.page({'splits':'parameters/seed','limit':7,'offset':7,'revision':first['revision']})
        self.assertEqual(first['total'],2000)
        self.assertEqual(len(first['branches']),7)
        self.assertEqual([len(call.args[0]) for call in render.call_args_list],[7,7])
        self.assertTrue(set(row['key'] for row in first['branches']).isdisjoint(row['key'] for row in second['branches']))
        self.assertLess(len(json.dumps(first)),15000)
        self.assertNotIn('epoch_uuids',json.dumps(first))

    def test_json_decoder_depth_overflow_is_bad_request_before_selection(self):
        app=Flask(__name__)
        app.register_error_handler(ValueError,lambda error: ({'error':str(error)},400))
        register_tree_page_routes(app,self.service,RLock(),nullcontext)
        body='{"predicate":'+('{"not":'*1100)+'{"all":[]}'+('}'*1100)+',"splits":""}'
        self.assertLess(len(body),65536)
        before=copy.deepcopy((self.service.rows,self.service.details,self.service._fingerprints))
        with patch.object(self.service,'_tree_rows',side_effect=AssertionError('Reject before selection')):
            response=app.test_client().post('/api/tree-pages',data=body,content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.assertIn('nesting',response.get_json()['error'])
        self.assertEqual((self.service.rows,self.service.details,self.service._fingerprints),before)

    def test_http_route_bounded_response_and_stale_status(self):
        app=Flask(__name__)
        app.register_error_handler(ValueError,lambda error: ({'error':str(error)},400))
        register_tree_page_routes(app,self.service,RLock(),nullcontext)
        client=app.test_client()
        root=client.post('/api/tree-pages',json={'splits':'cell'}).get_json()
        self.service._fingerprints[next(iter(self.service.rows))]='c'*64
        response=client.post('/api/tree-pages',json={'splits':'cell','revision':root['revision']})
        self.assertEqual(response.status_code,409)
        self.assertEqual(client.post('/api/tree-pages?bad=1',json={}).status_code,400)
        self.assertEqual(client.post('/api/tree-pages',json=[]).status_code,400)

if __name__=='__main__':unittest.main()
