"""Prepared Overview HTTP equivalence; recovery capture is a bounded test port."""
import contextlib
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch
import test_workspace_slow_read_memos as fixtures
from disco.workbench.recipes import checksum


class PreparedOverviewTests(fixtures.MemoFixture):
    def setUp(self):
        super().setUp();fixtures.ProtocolContextFastPathTests.publish(self)
        owner=self
        class Capture:
            lost=False
            history={}
            def snapshot(self):
                return {'curation':copy.deepcopy(owner.case.curation.rows),
                        'shared_annotation':copy.deepcopy(owner.fixture.records.rows),
                        'protocol_binding':copy.deepcopy(owner.case.explorer_history.Binding.rows)}
            def token(self):
                snapshot=self.snapshot();token=checksum(json.loads(json.dumps(snapshot,default=str)));self.history[token]=snapshot;return token
            @contextlib.contextmanager
            def capture(self,previous=None,**kwargs):
                watermark=self.token();current=self.history[watermark];prior=self.history.get(previous)
                names={'curation':['project_uuid','protocol_uuid','epoch_uuid'],
                       'shared_annotation':['project_uuid','target_kind','target_uuid','profile_uuid'],
                       'protocol_binding':['project_uuid','protocol_uuid']}
                keys={}
                for table,fields in names.items():
                    before={tuple(row[key] for key in fields):row for row in (prior or {}).get(table,[])}
                    after={tuple(row[key] for key in fields):row for row in current[table]}
                    keys[table]=[key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)]
                yield SimpleNamespace(complete=prior is not None and not self.lost,keys=keys,
                    primary_keys=names,watermark=watermark,verify=lambda:None)
        self.capture=Capture();self.service._recovery_tracker=self.capture
        self.prepare=self.app.extensions['prepare_overview_publication']
        self.addCleanup(self.close_projection)

    def close_projection(self):
        state=self.app.extensions['prepared_overview']
        self.app.extensions['close_overview_publication']()

    def reference(self,path):
        del self.service._recovery_tracker
        try:return self.get(path)
        finally:self.service._recovery_tracker=self.capture

    def test_first_page_matches_canonical_after_explicit_preparation(self):
        path='/api/overview?cells_limit=1'
        self.assertEqual(self.client.get(path).status_code,202)
        expected=self.reference(path)
        receipt=self.prepare();self.assertEqual(receipt['status'],'ready')
        self.assertEqual(self.get(path),expected)
        path=f'/api/protocols/{self.protocol}/overview?cells_limit=1'
        self.assertEqual(self.get(path),self.reference(path))

    def test_first_read_after_curation_and_shared_tags_is_exact_without_cohort_reads(self):
        self.prepare();path='/api/overview?cells_limit=1'
        self.save_curation(review_state='approved')
        self.fixture.edit('epoch',self.ids[0],['red'])
        expected=self.reference(path)
        with patch('workspace_api.summarize_cell_membership',side_effect=AssertionError('whole cell summary')):
            self.assertEqual(self.get(path),expected)

    def test_bound_prepared_protocol_preserves_the_complete_binding_dto(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        path=f'/api/protocols/{self.protocol}/overview?cells_limit=1'
        expected=self.reference(path);self.prepare()
        self.assertEqual(self.get(path),expected)

    def test_membership_delta_has_immediate_counts_then_exact_background_duration(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare()
        delta=history.create_delta(root['revision_uuid'],{},[self.ids[0]],'fixture',name='Removed one')
        history.bind(delta['revision_uuid'],self.protocol,1,'fixture',{},2)
        path=f'/api/protocols/{self.protocol}/overview?cells_limit=1'
        jobs=[]
        with patch.object(self.app.extensions['overview_durations'],'submit',side_effect=lambda *args,**kwargs:jobs.append(args)), \
             patch('disco.decisions.explorer.MemberView.__iter__',side_effect=AssertionError('Full membership hydration')):
            response=self.client.get(path);self.assertEqual(response.status_code,200)
            pending=response.get_json();old_etag=response.headers['ETag']
        expected=self.reference(path)
        self.assertEqual(pending['counts']['epochs'],expected['counts']['epochs'])
        self.assertEqual(pending['counts']['included'],expected['counts']['included'])
        self.assertIsNone(pending['counts']['duration_seconds'])
        self.assertEqual(pending['counts']['duration_status'],'pending')
        self.assertEqual(len(jobs),1)
        from disco.navigation.overview_durations import fold_duration
        order,rows,publish=jobs[0];publish(fold_duration(order,rows))
        response=self.client.get(path,headers={'If-None-Match':old_etag})
        self.assertEqual(response.status_code,200)
        self.assertNotEqual(response.headers['ETag'],old_etag)
        self.assertEqual(response.get_json(),expected)

    def test_unexplained_binding_change_cannot_use_a_matching_recovery_watermark(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare();watermark=self.capture.token()
        history.Binding.rows[0]['version']+=1
        with patch.object(self.capture,'token',return_value=watermark):
            response=self.client.get('/api/overview?cells_limit=1')
        self.assertEqual(response.status_code,202)
        self.assertNotIn('counts',response.get_json())

    def test_duration_failure_is_explicit_and_does_not_hide_counts(self):
        self.prepare();model=self.app.extensions['prepared_overview']['model']
        self.assertTrue(model.fail_duration(self.protocol,model.duration_versions[self.protocol]))
        result=self.get(f'/api/protocols/{self.protocol}/overview?cells_limit=1')
        self.assertEqual(result['preparation'],{'status':'failed','resource':'overview','reason':'duration_failed'})
        self.assertEqual(result['counts']['epochs'],len(self.ids))
        self.assertEqual(result['counts']['duration_status'],'failed')
        self.assertIsNone(result['counts']['duration_seconds'])

    def test_incomplete_feed_returns_preparing_instead_of_rebuilding(self):
        self.prepare();self.capture.lost=True;self.save_curation(included=False)
        with patch('workspace_api.summarize_cell_membership',side_effect=AssertionError('hidden rebuild')):
            response=self.client.get('/api/overview?cells_limit=1')
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.get_json()['preparation']['resource'],'overview')
