"""Exact protocol pagination with bounded decoration and selected curation reads."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from workspace_disk_index import DiskMetadataIndex
from workspace_service import WorkspaceService
import test_workspace_api as api_fixture
from workspace_curation import RevisionConflict


class EpochPageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.index = DiskMetadataIndex.build(Path(self.fixture.temp.name)/'pages.sqlite',
            self.service.rows,self.service.details,self.service.sources,'page-generation',self.service.project['project_uuid'])
        self.service.disk_index,self.service.details = self.index,self.index.details
        self.protocol = self.service.protocol_id

    def test_selected_curation_matches_legacy_rows_and_refreshes_every_page(self):
        self.service.set_curation_provider(lambda protocol,fingerprints:
            self.fixture.store.read(protocol,list(fingerprints),fingerprints))
        expected = self.service.filtered_rows(self.protocol)
        self.fixture.curation.read_log.clear()
        actual = self.service.epoch_page(self.protocol,limit=1)
        self.assertEqual(actual['epochs'],expected[:1])
        self.assertEqual(self.fixture.curation.read_log[-1]['restrictions'][-1],
            [{'epoch_uuid':self.service.ids[0]}])
        identity=self.service.ids[0]
        self.fixture.store.update(self.protocol,[identity],{'tags_add':['new']},{identity:0},
            {identity:self.service._fingerprints[identity]},'fixture')
        updated=self.service.epoch_page(self.protocol,limit=1)
        self.assertEqual(updated['epochs'][0]['curation']['tags'],['new'])
        self.assertEqual(updated['epochs'][0]['curation']['revision'],1)
        # Returning detached decorated rows never modifies the raw metadata.
        updated['epochs'][0]['cell_label']='changed output'
        self.assertNotEqual(self.service.rows[identity]['cell_label'],'changed output')

    def test_anchors_filters_in_place_membership_and_fingerprints_remain_current(self):
        first,second=self.service.ids
        page=self.service.epoch_page(self.protocol,limit=1,anchor_uuid=second)
        self.assertEqual((page['offset'],page['anchor_index'],page['total']),(1,1,2))
        filtered=self.service.epoch_page(self.protocol,{'cell_uuid':self.service.cell_ids[1]},limit=1,anchor_uuid=second)
        self.assertEqual((filtered['offset'],filtered['total']),(0,1))
        with self.assertRaises(ValueError):
            self.service.epoch_page(self.protocol,{'cell_uuid':self.service.cell_ids[1]},anchor_uuid=first)
        self.service.protocols[self.protocol]['result']['epochs'].pop()
        self.assertEqual(self.service.epoch_page(self.protocol)['total'],1)
        with self.assertRaises(ValueError):self.service.epoch_page(self.protocol,anchor_uuid=second)
        self.service._fingerprints[first]='c'*64
        with patch.object(self.service,'_filter_rows',wraps=self.service._filter_rows) as rebuild:
            self.service.epoch_page(self.protocol)
            rebuild.assert_called_once()
        with self.index.path.open('ab') as stream:stream.write(b'changed')
        with self.assertRaises(ValueError):self.service.epoch_page(self.protocol)

    def test_tag_membership_is_rechecked_while_ordinary_order_is_cached(self):
        selected={self.service.ids[0]}
        self.service.shared_annotations=SimpleNamespace(for_epochs=lambda rows: {
            row['epoch_uuid']:{'effective_tags':[{'tag':'keep'}] if row['epoch_uuid'] in selected else []}
            for row in rows})
        self.service.curation_provider=Mock(return_value={})
        body={'tag':'keep'}
        first=self.service.epoch_page(self.protocol,body)
        self.assertEqual([row['epoch_uuid'] for row in first['epochs']],self.service.ids[:1])
        selected.clear();selected.add(self.service.ids[1])
        second=self.service.epoch_page(self.protocol,body)
        self.assertEqual([row['epoch_uuid'] for row in second['epochs']],self.service.ids[1:])
        for call in self.service.curation_provider.call_args_list:
            self.assertEqual(len(call.args[1]),1)

    def test_binding_header_avoids_recipe_copy_and_binding_change_reloads_membership(self):
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        history=self.fixture.explorer_history
        full=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(full['revision_uuid'],self.protocol,0,'fixture',{},2)
        getter=Mock(wraps=history.protocol_binding)
        self.service.set_binding_provider(getter,header_provider=history.protocol_binding_header)
        self.assertEqual(self.service.epoch_page(self.protocol)['total'],2)
        self.assertEqual(getter.call_count,1)
        with patch('workspace_explorer.copy.deepcopy',side_effect=AssertionError('No recipe copy on warm page')):
            # The in-memory SQL double itself deepcopies its one binding row.
            # Supply that same already-fetched immutable header to isolate the
            # potentially huge recipe copy from the real header query's cost.
            self.service.binding_header_provider=lambda protocol:{'version':1,'revision_uuid':full['revision_uuid']}
            self.assertEqual(self.service.epoch_page(self.protocol)['total'],2)
        self.assertEqual(getter.call_count,1)
        detached=history.protocol_binding(self.protocol)
        detached['recipe']['epochs'].clear()
        self.assertEqual(len(history.protocol_binding(self.protocol)['recipe']['epochs']),2)
        narrow=copy.deepcopy(preview)
        narrow['membership']=narrow['membership'][:1];narrow['matched_count']=1
        next_revision=history.create(narrow,self.service.sources,'catalog.json','fixture')
        history.bind(next_revision['revision_uuid'],self.protocol,1,'fixture',{},2)
        self.service.binding_header_provider=history.protocol_binding_header
        self.assertEqual(self.service.epoch_page(self.protocol)['total'],1)
        self.assertEqual(getter.call_count,2)

    def test_epoch_scope_cache_respects_byte_budget_and_oversize_scope_is_uncached(self):
        page=self.service.epoch_page(self.protocol,limit=1)
        self.service._epoch_page_cache=None
        # The fingerprint guard fits; the two membership tuples do not.
        budget=sys.getsizeof(self.service._fingerprints)+16*1024+1
        with patch('workspace_service.EPOCH_PAGE_CACHE_BYTES',budget), \
             patch.object(self.service,'_filter_rows',wraps=self.service._filter_rows) as rebuild:
            self.assertEqual(self.service.epoch_page(self.protocol,limit=1),page)
            self.assertEqual(self.service.epoch_page(self.protocol,limit=1),page)
        self.assertEqual(rebuild.call_count,2)
        self.assertEqual(self.service._epoch_page_cache[1],{})

    def test_large_curation_batch_reads_exact_chunks_and_late_conflict_rolls_back(self):
        ids=[str(uuid.UUID(int=number+1000)) for number in range(1000)]
        outside=str(uuid.UUID(int=999999))
        self.fixture.curation.rows.extend({'project_uuid':self.service.project['project_uuid'],
            'protocol_uuid':self.protocol,'epoch_uuid':identity,'included':True,'tags':[],
            'review_state':'unreviewed','revision':1 if identity==ids[-1] else 0,
            'metadata_fingerprint':'b'*64} for identity in [*ids,outside])
        before=copy.deepcopy(self.fixture.curation.rows)
        self.fixture.curation.read_log.clear()
        with self.assertRaises(RevisionConflict):
            self.fixture.store.update(self.protocol,ids,{'included':False},
                {key:0 for key in ids},{key:'b'*64 for key in ids},'fixture')
        self.assertEqual(self.fixture.curation.rows,before)
        reads=self.fixture.curation.read_log
        self.assertEqual(len(reads),4)
        selected=[item['epoch_uuid'] for read in reads for item in read['restrictions'][-1]]
        self.assertEqual(selected,ids)
        self.assertTrue(all(len(read['restrictions'][-1])<=250 for read in reads))
        self.assertNotIn(outside,selected)


class LargeEpochPageStructureTests(unittest.TestCase):
    def test_100000_epoch_warm_page_reads_and_decorates_only_requested_rows(self):
        # Structural fixture: no SQL, disk contents or waveforms. Small real
        # sealed-index tests above independently verify the signature guard.
        class CountedRows(dict):
            reads=0
            def __getitem__(self,key):
                self.reads+=1
                return super().__getitem__(key)
        service=WorkspaceService.__new__(WorkspaceService)
        service._loaded=True
        service.rows=CountedRows()
        service._fingerprints={}
        protocol=str(uuid.UUID(int=1))
        ids=[]
        for number in range(100000):
            identity=str(uuid.UUID(int=number+2));ids.append(identity)
            service.rows[identity]={'epoch_uuid':identity,'cell_uuid':str(uuid.UUID(int=number//100+200000)),
                'cell_label':'Same display label','date':'2026-09-29','start_time':f'09/29/2026 {number:012d}'}
            service._fingerprints[identity]='a'*64
        service.protocols={protocol:{'definition':{},'result':{'epochs':[
            {'uuid':identity,'metadata_hash':'a'*64} for identity in reversed(ids)]}}}
        index=DiskMetadataIndex.__new__(DiskMetadataIndex)
        index.generation='structural-only';index._check=Mock()
        service.disk_index=index
        service.curation_provider=Mock(return_value={})
        service.epoch_page(protocol,limit=60)
        service.rows.reads=0;service.curation_provider.reset_mock()
        with patch.object(service,'query_result',side_effect=AssertionError('No full recipe hydration')), \
             patch.object(service,'_filter_rows',side_effect=AssertionError('No full sort on a warm page')), \
             patch.object(service,'_decorate',wraps=service._decorate) as decorate:
            page=service.epoch_page(protocol,offset=90000,limit=60)
        self.assertEqual([row['epoch_uuid'] for row in page['epochs']],ids[90000:90060])
        self.assertEqual(page['total'],100000)
        self.assertEqual(service.rows.reads,60)
        self.assertEqual(decorate.call_count,60)
        self.assertEqual(set(service.curation_provider.call_args.args[1]),set(ids[90000:90060]))
        far=service.epoch_page(protocol,limit=60,anchor_uuid=ids[-1])
        self.assertEqual(far['anchor_index'],99999)
        self.assertEqual(far['offset'],99960)
        self.assertEqual([row['epoch_uuid'] for row in far['epochs']],ids[99960:])


if __name__=='__main__':unittest.main()
