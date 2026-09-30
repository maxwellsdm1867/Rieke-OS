"""Dense multi-tag annotation operations retain exact profile and target scope."""
import copy
import unittest
from unittest.mock import patch
import uuid
from types import SimpleNamespace

import test_workspace_annotations as fixture
from workspace_curation import RevisionConflict
from workspace_tag_predicates import TagPredicates,SHARED_FIELDS


class DenseAnnotationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.SharedAnnotationTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.store=self.case.store;self.service=self.case.service;self.table=self.case.records
        self.author=self.store.default_profile['profile_uuid']
        original=self.service.rows[self.case.first]
        self.ids=[str(uuid.UUID(int=n+10000)) for n in range(1003)]
        for key in self.ids:self.service.rows[key]={**original,'epoch_uuid':key}
        self.multi_tags=['QC','qc','artifact','é','e\u0301']
        for key in self.ids:
            self.table.rows.append({'project_uuid':self.service.project['project_uuid'],
                'target_kind':'epoch','target_uuid':key,'profile_uuid':self.author,
                'tags':list(self.multi_tags),'author_name':self.store.default_profile['display_name'],
                'revision':1,'updated_at':'fixture'})
        self.other_author=str(uuid.uuid4())
        self.table.rows.append({**self.table.rows[0],'profile_uuid':self.other_author,'author_name':'Same display name','tags':['QC','other profile']})

    def test_thousand_target_read_uses_four_exact_primary_key_batches_and_preserves_all_profiles(self):
        selected=self.ids[:1000]
        result=self.store.read_targets('epoch',selected)
        self.assertEqual(set(result),set(selected))
        reads=self.table.read_log
        self.assertEqual(len(reads),4)
        self.assertTrue(all(len(read['restrictions'][-1])<=250 for read in reads))
        requested=[item['target_uuid'] for read in reads for item in read['restrictions'][-1]]
        self.assertEqual(requested,selected)
        self.assertEqual(set(result[selected[0]]['revisions']),{self.author,self.other_author})
        chips=result[selected[0]]['tags']
        self.assertEqual(len([chip for chip in chips if chip['tag']=='QC']),2)
        self.assertEqual({chip['tag'] for chip in chips},{*self.multi_tags,'other profile'})

    def test_thousand_target_save_reads_only_exact_target_author_keys(self):
        selected=self.ids[:1000];before=copy.deepcopy(self.table.rows)
        operations=[{'target_kind':'epoch','target_uuid':key,'profile_uuid':self.author,
            'expected_revision':1,'tags_add':['reviewed'],'tags_remove':['artifact']} for key in selected]
        with patch.object(self.store,'_rows',side_effect=AssertionError('No full annotation read')):
            result=self.store.apply_batch(operations,'fixture')
        self.assertEqual(result['changed'],1000)
        reads=self.table.read_log
        self.assertEqual(len(reads),4)
        requested=[item for read in reads for item in read['restrictions'][-1]]
        self.assertEqual(requested,[{'target_kind':'epoch','target_uuid':key,'profile_uuid':self.author} for key in selected])
        self.assertTrue(all(len(read['restrictions'][-1])<=250 for read in reads))
        for index,row in enumerate(self.table.rows):
            if row['target_uuid'] in selected and row['profile_uuid']==self.author:
                self.assertEqual(row['revision'],2)
                self.assertEqual(set(row['tags']),({*self.multi_tags,'reviewed'}-{'artifact'}))
            else:self.assertEqual(row,before[index])

    def test_last_target_revision_conflict_rolls_back_entire_multi_tag_batch(self):
        self.table.rows[999]['revision']=2
        before=copy.deepcopy(self.table.rows)
        operations=[{'target_kind':'epoch','target_uuid':key,'profile_uuid':self.author,
            'expected_revision':1,'tags_add':['never']} for key in self.ids[:1000]]
        with self.assertRaises(RevisionConflict):self.store.apply_batch(operations,'fixture')
        self.assertEqual(self.table.rows,before)
        self.assertFalse(self.case.case.events.rows)

    def test_verified_index_browse_summary_and_catalog_never_hydrate_snapshot_or_chips(self):
        rows=[self.service.rows[key] for key in self.ids]
        expected_summary=self.store.summary(rows)
        expected_catalog=TagPredicates(self.service).catalog_fields(self.ids)
        self.store.state_generation=SimpleNamespace(token=lambda:1,shared_changes=lambda token:([],1))
        # The small table fixture has no native SQL cursor. Supply its canonical
        # stream at the adapter boundary; native streaming is tested separately.
        canonical=copy.deepcopy(self.table.rows)
        with patch.object(self.store,'_index_records',side_effect=lambda keys:iter(canonical)), \
                patch.object(self.store,'snapshot',side_effect=AssertionError('No evidence snapshot for browsing')), \
                patch.object(self.store,'for_epochs',side_effect=AssertionError('No full provenance hydration')):
            actual=self.service._filter_rows(rows,{'tag':'QC'})
            self.assertEqual({row['epoch_uuid'] for row in actual},set(self.ids))
            self.assertEqual(self.store.summary(rows),expected_summary)
            catalog=TagPredicates(self.service).catalog_fields(self.ids)
            self.assertEqual([field for field in catalog if field['id'] in SHARED_FIELDS],
                [field for field in expected_catalog if field['id'] in SHARED_FIELDS])
        self.addCleanup(self.store._shared_tag_index.close)


if __name__=='__main__':unittest.main()
