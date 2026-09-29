"""Identity, authorship, inheritance and frozen shared-tag contracts without research writes."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import test_workspace_api as fixture
from test_workspace_curation import Table
from workspace_annotations import SharedAnnotations
from workspace_api import create_app
from workspace_curation import RevisionConflict
from workspace_tag_predicates import TagPredicates


class SharedAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.WorkspaceAPITests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.service=self.case.service
        self.profiles=Table(('project_uuid','profile_uuid'))
        self.records=Table(('project_uuid','target_kind','target_uuid','profile_uuid'))
        self.case.connection.tables.extend([self.profiles,self.records])
        self.store=SharedAnnotations(self.service,(self.profiles,self.records,self.case.events))
        self.app=create_app(self.case.temp.name,self.case.temp.name,service=self.service,store=self.case.store,
            explorer_history=self.case.explorer_history,data_stores=self.case.data_stores,
            protocol_suggestions=self.case.protocol_suggestions,shared_annotations=self.store)
        self.client=self.app.test_client();self.headers=self.case.headers
        self.author=self.store.default_profile['profile_uuid']
        self.first,self.second=self.service.ids
        self.cell,self.other_cell=self.service.cell_ids
        self.raw=copy.deepcopy((self.service.rows,self.service.details))

    def edit(self,kind,target,add=(),remove=(),revision=0,author=None):
        return self.store.update(kind,[target],author or self.author,
            {'tags_add':list(add),'tags_remove':list(remove)}, {target:revision}, 'OS test actor')

    def epoch(self,key):
        return self.store.for_epochs([self.service.rows[key]])[key]

    def test_same_labels_never_cross_dates_or_uuid_kinds_and_unknown_batch_rolls_back(self):
        self.service.rows[self.second]['cell_label']=self.service.rows[self.first]['cell_label']
        self.edit('cell',self.cell,['ON'])
        self.assertEqual([r['tag'] for r in self.epoch(self.first)['cell_tags']],['ON'])
        self.assertEqual(self.epoch(self.second)['effective_tags'],[])
        for kind,target in [('epoch',self.cell),('cell',self.first),('cell',str(uuid.uuid4()))]:
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.edit(kind,target,['bad'])
        before=copy.deepcopy((self.records.rows,self.case.events.rows))
        with self.assertRaises(ValueError):self.store.update('epoch',[self.first,str(uuid.uuid4())],self.author,
            {'tags_add':['bad']},{self.first:0},'actor')
        self.assertEqual((self.records.rows,self.case.events.rows),before)

    def test_inheritance_new_epoch_shared_cell_all_protocols_not_copied_rows(self):
        self.edit('cell',self.cell,['good cell'])
        later=str(uuid.uuid4());row=copy.deepcopy(self.service.rows[self.first]);row['epoch_uuid']=later
        row['protocol_name']='another.Protocol';self.service.rows[later]=row
        self.assertEqual([r['tag'] for r in self.epoch(later)['cell_tags']],['good cell'])
        self.assertEqual(len(self.records.rows),1)
        self.assertEqual(self.epoch(later)['epoch_tags'],[])
        self.assertTrue(all(r['target_kind']=='cell' for r in self.records.rows))

    def test_two_authors_same_text_and_direct_tag_survive_cell_author_removal(self):
        other=self.store.create_profile('Second scientist','local')['profile_uuid']
        self.edit('cell',self.cell,['same'])
        self.edit('cell',self.cell,['same'],author=other)
        self.edit('epoch',self.first,['same'])
        self.assertEqual(len(self.epoch(self.first)['effective_tags']),3)
        self.edit('cell',self.cell,remove=['same'],revision=1)
        current=self.epoch(self.first)
        self.assertEqual(len(current['effective_tags']),2)
        self.assertEqual(current['cell_tags'][0]['profile_uuid'],other)
        self.assertEqual(current['epoch_tags'][0]['profile_uuid'],self.author)
        self.assertEqual((self.service.rows,self.service.details),self.raw)
        self.assertFalse(self.case.curation.rows)

    def test_noop_is_idempotent_stale_revision_fails_and_state_failure_rolls_back(self):
        first=self.edit('epoch',self.first,['A']);self.assertEqual(first['changed'],1)
        before=copy.deepcopy((self.records.rows,self.case.events.rows))
        no_op=self.edit('epoch',self.first,['A'],revision=1)
        self.assertEqual(no_op['changed'],0);self.assertIsNone(no_op['event_uuid'])
        self.assertEqual((self.records.rows,self.case.events.rows),before)
        with self.assertRaises(RevisionConflict):self.edit('epoch',self.first,['B'],revision=0)
        with patch.object(self.records,'update1',side_effect=RuntimeError('State write failed')):
            with self.assertRaises(RuntimeError):self.edit('epoch',self.first,['B'],revision=1)
        self.assertEqual((self.records.rows,self.case.events.rows),before)
        self.assertTrue(any('GET_LOCK' in q for q in self.case.connection.queries))
        self.assertTrue(any('RELEASE_LOCK' in q for q in self.case.connection.queries))

    def test_batch_conflict_rolls_back_all_targets_and_profile_creation(self):
        self.edit('epoch',self.second,['existing'])
        new_author=str(uuid.uuid4());before=copy.deepcopy((self.records.rows,self.profiles.rows,self.case.events.rows))
        with self.assertRaises(RevisionConflict):
            self.store.apply_batch([
                dict(target_kind='epoch',target_uuid=self.first,profile_uuid=new_author,tags_add=['first'],expected_revision=0),
                dict(target_kind='epoch',target_uuid=self.second,profile_uuid=self.author,tags_add=['second'],expected_revision=0)],
                'local',profiles=[{'profile_uuid':new_author,'display_name':'Incoming author'}])
        self.assertEqual((self.records.rows,self.profiles.rows,self.case.events.rows),before)

    def test_project_scope_case_exactness_and_cached_bounded_vocabulary(self):
        self.edit('epoch',self.first,['ON','on'])
        foreign=copy.deepcopy(self.records.rows[0]);foreign['project_uuid']=str(uuid.uuid4());foreign['tags']=['Secret'];self.records.insert1(foreign)
        with patch('workspace_annotations.time.monotonic',return_value=1):
            result=self.store.suggestions('oN',1);reads=len(self.records.read_log)
            self.assertEqual(result['tags'][0]['tag'],'ON');self.assertEqual(result['total'],2)
            self.assertEqual(self.store.suggestions('s')['tags'],[]);self.assertEqual(len(self.records.read_log),reads)
        self.assertEqual(len(self.store.snapshot()['records']),1)
        self.edit('epoch',self.first,['New'],revision=1)
        self.assertEqual(self.store.suggestions('new')['tags'][0]['tag'],'New')

    def test_cell_direct_effective_and_author_predicates_are_distinct_and_exact(self):
        self.edit('cell',self.cell,['cellA']);self.edit('epoch',self.second,['directB'])
        def matches(field,value):
            return TagPredicates(self.service).match({'field':field,'operator':'contains','value':value},self.service.ids)[1]
        self.assertEqual(matches('annotations/cell/tags','cellA'),[self.first])
        self.assertEqual(matches('annotations/epoch/tags','cellA'),[])
        self.assertEqual(matches('annotations/effective/tags','cellA'),[self.first])
        self.assertEqual(matches('annotations/effective/tags','directB'),[self.second])
        self.assertEqual(set(matches('annotations/authors',self.store.default_profile['display_name'])),set(self.service.ids))
        predicate={'not':{'field':'annotations/epoch/tags','operator':'contains','value':'directB'}}
        self.assertEqual(TagPredicates(self.service).match(predicate,self.service.ids)[1],[self.first])
        with self.assertRaises(ValueError):TagPredicates(self.service).match({'field':'annotations/cell/tags','operator':'contains','value':True},self.service.ids)

    def test_paged_rows_detail_summary_and_predicate_browsing_batch_annotations(self):
        self.edit('cell',self.cell,['useful'])
        base='/api/protocols/'+self.service.protocol_id
        detail=self.client.get('/api/epochs/'+self.first).get_json()
        self.assertEqual(detail['annotations']['cell_tags'][0]['tag'],'useful')
        page=self.client.get(base+'/epochs').get_json()
        self.assertTrue(page['epochs'][0]['annotations']['cell_tags'])
        protocol=self.client.get(base).get_json()
        self.assertEqual(protocol['counts']['shared_tagged_cells'],1)
        self.assertEqual(protocol['annotation_summary']['tags'],[{'tag':'useful','cell_count':1,'epoch_count':1}])
        predicate={'all':[]};options={'predicate':predicate,'splits':''}
        preview=self.client.post('/api/explore/preview',json=options,headers=self.headers).get_json()
        response=self.client.post('/api/explore/epochs',json={**options,'revision':preview['tree_revision']},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertTrue(response.get_json()['epochs'][0]['annotations']['cell_tags'])
        tree=self.client.post('/api/tree-pages',json=options,headers=self.headers)
        self.assertEqual(tree.status_code,200,tree.get_json())
        self.assertTrue(tree.get_json()['epochs'][0]['annotations']['cell_tags'])

    def test_metadata_predicate_stable_tag_predicate_stale_even_same_membership(self):
        self.edit('cell',self.cell,['keep'])
        def preview(predicate):return self.service.explore_preview(predicate,'cell',include_tree=False)
        meta=preview({'all':[]});predicate={'field':'annotations/effective/tags','operator':'contains','value':'keep'}
        first=preview(predicate)
        self.edit('cell',self.cell,['extra'],revision=1)
        second=preview(predicate)
        self.assertEqual(first['membership'],second['membership'])
        self.assertNotEqual(first['annotation_scope']['revision'],second['annotation_scope']['revision'])
        self.assertNotEqual(first['tree_revision'],second['tree_revision'])
        self.assertEqual(meta['tree_revision'],preview({'all':[]})['tree_revision'])

    def test_http_bounds_csrf_and_optimistic_revision(self):
        body={'target_kind':'epoch','target_uuids':[self.first],'profile_uuid':self.author,
              'tags_add':['saved'],'expected_revisions':{self.first:0}}
        self.assertEqual(self.client.post('/api/annotations',json=body).status_code,403)
        response=self.client.post('/api/annotations',json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.client.post('/api/annotations',json=body,headers=self.headers).status_code,409)
        for invalid in (None,[],{'target_kind':'banana'},{**body,'target_uuids':[self.cell]}):
            with self.subTest(invalid=invalid):self.assertEqual(self.client.post('/api/annotations',json=invalid,headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/api/annotation-tags?limit=101').status_code,400)
        read=self.client.post('/api/annotations/read',json={'target_kind':'epoch','target_uuids':[self.first]},headers=self.headers).get_json()
        self.assertIn('annotations',read);self.assertEqual(read['targets'][self.first]['revisions'][self.author],1)

    def test_http_save_refreshes_suggestions_and_persists_current_state(self):
        self.service.Event=self.case.events
        self.assertEqual(self.client.get('/api/annotation-tags?q=check').get_json()['tags'], [])
        body={'target_kind':'epoch','target_uuids':[self.first],'profile_uuid':self.author,
              'tags_add':['Check response'],'expected_revisions':{self.first:0}}
        response=self.client.post('/api/annotations',json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        receipt=response.get_json()
        self.assertEqual(receipt['changed'],1)
        suggestions=self.client.get('/api/annotation-tags?q=cHeCk&limit=12').get_json()
        self.assertEqual(suggestions['tags'][0]['tag'],'Check response')
        read=self.client.get(f'/api/epochs/{self.first}/annotations').get_json()
        self.assertIn('Check response',str(read))
        events=self.client.get('/api/events?action=shared_annotations_updated&limit=50').get_json()['events']
        self.assertIsNone(receipt['event_uuid'])
        self.assertEqual(events,[])
        self.assertEqual(self.records.rows[0]['tags'],['Check response'])

    def test_bulk_tag_save_targets_selected_epochs_across_cells_only(self):
        ids=[self.first,self.second]
        read=self.client.post('/api/annotations/read',json={'target_kind':'epoch','target_uuids':ids},headers=self.headers).get_json()
        revisions={key:read['targets'][key]['revisions'].get(self.author,0) for key in ids}
        response=self.client.post('/api/annotations',json={'target_kind':'epoch','target_uuids':ids,
            'profile_uuid':self.author,'tags_add':['Batch review'],'expected_revisions':revisions},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['changed'],2)
        for key in ids:
            self.assertEqual([tag['tag'] for tag in self.epoch(key)['epoch_tags']],['Batch review'])
            self.assertEqual(self.epoch(key)['cell_tags'],[])
        self.assertEqual({row['target_uuid'] for row in self.records.rows},set(ids))
        self.assertEqual(self.case.events.rows,[])

    def test_unchanged_blank_operation_writes_no_profile_or_event(self):
        result=self.edit('epoch',self.first)
        self.assertEqual(result['changed'],0)
        self.assertFalse(self.profiles.rows);self.assertFalse(self.records.rows);self.assertFalse(self.case.events.rows)

    def test_forged_cell_link_and_oversized_tag_sets_fail_closed(self):
        forged={**self.service.rows[self.first],'cell_uuid':self.other_cell}
        with self.assertRaisesRegex(ValueError,'linkage'):self.store.for_epochs([forged])
        with self.assertRaises(ValueError):self.edit('epoch',self.first,[str(i) for i in range(101)])
        self.assertFalse(self.records.rows)
        for raw in ('limit=true','limit=1.5','limit=-1','limit=1&limit=2','limit=%D9%A1'):
            with self.subTest(raw=raw):self.assertEqual(self.client.get('/api/annotation-tags?'+raw).status_code,400)

    def test_protocol_export_freezes_annotations_and_stale_tags_reject_old_revision(self):
        base='/api/protocols/'+self.service.protocol_id
        previous=self.client.get(base).get_json()['query_revision']
        self.edit('cell',self.cell,['snapshot cell'])
        refused=self.client.post(base+'/exports',json={'query_revision':previous},headers=self.headers)
        self.assertEqual(refused.status_code,409)
        revision=self.client.get(base).get_json()['query_revision']
        exported=self.client.post(base+'/exports',json={'query_revision':revision},headers=self.headers)
        self.assertEqual(exported.status_code,201,exported.get_json())
        response=self.client.get(exported.get_json()['download_url']);raw=response.data;response.close()
        package=json.loads(raw)
        first=next(row for row in package['epochs'] if row['epoch_uuid']==self.first)
        self.assertEqual(first['annotations']['cell_tags'][0]['profile_uuid'],self.author)
        self.assertEqual(package['recipe']['query_snapshot']['shared_annotations_revision'],self.store.snapshot()['revision'])
        self.edit('cell',self.cell,remove=['snapshot cell'],revision=1)
        response=self.client.get(exported.get_json()['download_url']);self.assertEqual(response.data,raw);response.close()


if __name__=='__main__':unittest.main()
