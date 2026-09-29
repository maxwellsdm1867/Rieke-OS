"""Compact explorer responses never replace the exact immutable stored recipe."""
import copy
import unittest
import uuid
from unittest.mock import patch

import test_workspace_api as api_fixture
from workspace_recipes import checksum


class CompactExplorerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client = self.fixture.client
        self.service = self.fixture.service
        self.headers = self.fixture.headers

    def save(self,predicate=None,**options):
        response=self.client.post('/api/explore/revisions',json={
            'predicate':predicate or {'all':[]},'splits':'cell','summary_only':True,**options},headers=self.headers)
        self.assertEqual(response.status_code,201,response.get_json())
        return response.get_json()

    def test_compact_save_keeps_exact_canonical_membership_and_full_get(self):
        raw_before=copy.deepcopy((self.service.rows,self.service.details))
        with patch.object(self.service,'_render_tree',side_effect=AssertionError('Compact save must not build a full tree')):
            created=self.save(name='Compact fixture')
        recipe=created['recipe']
        self.assertTrue(recipe['summary_only'])
        self.assertEqual(recipe['epoch_count'],2)
        for key in ('epochs','diff','content_sha256'):self.assertNotIn(key,recipe)
        self.assertNotIn('membership',created['preview'])
        self.assertNotIn('children',created['preview']['tree'])
        self.assertEqual(created['preview']['baseline_diff'],{'added':0,'removed':0,'changed':0})
        self.assertIn('matlab_command',created['preview']['tree'])
        path='/api/explore/revisions/'+created['revision_uuid']
        full=self.client.get(path).get_json()
        canonical=full['recipe']
        self.assertEqual({row['uuid'] for row in canonical['epochs']},set(self.service.ids))
        self.assertEqual(set(canonical['diff']['added']),set(self.service.ids))
        self.assertEqual(canonical['content_sha256'],recipe['full_recipe_sha256'])
        self.assertEqual(checksum({k:v for k,v in canonical.items() if k!='content_sha256'}),canonical['content_sha256'])
        compact=self.client.get(path+'?summary=1').get_json()
        self.assertEqual(compact['recipe'],recipe)
        self.assertEqual(self.client.get(path).get_json(),full)
        self.assertEqual((self.service.rows,self.service.details),raw_before)
        self.assertEqual(len(self.fixture.explorer_revisions.rows),1)
        self.assertEqual(len(self.fixture.events.rows),1)

    def test_summary_preview_diff_and_focus_are_computed_against_frozen_members(self):
        first,second=self.service.ids
        baseline=self.save({'field':'parameters/example','operator':'eq','value':0})
        self.service._fingerprints[first]='c'*64
        body={'predicate':{'all':[]},'splits':'cell','summary_only':True,
              'baseline_revision_uuid':baseline['revision_uuid'],'focused_uuid':second}
        with patch.object(self.service,'_render_tree',side_effect=AssertionError('No full tree for summary')):
            response=self.client.post('/api/explore/preview',json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        payload=response.get_json()
        self.assertEqual(payload['baseline_diff'],{'added':1,'removed':0,'changed':1})
        self.assertTrue(payload['focused_in_scope'])
        self.assertEqual(payload['focused_uuid'],second)
        self.assertNotIn('membership',payload)
        body.update(predicate={'field':'parameters/example','operator':'eq','value':1},focused_uuid=first)
        changed=self.client.post('/api/explore/preview',json=body,headers=self.headers).get_json()
        self.assertEqual(changed['baseline_diff'],{'added':1,'removed':1,'changed':0})
        self.assertFalse(changed['focused_in_scope'])
        self.assertEqual(len(self.fixture.explorer_revisions.rows),1)  # Preview never writes.
        self.assertEqual(len(self.fixture.events.rows),1)

    def test_compact_child_recipe_retains_parent_exact_diff_and_legacy_preview(self):
        baseline=self.save({'field':'parameters/example','operator':'eq','value':0})
        child=self.save({'field':'parameters/example','operator':'eq','value':1},parent_revision_uuid=baseline['revision_uuid'])
        full=self.client.get('/api/explore/revisions/'+child['revision_uuid']).get_json()['recipe']
        self.assertEqual(full['diff'],{'added':[self.service.ids[1]],'removed':[self.service.ids[0]],'changed':[]})
        legacy=self.client.post('/api/explore/preview',json={'predicate':{'all':[]},'splits':'cell'},headers=self.headers).get_json()
        self.assertEqual({row['uuid'] for row in legacy['membership']},set(self.service.ids))
        self.assertIn('children',legacy['tree'])

    def test_summary_flags_and_foreign_baseline_fail_closed(self):
        for endpoint in ('preview','revisions'):
            response=self.client.post('/api/explore/'+endpoint,json={'predicate':{'all':[]},'splits':'cell','summary_only':'true'},headers=self.headers)
            self.assertEqual(response.status_code,400)
        saved=self.save()
        path='/api/explore/revisions/'+saved['revision_uuid']
        self.assertEqual(self.client.get(path+'?summary=0').status_code,400)
        self.assertEqual(self.client.get(path+'?summary=1&other=1').status_code,400)
        foreign=copy.deepcopy(self.fixture.explorer_revisions.rows[0])
        foreign['revision_uuid']=str(uuid.uuid4());foreign['project_uuid']=str(uuid.uuid4())
        self.fixture.explorer_revisions.insert1(foreign)
        response=self.client.post('/api/explore/preview',json={'predicate':{'all':[]},'splits':'cell',
            'summary_only':True,'baseline_revision_uuid':foreign['revision_uuid']},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/explore/revisions/'+foreign['revision_uuid']+'?summary=1').status_code,400)

    def test_compact_preview_revision_gates_paged_tree_snapshot(self):
        body={'predicate':{'field':'parameters/example','operator':'eq','value':0},'splits':'cell'}
        response=self.client.post('/api/explore/preview',json={**body,'summary_only':True},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        revision=response.get_json()['tree_revision']
        page=self.client.post('/api/tree-pages',json={**body,'revision':revision},headers=self.headers)
        self.assertEqual(page.status_code,200,page.get_json())
        self.assertEqual(page.get_json()['revision'],revision)
        self.assertEqual(page.get_json()['total_epochs'],1)
        self.service._fingerprints[self.service.ids[0]]='c'*64
        stale=self.client.post('/api/tree-pages',json={**body,'revision':revision},headers=self.headers)
        self.assertEqual(stale.status_code,409)
        self.assertEqual(stale.get_json()['code'],'stale_tree_revision')

    def test_optional_preview_identities_reject_malformed_json_types(self):
        for field in ('focused_uuid','baseline_revision_uuid'):
            for value in ({},[],None,1,True,'bad'):
                with self.subTest(field=field,value=value):
                    response=self.client.post('/api/explore/preview',json={'predicate':{'all':[]},
                        'splits':'cell','summary_only':True,field:value},headers=self.headers)
                    self.assertEqual(response.status_code,400)
        self.assertEqual(len(self.fixture.explorer_revisions.rows),0)
        self.assertEqual(len(self.fixture.events.rows),0)

    def test_epoch_anchor_locates_containing_page_in_exact_filtered_scope(self):
        first,second=self.service.ids
        response=self.client.get(self.fixture.base+'/epochs',query_string={'anchor_uuid':second,'limit':1})
        self.assertEqual(response.status_code,200,response.get_json())
        page=response.get_json()
        self.assertEqual((page['offset'],page['anchor_index'],page['total']),(1,1,2))
        self.assertEqual([row['epoch_uuid'] for row in page['epochs']],[second])
        filtered=self.client.get(self.fixture.base+'/epochs',query_string={
            'anchor_uuid':second,'cell_uuid':self.service.cell_ids[1],'limit':1}).get_json()
        self.assertEqual((filtered['offset'],filtered['anchor_index'],filtered['total']),(0,0,1))
        for identity in (first,str(uuid.uuid4()),'malformed'):
            response=self.client.get(self.fixture.base+'/epochs',query_string={
                'anchor_uuid':identity,'cell_uuid':self.service.cell_ids[1],'limit':1})
            self.assertEqual(response.status_code,400,response.get_json())

if __name__=='__main__':unittest.main()
