"""Disposable exact-identity additive exchange and handoff tests."""
import copy
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
import uuid

from flask import Flask
from workspace_tag_exchange import (normalize_document, preview_import, export_document,
    register_tag_exchange_routes, samarjit_document, frozen_document)
from workspace_sqlite import build_sqlite_export
from workspace_matlab import build_matlab_export
import test_workspace_sqlite as sqlite_tests


def uid(): return str(uuid.uuid4())


class Store:
    def __init__(self, profile):
        self.profile=profile; self.saved={}; self.calls=[]
    def lock(self): return contextlib.nullcontext()
    def list_profiles(self):
        return {'profiles':[self.profile], 'default_profile_uuid':self.profile['profile_uuid']}
    def read_targets(self,kind,ids):
        assert 1<=len(ids)<=1000
        self.calls.append((kind,len(ids)))
        return {key:copy.deepcopy(self.saved.get((kind,key),{'tags':[],'revisions':{}})) for key in ids}
    def apply_batch(self,operations,actor,profiles=None,audit_context=None):
        for op in operations:
            target=self.saved.setdefault((op['target_kind'],op['target_uuid']),{'tags':[],'revisions':{}})
            profile=op['profile_uuid']; assert target['revisions'].get(profile,0)==op['expected_revision']
            author=next(p['display_name'] for p in profiles if p['profile_uuid']==profile)
            target['revisions'][profile]=op['expected_revision']+1
            target['tags'] += [dict(tag=tag,profile_uuid=profile,author_name=author) for tag in op['tags_add']]
        return {'changed':len(operations),'actor':actor,'context':audit_context}


class TagExchangeTests(unittest.TestCase):
    def setUp(self):
        self.ids=[uid(),uid()];self.cells=[uid(),uid()];self.profile={'profile_uuid':uid(),'display_name':'Scientist A'}
        self.service=types.SimpleNamespace(project={'project_uuid':uid()},
            rows={key:{'epoch_uuid':key,'cell_uuid':cell,'source_sha256':str(i+1)*64,'cell_label':'Cell1','date':f'2026-09-{23+i}'} for i,(key,cell) in enumerate(zip(self.ids,self.cells))},
            cells={cell:{'label':'Cell1'} for cell in self.cells})
        self.store=Store(self.profile)
    def document(self,kind='epoch',target=None):
        return {'format':'rieke-tag-exchange','version':1,'project_uuid':self.service.project['project_uuid'],
            'entries':[{'target_kind':kind,'target_uuid':target or self.ids[0],
                        'tags':[{'tag':'good','profile_uuid':self.profile['profile_uuid'],'author_name':'Scientist A'}]}]}
    def test_same_labels_shuffled_subset_exact_uuid_and_additive_apply(self):
        app=Flask(__name__);register_tag_exchange_routes(app,self.service,self.store,contextlib.nullcontext())
        client=app.test_client();doc=self.document();preview=client.post('/api/annotations/import/preview',json={'document':doc})
        self.assertEqual(preview.status_code,200);self.assertEqual(self.store.saved,{})
        receipt=client.post('/api/annotations/import/apply',json={'document':doc,'preview_token':preview.json['preview_token'],'profile_uuid':self.profile['profile_uuid']})
        self.assertEqual(receipt.status_code,200);self.assertEqual(receipt.json['result']['actor'],'Scientist A')
        self.assertNotIn(('epoch',self.ids[1]),self.store.saved)
        self.assertEqual(preview_import(doc,self.service,self.store)['unchanged_count'],1)
        alltags=export_document(self.service,self.store);self.assertEqual(len(alltags['entries']),4)
        alltags['entries'].reverse();self.assertEqual(normalize_document(alltags,self.service)[0]['entries'][0]['target_kind'],'cell')
        self.assertEqual(client.post('/api/annotations/import/apply',json={'document':doc,'preview_token':preview.json['preview_token']}).status_code,409)
    def test_invalid_identity_kind_duplicate_source_author_fail_closed(self):
        variants=[]
        for target in (self.cells[0],uid(),'Cell1'):
            variants.append(self.document(target=target))
        duplicate=self.document();duplicate['entries']*=2;variants.append(duplicate)
        source=self.document();source['entries'][0]['source_sha256']='f'*64;variants.append(source)
        author=self.document();author['entries'][0]['tags'][0]['author_name']='Other name';variants.append(author)
        for doc in variants:
            with self.subTest(doc=doc),self.assertRaises(ValueError):preview_import(doc,self.service,self.store)
        self.assertEqual(self.store.saved,{})
    def test_legacy_exact_identity_author_claim_and_unsupported_level(self):
        legacy={uid():{'tags':[],self.cells[0]:{'tags':[['Old User','cell tag']],self.ids[1]:{'tags':[['Old User','epoch tag']]}}}}
        doc,profiles,warnings=normalize_document(legacy,self.service)
        self.assertEqual({e['target_kind'] for e in doc['entries']},{'cell','epoch'});self.assertTrue(warnings)
        bad={uid():{'tags':[['Old User','unsupported']]}}
        with self.assertRaisesRegex(ValueError,'unsupported'):normalize_document(bad,self.service)
    def test_registered_reads_bounded_and_empty_kind_allowed(self):
        self.assertEqual(preview_import(self.document(),self.service,self.store)['addition_count'],1)
        for _ in range(1001):
            key=uid();self.service.rows[key]={'epoch_uuid':key,'cell_uuid':self.cells[0],'source_sha256':'1'*64}
        export_document(self.service,self.store)
        self.assertTrue(all(n<=1000 for _,n in self.store.calls))
    def test_legacy_export_real_hierarchy_checksum_and_empty_ancestor_tags(self):
        with tempfile.TemporaryDirectory() as folder:
            self.service.project_dir=Path(folder);path=Path(folder)/'imports'/'metadata.json';path.parent.mkdir()
            tree={'uuid':uid(),'animals':[{'uuid':uid(),'preparations':[{'uuid':uid(),'cells':[{'uuid':self.cells[0],'epoch_groups':[{'uuid':uid(),'epoch_blocks':[{'uuid':uid(),'epochs':[{'uuid':self.ids[0]}]}]}]}]}]}]}
            raw=json.dumps(tree).encode();path.write_bytes(raw)
            self.service.manifests={'1'*64:{'metadata_path':str(path),'metadata_sha256':hashlib.sha256(raw).hexdigest()}}
            doc=self.document();legacy=samarjit_document(doc,self.service)
            self.assertEqual(next(iter(legacy.values()))['tags'],[])
            parsed,_,_=normalize_document(legacy,self.service)
            self.assertEqual(parsed['entries'][0]['target_uuid'],self.ids[0])
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'changed'):samarjit_document(doc,self.service)


class FrozenSharedTagTests(unittest.TestCase):
    def setUp(self):
        fixture=sqlite_tests.SQLiteExportTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.case=fixture.case;self.package=fixture.package;self.path=fixture.path;self.service=fixture.service

    def test_shared_annotations_sql_and_mat_preserve_kind_author_and_empty_revisions(self):
        author=uid()
        for record in self.package['epochs']:
            def chip(kind):return dict(target_kind=kind,target_uuid=record[kind+'_uuid'],profile_uuid=author,author_name='Scientist A',tag='same text',revision=3)
            cell,epoch=chip('cell'),chip('epoch')
            record['annotations']={'epoch_uuid':record['epoch_uuid'],'cell_uuid':record['cell_uuid'],
                'cell_tags':[cell],'epoch_tags':[epoch],'effective_tags':[cell,epoch],
                'revisions':{'cell':{author:3},'epoch':{author:3}}}
        build_sqlite_export(self.package,self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shared_annotations').fetchone()[0],4)
            self.assertEqual(db.execute('SELECT count(*) FROM epoch_tags').fetchone()[0],4)
            self.assertEqual({r[0] for r in db.execute('SELECT profile_uuid FROM shared_annotations')},{author})
        from scipy.io import loadmat
        recipe=copy.deepcopy(self.package['recipe']);recipe['destination']='epictree-mat'
        from workspace_recipes import seal
        recipe=seal(recipe)
        target=Path(self.case.temp.name)/'mat-shared'
        build_matlab_export(self.service,recipe,target,epoch_records=self.package['epochs'])
        document=json.loads((target/'annotations.json').read_text())
        self.assertEqual(len(document['entries']),4)
        data=loadmat(target/'recordings.mat',simplify_cells=True)
        self.assertEqual(json.loads(data['metadata']['workspace_tags_json']),document)
        self.assertTrue((target/'workspaceTag.m').exists())


class TagExchangeTransactionTests(unittest.TestCase):
    def setUp(self):
        import test_workspace_annotations as shared_tests
        self.case=shared_tests.SharedAnnotationTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.client=self.case.client;self.headers=self.case.headers
    def document(self):
        return {'format':'rieke-tag-exchange','version':1,'project_uuid':self.case.service.project['project_uuid'],
                'entries':[{'target_kind':'epoch','target_uuid':self.case.first,'tags':[
                    {'tag':'MATLAB review','profile_uuid':uid(),'author_name':'Imported scientist'}]}]}
    def preview(self,doc):
        result=self.client.post('/api/annotations/import/preview',headers=self.headers,json={'document':doc})
        self.assertEqual(result.status_code,200,result.json);return result.json
    def test_real_store_additive_author_import_audit_and_subset(self):
        self.case.edit('epoch',self.case.first,['original'])
        doc=self.document();preview=self.preview(doc)
        response=self.client.post('/api/annotations/import/apply',headers=self.headers,
            json={'document':doc,'preview_token':preview['preview_token'],'profile_uuid':self.case.author})
        self.assertEqual(response.status_code,200,response.json)
        chips=self.case.epoch(self.case.first)['epoch_tags'];self.assertEqual({t['tag'] for t in chips},{'original','MATLAB review'})
        self.assertEqual(next(t for t in chips if t['tag']=='MATLAB review')['profile_uuid'],doc['entries'][0]['tags'][0]['profile_uuid'])
        self.assertEqual(self.case.epoch(self.case.second)['effective_tags'],[])
        self.assertEqual(self.preview(doc)['addition_count'],0)
        self.assertFalse(self.case.case.curation.rows)
    def test_import_requires_explicit_author_even_when_default_exists(self):
        doc=self.document();preview=self.preview(doc)
        before=copy.deepcopy((self.case.profiles.rows,self.case.records.rows))
        result=self.client.post('/api/annotations/import/apply',headers=self.headers,
            json={'document':doc,'preview_token':preview['preview_token']})
        self.assertEqual(result.status_code,400,result.json)
        self.assertEqual((self.case.profiles.rows,self.case.records.rows),before)
    def test_state_failure_rolls_back_new_profile_and_tags(self):
        from unittest.mock import patch
        doc=self.document();preview=self.preview(doc)
        before=copy.deepcopy((self.case.profiles.rows,self.case.records.rows))
        with patch.object(self.case.records,'insert1',side_effect=RuntimeError('State unavailable')):
            response=self.client.post('/api/annotations/import/apply',headers=self.headers,
                json={'document':doc,'preview_token':preview['preview_token'],'profile_uuid':self.case.author})
        self.assertEqual(response.status_code,500,response.json)
        self.assertEqual((self.case.profiles.rows,self.case.records.rows),before)
    def test_changed_author_revision_and_wrong_importer_fail_without_partial_write(self):
        doc=self.document();doc['entries'][0]['tags'][0].update(profile_uuid=self.case.author,
            author_name=self.case.store.default_profile['display_name'])
        preview=self.preview(doc);self.case.edit('epoch',self.case.first,['concurrent'])
        result=self.client.post('/api/annotations/import/apply',headers=self.headers,
            json={'document':doc,'preview_token':preview['preview_token'],'profile_uuid':self.case.author})
        self.assertEqual(result.status_code,409)
        current=self.preview(doc)
        bad=self.client.post('/api/annotations/import/apply',headers=self.headers,
            json={'document':doc,'preview_token':current['preview_token'],'profile_uuid':uid()})
        self.assertEqual(bad.status_code,400)
        self.assertEqual([tag['tag'] for tag in self.case.epoch(self.case.first)['epoch_tags']],['concurrent'])
