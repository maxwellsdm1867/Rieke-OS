"""Small real-SQLite preparation/checkpoint lifecycle, no native server work."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_workspace_annotations import SharedAnnotationTests
from workspace_annotation_preparation import prepare_annotation_indexes,_ordered_rows
from workspace_annotation_checkpoint import restore_shared_checkpoint,save_shared_checkpoint
from workspace_disk_index import DiskMetadataIndex
from workspace_recipes import checksum
from workspace_shared_tag_index import SharedTagIndex


class AnnotationPreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=SharedAnnotationTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.service=self.fixture.service;self.shared=self.fixture.store;self.store=self.fixture.case.store
        self.service.project_dir=Path(self.service.project_dir).resolve()
        self.fixture.edit('cell',self.fixture.cell,['whole cell','QC'])
        self.index=DiskMetadataIndex.build(Path(self.fixture.case.temp.name)/'preparation.sqlite',
            self.service.rows,self.service.details,self.service.sources,'preparation-source',self.service.project['project_uuid'])
        self.service.disk_index=self.index
        self.witness='first witness';self.reads=[]
        self.tracker=SimpleNamespace(token=lambda:(self.witness,self.proof()['tables']['shared_annotation']['xor']))
        self.shared.state_generation=self.tracker
        self.fresh_index()
        self.proof_patch=patch('workspace_annotation_checkpoint._proof',side_effect=lambda service:self.proof())
        self.proof_patch.start();self.addCleanup(self.proof_patch.stop)

    def proof(self):
        return {'project_uuid':self.service.project['project_uuid'],'tables':{
            'shared_annotation':{'count':len(self.fixture.records.rows),
                'xor':checksum(json.dumps(self.fixture.records.rows,sort_keys=True,default=str))},
            'annotation_profile':{'count':len(self.fixture.profiles.rows),
                'xor':checksum(json.dumps(self.fixture.profiles.rows,sort_keys=True,default=str))}}}

    def fresh_index(self):
        previous=getattr(self.shared,'_shared_tag_index',None)
        if previous is not None:previous.close()
        def records(keys):
            self.reads.append(keys)
            yield from copy.deepcopy(self.fixture.records.rows)
        index=SharedTagIndex(generation=self.tracker.token,changes=lambda previous:None,
            records=records,validate=self.shared._index_record_tags)
        self.shared._shared_tag_index=index;self.shared._shared_tag_index_tracker=self.tracker
        self.addCleanup(index.close)
        return index

    def prepare(self):return prepare_annotation_indexes(self.service,self.store,self.shared)

    def test_preparation_reuses_records_and_cell_tags_are_not_copied_to_epochs(self):
        first=self.prepare();second=self.prepare()
        self.assertEqual(first['status'],'ready');self.assertEqual(second['status'],'ready')
        self.assertEqual(len(self.reads),1)
        self.assertEqual(len(self.fixture.records.rows),1)
        self.assertEqual(self.fixture.records.rows[0]['target_kind'],'cell')
        result,_=self.shared._shared_tag_index.matching(_ordered_rows(self.service),{'tag':'whole cell'})
        self.assertEqual(result,(self.fixture.first,))

    def test_checkpoint_reopens_under_new_witness_only_with_matching_fresh_content(self):
        self.prepare();saved=save_shared_checkpoint(self.service,self.shared)
        self.assertTrue(saved['saved'],saved)
        old=self.shared._shared_tag_index.token
        index=self.fresh_index();self.witness='new witness after restart';self.reads.clear()
        restored=restore_shared_checkpoint(self.service,self.shared)
        self.assertTrue(restored['restored'],restored)
        self.assertNotEqual(index.token,old)
        self.assertEqual(self.prepare()['status'],'ready')
        self.assertEqual(self.reads,[])
        self.assertEqual(index.summary(_ordered_rows(self.service))['shared_tagged_epochs'],1)
        self.assertEqual(index.suggestions('whole',30)['tags'][0]['count'],1)
        self.assertEqual(index.stats['full_builds'],0)

    def test_stale_content_corruption_and_unavailable_proof_rebuild_instead_of_reuse(self):
        self.prepare();saved=save_shared_checkpoint(self.service,self.shared);self.assertTrue(saved['saved'],saved)
        self.fresh_index();self.fixture.records.rows[0]['tags']=['new canonical tag']
        self.assertFalse(restore_shared_checkpoint(self.service,self.shared)['restored'])
        self.assertEqual(self.prepare()['status'],'ready')
        current=save_shared_checkpoint(self.service,self.shared);self.assertTrue(current['saved'],current)
        self.fresh_index()
        path=self.service.project_dir/'cache'/'annotation-index'/(current['sha256']+'.sqlite')
        with path.open('ab') as stream:stream.write(b'corrupted derived checkpoint')
        self.assertFalse(restore_shared_checkpoint(self.service,self.shared)['restored'])
        self.assertEqual(self.prepare()['status'],'ready')
        self.fresh_index()
        with patch('workspace_annotation_checkpoint._proof',return_value=None):
            self.assertFalse(restore_shared_checkpoint(self.service,self.shared)['restored'])

    def test_edit_during_checkpoint_publication_cannot_publish_stale_membership(self):
        import workspace_annotation_checkpoint as checkpoint
        self.prepare()
        initial=save_shared_checkpoint(self.service,self.shared)
        self.assertTrue(initial['saved'])
        pointer=self.service.project_dir/'cache'/'annotation-index'/'current.json'
        prior=pointer.read_bytes()
        sha=checkpoint._sha;edited=[]
        def concurrent_edit(path):
            result=sha(path)
            if Path(path).suffix=='.sqlite' and not edited:
                self.fixture.records.rows[0]['tags']=['changed while sealing']
                self.fixture.records.rows[0]['revision']+=1
                edited.append(True)
            return result
        with patch.object(checkpoint,'_sha',side_effect=concurrent_edit):
            saved=save_shared_checkpoint(self.service,self.shared)
        self.assertTrue(edited)
        self.assertFalse(saved['saved'])
        self.assertEqual(pointer.read_bytes(),prior)
        self.fresh_index()
        self.assertFalse(restore_shared_checkpoint(self.service,self.shared)['restored'])
        self.prepare()
        matches,_=self.shared._shared_tag_index.matching(_ordered_rows(self.service),{'tag':'changed while sealing'})
        self.assertEqual(matches,(self.fixture.first,))
        matches,_=self.shared._shared_tag_index.matching(_ordered_rows(self.service),{'tag':'whole cell'})
        self.assertEqual(matches,())

    def test_changed_source_links_during_preparation_discard_derived_work(self):
        def progress(stage):
            if stage=='preparing_tag_suggestions':
                self.service.rows[self.fixture.first]['cell_uuid']=self.fixture.other_cell
        with self.assertRaisesRegex(ValueError,'identities changed'):
            prepare_annotation_indexes(self.service,self.store,self.shared,progress=progress)
        self.assertEqual(self.service.annotation_preparation['status'],'failed')
        self.assertIsNone(self.shared._shared_tag_index.connection)


if __name__=='__main__':unittest.main()
