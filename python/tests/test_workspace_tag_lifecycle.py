"""Disposable end-to-end tag scopes, lifecycle, immutable history and selection."""
import copy
import json
import hashlib
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import test_workspace_api as api_fixture
from workspace_disk_index import DiskMetadataIndex
from workspace_tree_pages import TreePages, StaleTreePage
from workspace_tag_predicates import annotation_locks


class TagLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture=api_fixture.WorkspaceAPITests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service=self.fixture.service;self.client=self.fixture.client;self.headers=self.fixture.headers
        self.protocol=self.service.protocol_id;self.field=f'curation/{self.protocol}/tags'
        self.predicate={'field':self.field,'operator':'contains','value':'keep'}
        self.source='a'*64;self.source_url='/api/data-stores/'+self.source
        self.raw_path=Path(self.service.sources[0]['source_path']);self.raw_path.write_bytes(b'untouched disposable source')
        self.service.manifests[self.source]['source_size']=self.raw_path.stat().st_size
        self.initial_raw=self.raw_path.read_bytes()

    def tag(self,changes,ids=None,protocol=None):
        protocol=protocol or self.protocol;ids=ids or [self.service.ids[0]]
        base='/api/protocols/'+protocol
        revision=self.client.get(base).get_json()['query_revision']
        state=self.fixture.store.read(protocol,ids,{key:self.service._fingerprints[key] for key in ids})
        response=self.client.post(base+'/curation',json={'epoch_uuids':ids,'changes':changes,
            'expected_revisions':{key:value['revision'] for key,value in state.items()},'query_revision':revision},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json());return response.get_json()

    def preview(self,predicate=None):
        response=self.client.post('/api/explore/preview',json={'predicate':predicate or self.predicate,'splits':'cell'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json());return response.get_json()

    def save(self,predicate=None):
        response=self.client.post('/api/explore/revisions',json={'predicate':predicate or self.predicate,'splits':'cell','name':'Tagged fixture'},headers=self.headers)
        self.assertEqual(response.status_code,201,response.get_json());return response.get_json()

    def lifecycle(self,action,version):
        return self.client.post(self.source_url+'/state',json={'action':action,'expected_version':version,'reason':'Disposable lifecycle test'},headers=self.headers)

    def test_tag_add_remove_and_protocol_namespaces_are_not_unioned(self):
        other=str(uuid.uuid4());entry=copy.deepcopy(self.service.protocols[self.protocol])
        entry['definition'].update(protocol_uuid=other,name='Other protocol');entry['result']['protocol_uuid']=other
        self.service.protocols[other]=entry
        self.tag({'tags_add':['keep']})
        baseline=self.preview()
        self.tag({'tags_add':['keep']},ids=[self.service.ids[1]],protocol=other)
        self.assertEqual(self.preview()['annotation_scope'],baseline['annotation_scope'])
        metadata=self.preview({'all':[]})
        self.assertNotIn('annotation_scope',metadata)
        self.assertEqual([row['uuid'] for row in self.preview()['membership']],[self.service.ids[0]])
        other_predicate={**self.predicate,'field':f'curation/{other}/tags'}
        self.assertEqual([row['uuid'] for row in self.preview(other_predicate)['membership']],[self.service.ids[1]])
        combined=self.preview({'all':[self.predicate,other_predicate]})
        self.assertEqual(combined['matched_count'],0)
        catalog=self.client.get('/api/explore/predicate-fields').get_json()
        fields={field['id']:field for field in catalog['fields']}
        self.assertEqual(fields[self.field]['label'],'Tags · Fixture protocol')
        self.assertEqual(fields[self.field]['types'],['array'])
        self.tag({'tags_remove':['keep']})
        self.assertEqual(self.preview()['matched_count'],0)
        self.assertEqual(self.preview(other_predicate)['matched_count'],1)
        foreign={**self.predicate,'field':f'curation/{uuid.uuid4()}/tags'}
        self.assertEqual(self.client.post('/api/explore/preview',json={'predicate':foreign,'splits':'cell'},headers=self.headers).status_code,400)
        numeric={**self.predicate,'value':1}
        self.assertEqual(self.client.post('/api/explore/preview',json={'predicate':numeric,'splits':'cell'},headers=self.headers).status_code,400)

    def test_same_membership_annotation_change_stales_candidate_and_tree(self):
        self.tag({'tags_add':['keep']});saved=self.save();recipe=copy.deepcopy(saved['recipe'])
        initial=self.preview();pager=TreePages(self.service)
        page=pager.page({'predicate':self.predicate,'splits':'cell'})
        self.assertEqual(page['revision'],initial['tree_revision'])
        self.tag({'tags_add':['other-note']})
        changed=self.preview()
        self.assertEqual(initial['membership'],changed['membership'])
        self.assertNotEqual(initial['annotation_scope']['revision'],changed['annotation_scope']['revision'])
        self.assertNotEqual(initial['tree_revision'],changed['tree_revision'])
        with self.assertRaises(StaleTreePage): pager.page({'predicate':self.predicate,'splits':'cell','revision':page['revision']})
        path='/api/explore/revisions/'+saved['revision_uuid']
        comparison=self.client.post(path+'/compare-to-protocol',json={'protocol_uuid':self.protocol},headers=self.headers)
        self.assertEqual(comparison.status_code,409,comparison.get_json())
        self.assertEqual(self.client.get(path).get_json()['recipe'],recipe)

    def test_archive_freeze_exclude_restore_preserve_raw_and_frozen_membership(self):
        self.tag({'tags_add':['keep']});saved=self.save();recipe=copy.deepcopy(saved['recipe'])
        self.assertEqual(self.lifecycle('freeze',0).status_code,200)
        self.tag({'tags_add':['editable-while-frozen']})
        self.assertEqual(self.lifecycle('exclude',1).status_code,409)
        self.assertEqual(self.lifecycle('unfreeze',1).status_code,200)
        self.assertEqual(self.lifecycle('archive',2).status_code,200)
        self.assertEqual(self.preview()['matched_count'],1)  # Archive is visibility only.
        self.assertEqual(self.lifecycle('exclude',3).status_code,200)
        self.assertEqual(self.preview()['matched_count'],0)
        self.assertEqual(self.preview({'not':self.predicate})['matched_count'],0)
        self.assertEqual(self.client.get(self.fixture.base).get_json()['counts']['epochs'],2)
        self.assertEqual(self.lifecycle('restore',4).status_code,200)
        self.assertEqual(self.preview()['matched_count'],0)  # Restore does not include.
        self.assertEqual(self.lifecycle('include',5).status_code,200)
        self.assertEqual(self.preview()['matched_count'],1)
        self.assertEqual(self.client.get('/api/explore/revisions/'+saved['revision_uuid']).get_json()['recipe'],recipe)
        self.assertEqual(self.raw_path.read_bytes(),self.initial_raw)

    def test_tag_predicate_apply_then_export_freezes_exact_selected_epoch(self):
        self.tag({'tags_add':['keep']});saved=self.save();path='/api/explore/revisions/'+saved['revision_uuid']
        comparison=self.client.post(path+'/compare-to-protocol',json={'protocol_uuid':self.protocol},headers=self.headers).get_json()
        response=self.client.post(path+'/apply-to-protocol',json={key:comparison[key] for key in ('protocol_uuid','expected_binding_version','expected_query_revision')},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.client.get(self.fixture.base+'/epochs').get_json()['total'],1)
        exported=self.client.post(self.fixture.base+'/exports',json={'query_revision':self.fixture.revision()},headers=self.headers)
        self.assertEqual(exported.status_code,201,exported.get_json())
        artifact=self.fixture.store.get_dataset_revision(exported.get_json()['dataset_uuid'])
        package=json.loads(Path(artifact['artifact_path']).read_text())
        self.assertEqual([row['epoch_uuid'] for row in package['epochs']],[self.service.ids[0]])
        self.assertEqual(package['epochs'][0]['curation']['tags'],['keep'])
        self.assertEqual(package['recipe']['query_snapshot']['query']['predicate'],self.predicate)
        self.assertEqual(package['recipe']['dataset_binding']['annotation_scope'],saved['recipe']['annotation_scope'])
        artifact_bytes=Path(artifact['artifact_path']).read_bytes()
        self.tag({'tags_remove':['keep']})
        self.assertEqual(self.preview()['matched_count'],0)
        self.assertEqual(Path(artifact['artifact_path']).read_bytes(),artifact_bytes)
        self.assertEqual(self.raw_path.read_bytes(),self.initial_raw)

    def test_global_search_delegates_protocol_tags_and_inclusion_stays_local(self):
        from workspace_search import search_workspace
        self.tag({'tags_add':['keep'],'included':False})
        result=search_workspace(self.service,'',field=self.field,operator='contains',value='keep')
        self.assertEqual(result['results'][0]['count'],1)
        self.assertEqual(self.preview()['matched_count'],1)
        fields={field['id'] for field in self.client.get('/api/explore/predicate-fields').get_json()['fields']}
        self.assertNotIn('included',fields)
        self.assertNotIn(f'curation/{self.protocol}/included',fields)
        self.tag({'tags_remove':['keep']})
        self.assertEqual(search_workspace(self.service,'',field=self.field,operator='contains',value='keep')['results'][0]['count'],0)

    def test_annotation_locks_order_scope_and_release_after_failure(self):
        extra=str(uuid.uuid4());calls=[]
        class Result:
            def fetchone(self): return (1,)
        def query(sql): calls.append(sql);return Result()
        with patch.object(self.fixture.connection,'query',side_effect=query):
            with self.assertRaisesRegex(RuntimeError,'body failure'):
                with annotation_locks(self.service,self.predicate,extra_protocols=[extra,self.protocol]):
                    raise RuntimeError('body failure')
        hashes=[hashlib.sha256((self.service.project['project_uuid']+key).encode()).hexdigest() for key in sorted({extra,self.protocol})]
        self.assertEqual(calls,[f"SELECT GET_LOCK('{key}', 10)" for key in hashes]+[f"SELECT RELEASE_LOCK('{key}')" for key in reversed(hashes)])
        calls.clear()
        class Failed:
            def fetchone(self): return (0,)
        def fail_second(sql):
            calls.append(sql)
            return Failed() if len(calls)==2 else Result()
        with patch.object(self.fixture.connection,'query',side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError,'annotation update'):
                with annotation_locks(self.service,self.predicate,extra_protocols=[extra]): pass
        self.assertEqual(calls[-1],f"SELECT RELEASE_LOCK('{hashes[0]}')")
        with patch.object(self.service.dj,'conn',side_effect=AssertionError('No lock for metadata-only preview')):
            with annotation_locks(self.service,{'all':[]}): pass

    def test_disk_predicate_path_matches_fallback_without_caching_mutable_tags(self):
        self.tag({'tags_add':['keep']})
        predicate={'all':[self.predicate,{'field':'parameters/example','operator':'eq','value':0}]}
        before=self.preview(predicate)
        self.service.disk_index=DiskMetadataIndex.build(Path(self.fixture.temp.name)/'derived.sqlite',
            self.service.rows,self.service.details,self.service.sources,'test-generation',self.service.project['project_uuid'])
        self.service._registered_tree_cache=None
        after=self.preview(predicate)
        self.assertEqual(after['membership'],before['membership'])
        self.assertEqual(after['annotation_scope'],before['annotation_scope'])
        self.assertEqual(after['tree_revision'],before['tree_revision'])
        self.assertNotIn(self.field,{field['id'] for field in self.service.disk_index.catalog()['fields']})
        self.tag({'tags_remove':['keep']})
        self.assertEqual(self.preview(predicate)['matched_count'],0)

if __name__=='__main__':unittest.main()
