"""Detached query exports publish exact artifacts without protocol creation."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from threading import RLock
import unittest
from unittest.mock import patch
import uuid
import zipfile

import h5py
from scipy.io import loadmat

import test_workspace_api as api_fixture
from workspace_candidate_exports import register_candidate_export_routes,candidate_scope_uuid
from workspace_matlab_masks import read_ugm
from workspace_recipes import checksum
from test_workspace_matlab import epochs as matlab_epochs


class CandidateExportTests(unittest.TestCase):
    def setUp(self):
        self.case=api_fixture.WorkspaceAPITests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.service,self.client,self.store=self.case.service,self.case.client,self.case.store
        self.project=self.service.project['project_uuid']
        source_path=Path(self.case.temp.name)/'fixture.h5'
        with h5py.File(source_path,'w') as file:file.create_dataset('fixture',data=[1.,2.])
        sha=hashlib.sha256(source_path.read_bytes()).hexdigest()
        source=self.service.sources[0]
        source.update(source_sha256=sha,experiment_uuid=str(uuid.uuid4()),metadata={'label':'Fixture'})
        self.service.manifests={sha:{'source_path':str(source_path),'source_sha256':sha,'source_size':source_path.stat().st_size}}
        self.service._source_signatures={}
        self.case.sources.rows[0]['source_sha256']=sha
        for key,row in self.service.rows.items():
            row['source_sha256']=sha
            self.service.details[key]['metadata'].update(cell={'uuid':row['cell_uuid'],'start_time':row['start_time']},
                group={'uuid':row['group_uuid']},block={'uuid':row['block_uuid']},
                epoch={'uuid':key,'responses':{},'stimuli':{}})
            self.service._fingerprints[key]=hashlib.sha256(json.dumps({'epoch':self.service.details[key],
                'source_sha256':sha},sort_keys=True,allow_nan=False).encode()).hexdigest()
        self.service.protocols[self.service.protocol_id]['result']['source_revisions']=[sha]
        if 'candidate_export' not in self.case.app.view_functions:
            register_candidate_export_routes(self.case.app,self.service,self.store,self.case.explorer_history,RLock(),self.case.data_stores.registration_locks)
        self.headers=self.case.headers

    def save(self,predicate=None,splits='cell,parameters/example'):
        response=self.client.post('/api/explore/revisions',json={'predicate':predicate or {'all':[]},
            'splits':splits,'summary_only':True},headers=self.headers)
        self.assertEqual(response.status_code,201,response.get_json())
        return response.get_json()

    def export(self,candidate,format='reference-json',**options):
        return self.client.post('/api/explore/revisions/'+candidate['revision_uuid']+'/exports',json={
            'format':format,'expected_recipe_sha256':candidate['recipe']['full_recipe_sha256'],**options},headers=self.headers)

    def test_sqlite_exact_candidate_ignores_unrelated_protocol_masks_and_keeps_history(self):
        key=self.service.ids[0]
        self.store.update(self.service.protocol_id,[key],{'included':False,'tags_add':['protocol-only']},
            {key:0},{key:self.service._fingerprints[key]},'fixture')
        candidate=self.save({'field':'parameters/example','operator':'eq','value':0})
        before=copy.deepcopy((self.service.rows,self.service.details,self.service.protocols,self.case.curation.rows,self.case.protocol_bindings.rows))
        response=self.export(candidate,'wheeler-sqlite',name='Named one-off')
        self.assertEqual(response.status_code,201,response.get_json())
        result=response.get_json()
        self.assertEqual(result['export_scope']['kind'],'explorer_candidate')
        self.assertEqual(result['name'],'Named one-off')
        self.assertEqual(result['epoch_count'],1)
        self.assertEqual((self.service.rows,self.service.details,self.service.protocols,self.case.curation.rows,self.case.protocol_bindings.rows),before)
        record=self.store.get_dataset_revision(result['dataset_uuid'])
        self.assertNotIn(record['protocol_uuid'],self.service.protocols)
        self.assertEqual(record['protocol_uuid'],candidate_scope_uuid(self.project,candidate['revision_uuid']))
        with sqlite3.connect('file:'+record['artifact_path']+'?mode=ro',uri=True) as db:
            self.assertEqual(db.execute('SELECT epoch_uuid,included,review_state FROM epochs').fetchall(),[(key,1,'unreviewed')])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM epoch_tags').fetchone()[0],0)
            recipe=json.loads(db.execute('SELECT recipe_json FROM export_metadata').fetchone()[0])
            self.assertEqual(recipe['query']['predicate'],candidate['recipe']['predicate'])
            self.assertEqual(recipe['options']['split_order'],candidate['recipe']['splits'])
            self.assertEqual(recipe['query_snapshot']['export_scope'],result['export_scope'])
        downloaded=self.client.get(result['download_url'])
        self.assertEqual(downloaded.status_code,200)
        self.assertEqual(hashlib.sha256(downloaded.data).hexdigest(),record['artifact_sha256'])
        downloaded.close()
        history=self.store.list_dataset_revisions()
        self.assertEqual(history[0]['export_scope']['revision_uuid'],candidate['revision_uuid'])
        self.assertEqual(self.store.epoch_exports(key)[0]['export_scope']['kind'],'explorer_candidate')
        self.assertTrue(any(row['action']=='dataset_revision_exported' for row in self.case.events.rows))

    def test_history_reuse_returns_candidate_review_intent_without_protocol_lookup_or_export(self):
        candidate=self.save()
        created=self.export(candidate,'wheeler-sqlite',name='Repeat this selection').get_json()
        before=copy.deepcopy((self.case.datasets.rows,self.case.curation.rows,self.case.events.rows,self.case.protocol_bindings.rows))
        with patch.object(self.service,'protocol',side_effect=AssertionError('No phantom protocol lookup')), \
             patch.object(self.service,'query_result',side_effect=AssertionError('No protocol query')):
            response=self.client.get('/api/exports/'+created['dataset_uuid']+'/reuse')
        self.assertEqual(response.status_code,200,response.get_json())
        result=response.get_json()
        self.assertEqual(result['kind'],'explorer_candidate')
        self.assertEqual(result['candidate_revision_uuid'],candidate['revision_uuid'])
        self.assertEqual(result['export_intent'],{'name':'Repeat this selection','format':'wheeler-sqlite'})
        self.assertNotIn('protocol_uuid',result)
        self.assertTrue(result['review_required'])
        self.assertEqual((self.case.datasets.rows,self.case.curation.rows,self.case.events.rows,self.case.protocol_bindings.rows),before)
        history=self.client.get('/api/exports').get_json()['exports']
        self.assertEqual(history[0]['export_scope']['kind'],'explorer_candidate')

    def test_matlab_bundle_roundtrip_mask_and_generated_script(self):
        candidate=self.save()
        response=self.export(candidate,'epictree-mat')
        self.assertEqual(response.status_code,201,response.get_json())
        result=response.get_json()
        self.assertTrue(result['name'])
        download=self.client.get(result['download_url'])
        bundle=zipfile.ZipFile(io.BytesIO(download.data));download.close()
        self.addCleanup(bundle.close)
        data=loadmat(io.BytesIO(bundle.read('recordings.mat')),simplify_cells=True)
        self.assertEqual({epoch['h5_uuid'] for epoch in matlab_epochs(data)},set(self.service.ids))
        self.assertIn('launchWorkspaceTree',bundle.read('tree_layout.m').decode())
        mask=Path(self.case.temp.name)/'roundtrip.ugm';mask.write_bytes(bundle.read('selection.ugm'))
        loaded=read_ugm(mask,expected_epoch_uuids=self.service.ids)
        self.assertTrue(all(loaded['mask']))
        recipe=json.loads(bundle.read('recipe.json'))
        self.assertEqual(recipe['options']['export_scope']['revision_uuid'],candidate['revision_uuid'])
        self.assertEqual(self.case.curation.rows,[])
        self.assertEqual(self.case.protocol_bindings.rows,[])

    def test_stale_metadata_and_candidate_receipt_reject_before_publication(self):
        candidate=self.save()
        self.service._fingerprints[self.service.ids[0]]='c'*64
        response=self.export(candidate)
        self.assertEqual(response.status_code,409,response.get_json())
        self.assertEqual(response.get_json()['code'],'stale_candidate_export')
        self.assertEqual(self.case.datasets.rows,[])
        self.assertEqual(list((self.service.project_dir/'exports').iterdir()),[])
        wrong=self.export(candidate,expected_recipe_sha256='0'*64)
        self.assertEqual(wrong.status_code,409)

    def test_writer_failure_creates_no_success_dataset_or_curation(self):
        candidate=self.save()
        before=copy.deepcopy(self.case.events.rows)
        with patch('workspace_sqlite.build_sqlite_export',side_effect=ValueError('fixture writer failure')):
            response=self.export(candidate,'wheeler-sqlite')
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.case.datasets.rows,[])
        self.assertEqual(self.case.curation.rows,[])
        self.assertEqual(self.case.events.rows,before)
        failures=list((self.service.project_dir/'exports').glob('*/failure.json'))
        self.assertEqual(len(failures),1)
        self.assertFalse(json.loads(failures[0].read_text())['artifact_published'])

    def test_scoped_tag_evidence_is_frozen_without_implicit_tag_curation(self):
        key=self.service.ids[0]
        self.store.update(self.service.protocol_id,[key],{'tags_add':['keep']},
            {key:0},{key:self.service._fingerprints[key]},'fixture')
        candidate=self.save({'field':f'curation/{self.service.protocol_id}/tags','operator':'contains','value':'keep'})
        full=self.case.explorer_history.get(candidate['revision_uuid'])['recipe']
        response=self.export(candidate)
        self.assertEqual(response.status_code,201,response.get_json())
        result=response.get_json()
        record=self.store.get_dataset_revision(result['dataset_uuid'])
        package=json.loads(Path(record['artifact_path']).read_text())
        self.assertEqual(package['recipe']['query_snapshot']['annotation_scope'],full['annotation_scope'])
        self.assertEqual([row['epoch_uuid'] for row in package['epochs']],[key])
        self.assertEqual(package['epochs'][0]['curation']['tags'],[])
        self.assertEqual(len(self.case.curation.rows),1)
        exported=next(row for row in self.case.events.rows if row['action']=='dataset_revision_exported')
        self.assertEqual(exported['payload']['export_scope']['kind'],'explorer_candidate')
        # Same selected membership, changed annotation evidence: must still fail.
        self.store.update(self.service.protocol_id,[key],{'tags_add':['another']},
            {key:1},{key:self.service._fingerprints[key]},'fixture')
        self.assertEqual(self.export(candidate).status_code,409)
        self.assertEqual(len(self.case.datasets.rows),1)

    def test_tag_change_during_writer_is_rechecked_under_publication_locks(self):
        import workspace_sqlite
        key=self.service.ids[0]
        self.store.update(self.service.protocol_id,[key],{'tags_add':['keep']},
            {key:0},{key:self.service._fingerprints[key]},'fixture')
        candidate=self.save({'field':f'curation/{self.service.protocol_id}/tags','operator':'contains','value':'keep'})
        writer=workspace_sqlite.build_sqlite_export
        def change_after_writing(package,path):
            result=writer(package,path)
            self.store.update(self.service.protocol_id,[key],{'tags_add':['changed']},
                {key:1},{key:self.service._fingerprints[key]},'other-fixture-client')
            return result
        with patch.object(workspace_sqlite,'build_sqlite_export',side_effect=change_after_writing):
            response=self.export(candidate,'wheeler-sqlite')
        self.assertEqual(response.status_code,409,response.get_json())
        self.assertEqual(self.case.datasets.rows,[])
        self.assertFalse(any(row['action']=='dataset_revision_exported' for row in self.case.events.rows))
        lock=hashlib.sha256((self.project+self.service.protocol_id).encode()).hexdigest()
        self.assertEqual(self.case.connection.queries.count(f"SELECT GET_LOCK('{lock}', 10)"),
                         self.case.connection.queries.count(f"SELECT RELEASE_LOCK('{lock}')"))

    def test_source_changed_during_writer_is_not_published(self):
        import workspace_sqlite
        candidate=self.save()
        writer=workspace_sqlite.build_sqlite_export
        def alter_source(package,path):
            result=writer(package,path)
            with Path(self.service.sources[0]['source_path']).open('ab') as stream:stream.write(b'changed')
            return result
        with patch.object(workspace_sqlite,'build_sqlite_export',side_effect=alter_source):
            response=self.export(candidate,'wheeler-sqlite')
        self.assertEqual(response.status_code,400,response.get_json())
        self.assertEqual(self.case.datasets.rows,[])
        self.assertFalse(any(row['action']=='dataset_revision_exported' for row in self.case.events.rows))

    def test_empty_query_wrong_options_and_missing_receipt_fail_closed(self):
        candidate=self.save({'any':[]})
        self.assertEqual(self.export(candidate).status_code,400)
        path='/api/explore/revisions/'+candidate['revision_uuid']+'/exports'
        for options in ({},{'format':'bad','expected_recipe_sha256':'a'*64},
                        {'format':'reference-json','expected_recipe_sha256':'a'*64,'mask':['foreign']},
                        {'format':'reference-json','expected_recipe_sha256':None},
                        {'format':'reference-json','expected_recipe_sha256':'a'*64,'name':[]}):
            with self.subTest(options=options):
                self.assertEqual(self.client.post(path,json=options,headers=self.headers).status_code,400)
        self.assertEqual(self.case.datasets.rows,[])

if __name__=='__main__':unittest.main()
