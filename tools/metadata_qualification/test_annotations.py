"""Isolated native annotation/tag/edit/export checks with transactional table doubles.

Uses production SharedAnnotations and tag exchange, not a candidate annotation
implementation. Fixture tables are in memory and project files are in /tmp.
"""
import copy
from pathlib import Path
import sys
import unittest
import uuid

REPO=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(REPO/'python'),str(REPO/'python'/'tests')]
import test_workspace_annotations as fixtures
from disco.decisions.tag_exchange import export_document, preview_import
from disco.decisions.curation import RevisionConflict


class IsolatedAnnotationQualification(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.SharedAnnotationTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service=self.fixture.service;self.store=self.fixture.store
        first=self.fixture.first
        for _ in range(8):
            key=str(uuid.uuid4());row=copy.deepcopy(self.service.rows[first]);row['epoch_uuid']=key
            self.service.rows[key]=row;self.service.details[key]=copy.deepcopy(self.service.details[first])
            self.service.details[key]['metadata']['epoch']['uuid']=key
            self.service._fingerprints[key]=self.service._fingerprints[first]
        self.ids=list(self.service.rows)
        self.immutable=copy.deepcopy((self.service.rows,self.service.details))
        self.author=self.store.default_profile['profile_uuid']

    def test_tag_ten_exact_ownership_inheritance_edit_and_export(self):
        self.assertEqual(len(self.ids),10)
        cell=self.fixture.cell
        self.store.update('cell',[cell],self.author,{'tags_add':['shared']},{cell:0},'fixture actor')
        result=self.store.update('epoch',self.ids,self.author,{'tags_add':['review']},
                                 {identity:0 for identity in self.ids},'fixture actor')
        self.assertEqual(result['changed'],10)
        states=self.store.for_epochs([self.service.rows[i] for i in self.ids])
        for identity,state in states.items():
            self.assertEqual([t['tag'] for t in state['epoch_tags']],['review'])
            self.assertEqual({t['target_uuid'] for t in state['epoch_tags']},{identity})
            self.assertEqual({t['profile_uuid'] for t in state['epoch_tags']},{self.author})
            expected=['shared'] if self.service.rows[identity]['cell_uuid']==cell else []
            self.assertEqual([t['tag'] for t in state['cell_tags']],expected)
        self.assertEqual(len(self.fixture.records.rows),11) # inherited cell tag stored once
        self.assertEqual((self.service.rows,self.service.details),self.immutable)
        document=export_document(self.service,self.store)
        epochs={e['target_uuid']:e for e in document['entries'] if e['target_kind']=='epoch'}
        self.assertEqual(set(epochs),set(self.ids))
        for identity,entry in epochs.items():
            self.assertEqual(entry['tags'],[dict(tag='review',profile_uuid=self.author,
                author_name=self.store.default_profile['display_name'])])
        self.assertEqual(preview_import(document,self.service,self.store)['addition_count'],0)
        first=self.ids[0]
        self.store.update('epoch',[first],self.author,{'tags_remove':['review']},{first:1},'fixture actor')
        edited=self.store.for_epochs([self.service.rows[first]])[first]
        self.assertEqual(edited['epoch_tags'],[])
        self.assertEqual([t['tag'] for t in edited['cell_tags']],['shared'])
        after=export_document(self.service,self.store)
        self.assertEqual(next(e for e in after['entries'] if e['target_uuid']==first)['tags'],[])
        self.assertEqual((self.service.rows,self.service.details),self.immutable)
        self.assertEqual(self.fixture.case.curation.rows,[]) # shared tags never become protocol curation

    def test_annotation_generation_changes_when_tag_membership_is_equal(self):
        cell=self.fixture.cell
        self.store.update('cell',[cell],self.author,{'tags_add':['keep']},{cell:0},'actor')
        meta=self.service.explore_preview({'all':[]},'cell',include_tree=False)
        predicate={'field':'annotations/effective/tags','operator':'contains','value':'keep'}
        before=self.service.explore_preview(predicate,'cell',include_tree=False)
        self.store.update('cell',[cell],self.author,{'tags_add':['unrelated']},{cell:1},'actor')
        after=self.service.explore_preview(predicate,'cell',include_tree=False)
        self.assertEqual(before['membership'],after['membership'])
        self.assertNotEqual(before['annotation_scope']['revision'],after['annotation_scope']['revision'])
        self.assertNotEqual(before['tree_revision'],after['tree_revision'])
        self.assertEqual(meta['tree_revision'],self.service.explore_preview({'all':[]},'cell',include_tree=False)['tree_revision'])
        self.store.update('cell',[cell],self.author,{'tags_remove':['keep']},{cell:2},'actor')
        removed=self.service.explore_preview(predicate,'cell',include_tree=False)
        self.assertNotEqual(after['membership'],removed['membership'])
        self.assertEqual((self.service.rows,self.service.details),self.immutable)

    def test_stale_revision_fault_rolls_back_ten_target_batch_and_export_is_read_only(self):
        last=self.ids[-1]
        self.store.update('epoch',[last],self.author,{'tags_add':['existing']},{last:0},'actor')
        before=copy.deepcopy((self.fixture.records.rows,self.fixture.case.events.rows))
        with self.assertRaises(RevisionConflict):
            self.store.update('epoch',self.ids,self.author,{'tags_add':['failed']},
                              {i:0 for i in self.ids},'actor')
        self.assertEqual((self.fixture.records.rows,self.fixture.case.events.rows),before)
        export_document(self.service,self.store)
        self.assertEqual((self.fixture.records.rows,self.fixture.case.events.rows),before)
        self.assertEqual((self.service.rows,self.service.details),self.immutable)


if __name__=='__main__':unittest.main()
