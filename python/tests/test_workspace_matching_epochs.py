"""Exact preview inspection pages and compact annotation transport; isolated DB."""
import copy
import unittest
import uuid
from unittest.mock import patch

import test_workspace_api as api_fixture
from workspace_recipes import capture_query


class MatchingEpochTests(unittest.TestCase):
    def setUp(self):
        self.fixture=api_fixture.WorkspaceAPITests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service=self.fixture.service;self.client=self.fixture.client;self.headers=self.fixture.headers
        self.predicate={'all':[]};self.splits='cell'

    def preview(self,predicate=None):
        response=self.client.post('/api/explore/preview',json={'predicate':self.predicate if predicate is None else predicate,
            'splits':self.splits,'summary_only':True},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json());return response.get_json()

    def page(self,expected_revision=None,**overrides):
        body={'predicate':self.predicate,'splits':self.splits,'revision':expected_revision or self.preview()['tree_revision'],**overrides}
        return self.client.post('/api/explore/epochs',json=body,headers=self.headers)

    def test_pagination_is_chronological_bounded_metadata_only_and_preserves_names(self):
        first,second=self.service.ids
        self.service.rows[first]['start_time']='09/24/2026 12:00:09:000000'
        self.service.rows[first]['protocol_name']='fixture.HistoryProtocol'
        self.service.rows[second]['protocol_name']='fixture.OtherProtocol'
        revision=self.preview()['tree_revision'];events=copy.deepcopy(self.fixture.events.rows)
        with patch('h5py.File',side_effect=AssertionError('Matching pages must not read waveforms')):
            a=self.page(revision,limit=1).get_json();b=self.page(revision,offset=1,limit=1).get_json()
            end=self.page(revision,offset=2,limit=1).get_json()
        self.assertEqual([a['epochs'][0]['epoch_uuid'],b['epochs'][0]['epoch_uuid']],[second,first])
        self.assertEqual(a['epochs'][0]['protocol_name'],'fixture.OtherProtocol')
        self.assertEqual(b['epochs'][0]['protocol_name'],'fixture.HistoryProtocol')
        self.assertEqual(a['epochs'][0]['cell_uuid'],self.service.rows[second]['cell_uuid'])
        self.assertEqual(a['epochs'][0]['date'],'2026-09-24')
        self.assertEqual((a['total'],a['has_more'],b['has_more']),(2,True,False))
        self.assertEqual(end['epochs'],[])
        self.assertEqual(a['revision'],revision)
        self.assertFalse({'metadata','responses','parameters','curation'} & a['epochs'][0].keys())
        self.assertEqual(self.fixture.events.rows,events)

    def test_cell_overview_is_complete_and_cell_pages_never_broaden_predicate(self):
        first,second=self.service.ids
        cell=self.service.rows[first]['cell_uuid']
        revision=self.preview()['tree_revision']
        with patch('h5py.File',side_effect=AssertionError('Overview must not read traces')):
            data=self.page(revision,limit=1,include_cells=True).get_json()
            scoped=self.page(revision,cell_uuid=cell,include_cells=True).get_json()
        self.assertEqual(len(data['epochs']),1)
        self.assertEqual(len(data['cells']),2)
        self.assertEqual(sum(item['epochs'] for item in data['cells']),2)
        self.assertEqual([row['epoch_uuid'] for row in scoped['epochs']],[first])
        self.assertEqual(len(scoped['cells']),2)
        self.assertEqual(self.page(revision,cell_uuid=cell,anchor_uuid=second).status_code,400)
        self.predicate={'field':'parameters/example','operator':'eq','value':0}
        narrowed=self.preview()['tree_revision']
        other=self.service.rows[second]['cell_uuid']
        empty=self.page(narrowed,cell_uuid=other,include_cells=True).get_json()
        self.assertEqual(empty['epochs'],[])
        self.assertEqual([row['cell_uuid'] for row in empty['cells']],[cell])
        for invalid in ({'cell_uuid':False},{'cell_uuid':'bad'},{'include_cells':1}):
            self.assertEqual(self.page(narrowed,**invalid).status_code,400)

    def test_anchor_locates_exact_page_and_never_broadens_predicate(self):
        target=self.service.ids[1];revision=self.preview()['tree_revision']
        anchored=self.page(revision,anchor_uuid=target,limit=1)
        self.assertEqual(anchored.status_code,200,anchored.get_json())
        data=anchored.get_json()
        self.assertEqual((data['anchor_uuid'],data['anchor_index'],data['offset']),(target,1,1))
        self.assertEqual(data['epochs'][0]['epoch_uuid'],target)
        self.predicate={'field':'parameters/example','operator':'eq','value':0}
        narrowed=self.preview()['tree_revision']
        outside=self.page(narrowed,anchor_uuid=target)
        self.assertEqual(outside.status_code,400)
        self.assertIn('outside this predicate',outside.get_json()['error'])
        self.assertEqual(self.page(narrowed,anchor_uuid=str(uuid.uuid4())).status_code,400)

    def test_metadata_scope_and_tag_changes_require_new_preview(self):
        revision=self.preview()['tree_revision']
        self.service._fingerprints[self.service.ids[0]]='c'*64
        changed=self.page(revision)
        self.assertEqual(changed.status_code,409,changed.get_json())
        self.assertEqual(self.page().status_code,200)
        field=f'curation/{self.service.protocol_id}/tags'
        self.predicate={'field':field,'operator':'contains','value':'keep'}
        self._tag(['keep'])
        revision=self.preview()['tree_revision']
        self._tag(['additional-note'])
        stale=self.page(revision)
        self.assertEqual(stale.status_code,409,stale.get_json())
        current=self.page().get_json()
        self.assertEqual([row['epoch_uuid'] for row in current['epochs']],[self.service.ids[0]])

    def test_excluded_sources_leave_new_pages_but_preserve_working_dataset(self):
        revision=self.preview()['tree_revision'];source='a'*64
        response=self.client.post('/api/data-stores/'+source+'/state',json={
            'action':'exclude','expected_version':0,'reason':'Disposable page exclusion'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.page(revision).status_code,409)
        fresh=self.page().get_json()
        self.assertEqual((fresh['epochs'],fresh['total']),([],0))
        self.predicate={'not':{'any':[]}}
        self.assertEqual(self.page().get_json()['total'],0)
        self.assertEqual(self.client.get(self.fixture.base+'/epochs').get_json()['total'],2)

    def test_invalid_page_requests_fail_before_scope_evaluation(self):
        revision=self.preview()['tree_revision']
        bad=[{'limit':True},{'limit':0},{'limit':101},{'offset':True},{'offset':-1},
             {'offset':10_000_001},{'revision':'not-a-revision'},{'anchor_uuid':False},
             {'anchor_uuid':'not-a-uuid'},{'anchor_uuid':self.service.ids[0],'offset':1},
             {'unsupported':'value'}]
        with patch.object(self.service,'match_predicate',side_effect=AssertionError('Invalid pages must not evaluate')):
            for change in bad:
                with self.subTest(change=change):
                    response=self.page(revision,**change)
                    self.assertEqual(response.status_code,400,response.get_json())
        body={'predicate':{'all':[]},'splits':'cell'}
        self.assertEqual(self.client.post('/api/explore/epochs',json=body,headers=self.headers).status_code,400)

    def _tag(self,tags):
        identity=self.service.ids[0];protocol=self.service.protocol_id
        state=self.fixture.store.read(protocol,[identity],{identity:self.service._fingerprints[identity]})
        response=self.client.post(self.fixture.base+'/curation',json={'epoch_uuids':[identity],
            'changes':{'tags_add':tags},'query_revision':self.fixture.revision(),
            'expected_revisions':{identity:state[identity]['revision']}},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())

    def test_binding_transport_compacts_evidence_without_mutating_canonical_recipe(self):
        self._tag(['keep']);field=f'curation/{self.service.protocol_id}/tags'
        self.predicate={'field':field,'operator':'contains','value':'keep'}
        saved=self.client.post('/api/explore/revisions',json={'predicate':self.predicate,'splits':'cell'},headers=self.headers).get_json()
        path='/api/explore/revisions/'+saved['revision_uuid']
        compare=self.client.post(path+'/compare-to-protocol',json={'protocol_uuid':self.service.protocol_id},headers=self.headers).get_json()
        applied=self.client.post(path+'/apply-to-protocol',json={key:compare[key] for key in
            ('protocol_uuid','expected_binding_version','expected_query_revision')},headers=self.headers)
        self.assertEqual(applied.status_code,200,applied.get_json())
        canonical=copy.deepcopy(self.service.query_result(self.service.protocol_id))
        full=canonical['dataset_binding']['annotation_scope']
        self.assertEqual(len(full['protocols'][0]['records']),1)
        overview=self.client.get('/api/overview').get_json()['protocols'][0]['binding']
        protocol=self.client.get(self.fixture.base).get_json()['binding']
        compare_again=self.client.post(path+'/compare-to-protocol',json={'protocol_uuid':self.service.protocol_id},headers=self.headers).get_json()['binding']
        for binding in (overview,protocol,compare_again,applied.get_json()['binding']):
            compact=binding['annotation_scope']
            self.assertEqual(compact['revision'],full['revision'])
            self.assertEqual(compact['protocols'][0]['revision'],full['protocols'][0]['revision'])
            self.assertEqual(compact['protocols'][0]['record_count'],1)
            self.assertNotIn('records',compact['protocols'][0])
        self.assertEqual(self.service.query_result(self.service.protocol_id),canonical)
        self.assertEqual(self.client.get(path).get_json()['recipe']['annotation_scope'],full)
        snapshot=capture_query(self.service.protocols[self.service.protocol_id]['definition'],canonical,'fixture')
        self.assertEqual(snapshot['dataset_binding']['annotation_scope'],full)

if __name__=='__main__':unittest.main()
