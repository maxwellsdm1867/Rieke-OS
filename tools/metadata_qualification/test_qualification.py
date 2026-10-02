"""Focused fixture verification. No preserved private corpus reads or live writes."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from checks import qualify
from native import NativeAdapter
from service_checks import assert_registry, assert_summary_state, assert_empty_branches, cursor_refusal, assert_generation_compatible
from storage import physical_assets, sqlite_components, normalized, incremental, growth, HighWater
from timing import paired
from truth import Truth, equal, matches, canonical, validation_rejections
from replay_gate import verify, inventory


class NativeTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth=Truth();cls.temp=tempfile.TemporaryDirectory()
        cls.adapter=NativeAdapter(Path(cls.temp.name)/'native.sqlite',cls.truth.fixture())
    @classmethod
    def tearDownClass(cls):cls.adapter.close();cls.temp.cleanup()

    def test_complete_membership_dto_cursor_detail_and_facets(self):
        receipt=qualify(self.adapter,self.truth)
        self.assertGreater(receipt['fields'],140)
        self.assertGreater(receipt['checks'],1000)
        self.assertFalse(receipt['real_million'])

    def test_native_eligible_value_projection_matches_explicit_frozen_truth(self):
        actual=dict(self.adapter.index.values(fields=self.truth.fields).items())
        self.assertEqual(canonical(actual),canonical(self.truth.values))
        self.assertGreater(len(self.adapter.fields),140)

    def test_exact_validation_errors_and_browser_integer_limit(self):
        cases=validation_rejections()
        for predicate,error in cases:
            with self.subTest(predicate=predicate),self.assertRaises(ValueError) as caught:
                self.adapter.membership(predicate)
            self.assertEqual(str(caught.exception),error)

    def test_generation_project_corruption_and_failed_publication(self):
        from workspace_disk_index import DiskMetadataIndex
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fault.sqlite'; data=self.truth.fixture()
            index=DiskMetadataIndex.build(path,data['rows'],data['details'],data['sources'],'old','project')
            with self.assertRaises(ValueError):DiskMetadataIndex.open(path,'new','project')
            with self.assertRaises(ValueError):DiskMetadataIndex.open(path,'old','foreign')
            bad=copy.deepcopy(data['details']);bad[self.truth.ids[0]]['parameters']['bad']=float('nan')
            with self.assertRaises(ValueError):DiskMetadataIndex.build(path,data['rows'],bad,data['sources'],'new','project')
            self.assertEqual(len(index.rows()),12)
            with sqlite3.connect(path) as con:con.execute("UPDATE epochs SET row_json='{}' WHERE epoch_id=1")
            with self.assertRaises(ValueError):index.rows()
            with self.assertRaises(ValueError):DiskMetadataIndex.open(path,'old','project')
            index.close()

    def test_excluded_source_has_no_truth_membership_and_labels_do_not_define_identity(self):
        permitted=self.truth.membership(eligible_sources=['source-A'])
        self.assertEqual(len(permitted),8)
        self.assertEqual({self.truth.rows[i]['source_sha256'] for i in permitted},{'source-A'})
        self.assertEqual(len({r['cell_label'] for r in self.truth.rows.values()}),1)
        self.assertEqual(len({r['cell_uuid'] for r in self.truth.rows.values()}),3)
        self.assertEqual(self.truth.membership(scope={'block':'empty-block'}),[])

    def test_oracle_distinguishes_recorded_null_missing_unloaded_detail_and_large_values(self):
        self.assertFalse(equal(True,1));self.assertTrue(equal(1,1.0));self.assertTrue(equal(-0.0,0))
        self.assertFalse(equal([True],[1]));self.assertFalse(equal(2**60,2**60+1))
        self.assertFalse(equal({'a':True},{'a':1}))
        self.assertTrue(matches({'field':'x','operator':'missing'},{}))
        self.assertFalse(matches({'field':'x','operator':'is_null'},{}))
        self.assertTrue(matches({'field':'x','operator':'exists'},{'x':None}))
        # Removing an eligible value is not evidence of unloaded detail.
        data=self.truth.fixture();first=self.truth.ids[0]
        self.assertIn('raw_reconstruction_bundle',data['details'][first])
        self.assertNotIn('raw_reconstruction_bundle',data['values'][first])

    def test_checks_detect_corrupt_dto_facet_and_cursor(self):
        for defect in ('rows','facets','cursor'):
            class Broken:
                fields=self.adapter.fields
                membership=self.adapter.membership
                detail=self.adapter.detail
                def preview(_,**request):
                    page=self.adapter.preview(**request)
                    if defect=='rows':page['rows']=[]
                    if defect=='facets':page['facets']={}
                    if defect=='cursor':page['cursor']=None
                    return page
            with self.subTest(defect=defect),self.assertRaises(AssertionError):qualify(Broken(),self.truth)

    def test_truth_seal_refuses_changed_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'truth.json';path.write_text('{}')
            path.with_suffix('.seal.json').write_text(json.dumps({'sha256':self.truth.sha256}))
            with self.assertRaisesRegex(ValueError,'seal'):Truth(path)


class ServiceSeamCheckerTests(unittest.TestCase):
    """Verify checker rejects bad adapters; no claim integrated service passed."""
    def setUp(self):self.generation=dict(metadata='m',typed='t',source='s',publication='p')
    def test_registry_checker_rejects_distribution_and_missing_fields(self):
        payload=dict(fields=[dict(id='new',types=['boolean'],operators=['eq'])],operators=['eq'],
                     generation=self.generation,source_scope={},summary_available=False)
        assert_registry(payload,['new'])
        with self.assertRaises(AssertionError):assert_registry(payload,['unseen'])
        payload['fields'][0]['choices']=[]
        with self.assertRaises(AssertionError):assert_registry(payload,['new'])
    def test_summary_states_reject_zero_imputation_stale_identity_and_unready_result(self):
        expected=dict(count=0,facets={})
        for status in ('pending','cancelled','stale','failed'):
            payload=dict(request_id='id',generation=self.generation,status=status)
            assert_summary_state(payload,'id',self.generation,status)
            payload['result']={'matched_count':0,'summaries':{}}
            with self.assertRaises(AssertionError):assert_summary_state(payload,'id',self.generation,status)
        payload=dict(request_id='id',generation=self.generation,status='ready',result=dict(matched_count=0,summaries={}))
        assert_summary_state(payload,'id',self.generation,'ready',expected)
        payload['result']['summaries']['missing']={'present_count':0}
        with self.assertRaises(AssertionError):assert_summary_state(payload,'id',self.generation,'ready',expected)
        with self.assertRaises(AssertionError):assert_summary_state(payload,'other',self.generation,'ready',expected)
    def test_context_witnesses_can_enrich_registry_without_hiding_true_staleness(self):
        contextual={**self.generation,'binding':{'protocol':'fixture','revision':'b'},
                    'annotation':{'scope':'cell','revision':'a'}}
        assert_generation_compatible(self.generation,contextual)
        admitted={**self.generation,'annotation':'registry-shared','binding':None}
        assert_generation_compatible(admitted,contextual)
        wrong={**contextual,'metadata':'new'}
        with self.assertRaises(AssertionError):assert_generation_compatible(self.generation,wrong)
        missing=dict(contextual);missing.pop('source')
        with self.assertRaises(AssertionError):assert_generation_compatible(self.generation,missing)
        # After admission, pending->ready must keep the full contextual token exactly.
        payload=dict(request_id='id',generation={**contextual,'annotation':{'scope':'cell','revision':'new'}},status='pending')
        with self.assertRaises(AssertionError):assert_summary_state(payload,'id',contextual,'pending')

    def test_cursor_refusal_checker_fails_adapter_that_accepts_stale_cursor(self):
        class Service:
            def explore_page(self,*args,**kwargs):return {'cursor':'opaque'}
        with self.assertRaises(AssertionError):cursor_refusal(Service(),{'all':[]},lambda:None)
    def test_empty_branch_checker_rejects_loss_or_wrong_parent(self):
        expected=Truth().fixture()['empty_branches'];assert_empty_branches(expected,expected)
        with self.assertRaises(AssertionError):assert_empty_branches([],expected)
        mutated=copy.deepcopy(expected);mutated[0]['group_uuid']='label'
        with self.assertRaises(AssertionError):assert_empty_branches(mutated,expected)


class StorageTests(unittest.TestCase):
    def test_physical_components_hardlink_dedup_and_highwater(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data.sqlite'
            with sqlite3.connect(path) as con:
                con.execute('CREATE TABLE value_dictionary(id INTEGER PRIMARY KEY,value TEXT)')
                con.executemany('INSERT INTO value_dictionary(value) VALUES(?)',[('a'*100,)]*12)
                con.execute('CREATE INDEX value_lookup ON value_dictionary(value)')
            alias=Path(folder)/'alias.sqlite';os.link(path,alias)
            assets=[dict(path=path,role='base',generation='one'),dict(path=alias,role='shared-reference',generation='one')]
            physical=physical_assets(assets)
            self.assertEqual(physical['total_file_bytes'],path.stat().st_size)
            component=sqlite_components(path)
            self.assertEqual({s['name']:s.get('rows') for s in component['schema']}['value_dictionary'],12)
            self.assertEqual(component['dbstat_used_page_bytes'],component['page_count']*component['page_size'])
            report=normalized(physical,12,24,base_bytes=path.stat().st_size,added_bytes=0)
            self.assertIsNone(report['raw_ratios'][0]['ratio'])
            self.assertTrue(report['raw_ratios'][1]['projected'])
            high=HighWater();self.assertEqual(high.receipt()['status'],'unrun')
            high.observe('steady',assets);self.assertEqual(high.receipt()['peak_file_bytes'],path.stat().st_size)
            self.assertEqual(high.receipt()['status'],'observed_lower_bound')
            with self.assertRaises(ValueError):sqlite_components(path,max_file_bytes=1)
    def test_incremental_and_controlled_growth_refuse_wrong_layout_or_synthetic(self):
        before=dict(layout='native-sidecar',generation='one',total_file_bytes=100)
        after=dict(layout='native-sidecar',generation='two',total_file_bytes=150)
        result=incremental(before,after,dict(epochs=5,fields=1))
        self.assertEqual(result['bytes_per_new_epochs'],10)
        self.assertIsNone(result['bytes_per_new_sources'])
        after['layout']='clone'
        with self.assertRaises(ValueError):incremental(before,after,{})
        points=[dict(layout='same',epochs=n,total_file_bytes=n*10,corpus_kind='real-lineage-replay',
                     seal_verified=True,lineage_receipt='sealed') for n in (2781,100000,1000000)]
        self.assertFalse(growth(points)['increasing_bytes_per_epoch'])
        points[-1]['corpus_kind']='synthetic'
        with self.assertRaises(ValueError):growth(points)
    def test_heavy_replay_gate_closed_and_stat_inventory_never_claims_seal(self):
        with self.assertRaisesRegex(ValueError,'serial'):verify('absent','absent','absent')
        status=inventory(['/tmp/does-not-exist-qualification-fixture'])
        self.assertFalse(status[0]['exists']);self.assertIn('unverified',status[0]['seal_status'])


class TimingTests(unittest.TestCase):
    def test_serial_pair_and_generation_fault_receipts(self):
        calls=[]
        def arm(label):
            def call():calls.append(label);return {'count':1}
            return call
        result=paired(arm('b'),arm('c'),{'count':1},lambda:'fixed',repeats=2)
        self.assertEqual(calls,['b','c','c','b']);self.assertEqual(result['status'],'complete')
        self.assertIsNone(result['arms']['baseline']['p95_ms'])
        generation=['old']
        def mutation():generation[0]='new';return {'count':1}
        failed=paired(mutation,lambda:{'count':1},{'count':1},lambda:generation[0],repeats=2)
        self.assertEqual(failed['status'],'incomplete');self.assertEqual(failed['arms']['baseline']['samples_ms'],[])
    def test_timeout_and_output_mismatch_are_incomplete(self):
        def timeout():raise TimeoutError('capped')
        result=paired(timeout,lambda:0,0,lambda:'same',repeats=2)
        self.assertEqual(result['status'],'incomplete');self.assertIsNone(result['arms']['baseline']['first_ms'])
        self.assertEqual(paired(lambda:1,lambda:2,1,lambda:'same',repeats=2)['status'],'incomplete')
        with self.assertRaises(ValueError):paired(lambda:1,lambda:1,1,lambda:'same',seconds=46)


if __name__=='__main__':unittest.main()
