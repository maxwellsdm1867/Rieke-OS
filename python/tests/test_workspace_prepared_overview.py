"""Prepared Overview HTTP equivalence; recovery capture is a bounded test port."""
import contextlib
import copy
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch
import test_workspace_slow_read_memos as fixtures
from disco.workbench.recipes import checksum
from disco.decisions.explorer import MemberView


class PreparedOverviewTests(fixtures.MemoFixture):
    @contextlib.contextmanager
    def no_search_member_hydration(self):
        previous=sys.getprofile()
        def check(frame,event,arg):
            if (event=='call' and frame.f_globals.get('__name__')=='workspace_service'
                    and frame.f_code.co_name in ('query_members','query_result')):
                raise AssertionError('Search hydrated full query membership')
        sys.setprofile(check)
        try:yield
        finally:sys.setprofile(previous)

    def test_first_uuid_search_labels_reuse_prepared_members_without_query_hydration(self):
        path='/api/search?q='+self.ids[0]
        with self.no_search_member_hydration():
            response=self.client.get(path)
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.get_json()['code'],'metadata_preparing')
            self.assertIn('Retry search',response.get_json()['error'])
            self.assertNotIn('results',response.get_json())
        self.prepare()
        with self.no_search_member_hydration(), \
             patch.object(MemberView,'__iter__',side_effect=AssertionError('full bound membership iteration')):
            result=self.get(path)
        epoch=next(item for item in result['results'] if item['kind']=='epoch')
        self.assertEqual(epoch['protocols'],[{'protocol_uuid':self.protocol,
            'name':self.service.protocols[self.protocol]['definition']['name']}])

    def test_uuid_search_tracks_membership_remove_and_restore_without_hydration(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare()
        delta=history.create_delta(root['revision_uuid'],{},[self.ids[0]],'fixture',name='Remove one')
        history.bind(delta['revision_uuid'],self.protocol,1,'fixture',{},2)
        path='/api/search?q='+self.ids[0]
        with self.no_search_member_hydration(), \
             patch.object(MemberView,'__iter__',side_effect=AssertionError('full bound membership')), \
             patch.object(self.app.extensions['overview_durations'],'submit'):
            self.assertEqual(self.get(path)['results'][0]['protocols'],[])
            history.bind(root['revision_uuid'],self.protocol,2,'fixture',{},2)
            self.assertEqual(self.get(path)['results'][0]['protocol_uuid'],self.protocol)

    def test_uuid_search_closing_binding_change_discards_prepared_labels(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare();model=self.app.extensions['prepared_overview']['model']
        lookup=model.protocols_for_epochs
        def changed(identities):
            result=lookup(identities);history.Binding.rows[0]['version']+=1;return result
        with patch.object(model,'protocols_for_epochs',side_effect=changed):
            response=self.client.get('/api/search?q='+self.ids[0])
        self.assertEqual(response.status_code,409)
        self.assertNotIn('results',response.get_json())

    def test_uuid_search_source_eligibility_change_requires_preparation_without_losing_registered_labels(self):
        self.prepare()
        self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}})
        path='/api/search?q='+self.ids[0]
        response=self.client.get(path)
        self.assertEqual(response.status_code,503)
        self.prepare()
        result=self.get(path)['results'][0]
        self.assertTrue(result['query_excluded'])
        self.assertEqual(result['protocol_uuid'],self.protocol)

    def test_uuid_search_invalid_publication_does_not_hide_another_unavailable_member(self):
        from workspace_service import freeze
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare()
        self.service.rows=freeze({key:row for key,row in self.service.rows.items() if key!=self.ids[1]})
        response=self.client.get('/api/search?q='+self.ids[0])
        self.assertEqual(response.status_code,503)
        self.assertNotIn('results',response.get_json())
        # An unsupported custom reader still executes the old exact oracle,
        # including rejection of an unavailable member outside the shown hit.
        original=self.service.query_result
        with patch.object(self.service,'query_result',side_effect=original):
            response=self.client.get('/api/search?q='+self.ids[0])
        self.assertEqual(response.status_code,400)
        self.assertIn('unavailable',response.get_json()['error'])

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

    def test_adversarial_duration_matches_both_canonical_http_totals(self):
        import uuid
        from pathlib import Path
        from disco.metadata.disk_index import DiskMetadataIndex
        third=str(uuid.uuid4());identities=[*self.ids,third]
        rows=copy.deepcopy(dict(self.service.rows));rows[third]=copy.deepcopy(rows[self.ids[0]])
        rows[third]['epoch_uuid']=third
        for identity,value in zip(identities,(1e16,1.,1.)):rows[identity]['duration_seconds']=value
        details={key:copy.deepcopy(self.service.details[key]) for key in self.ids}
        details[third]=copy.deepcopy(details[self.ids[0]])
        details[third]['metadata']['epoch']['uuid']=third
        protocols=copy.deepcopy(self.service.protocols)
        protocols[self.protocol]['result']['epochs']=[{'uuid':key,'metadata_hash':'b'*64} for key in identities]
        self.service.rows=rows;self.service.protocols=protocols
        self.service._fingerprints={**self.service._fingerprints,third:'b'*64}
        index=DiskMetadataIndex.build(Path(self.case.temp.name)/'adversarial-duration.sqlite',
            rows,details,self.service.sources,'adversarial-duration',self.service.project['project_uuid'])
        self.service.disk_index,self.service.details=index,index.details
        fixtures.ProtocolContextFastPathTests.publish(self)
        path=f'/api/protocols/{self.protocol}/overview?cells_limit=1'
        expected=self.reference(path);self.prepare()
        model=self.app.extensions['prepared_overview']['model']
        with patch.object(model,'retained_counts',wraps=model.retained_counts) as retained_reads:
            actual=self.get(path)
        retained_reads.assert_called_once_with(self.protocol)
        ordered=0
        for identity in identities:ordered+=rows[identity]['duration_seconds']
        retained=sum(rows[identity]['duration_seconds'] for identity in identities)
        self.assertEqual(expected['counts']['duration_seconds'],ordered)
        self.assertEqual(expected['total_counts']['duration_seconds'],retained)
        self.assertEqual(actual,expected)

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
             patch.object(MemberView,'__iter__',side_effect=AssertionError('Full membership hydration')):
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

    def test_undo_keeps_initial_recipe_duration_order_after_order_cache_eviction(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare();state=self.app.extensions['prepared_overview']
        original=state['model'].duration_orders[self.protocol]
        delta=history.create_delta(root['revision_uuid'],{},[self.ids[0]],'fixture',name='Removed one')
        history.bind(delta['revision_uuid'],self.protocol,1,'fixture',{},2)
        path=f'/api/protocols/{self.protocol}/overview?cells_limit=1';jobs=[]
        with patch.object(self.app.extensions['overview_durations'],'submit',side_effect=lambda *args,**kwargs:jobs.append(args)):
            self.get(path)
            state['duration_orders'].clear()  # Exact LRU eviction outcome after many intervening revisions.
            history.bind(root['revision_uuid'],self.protocol,2,'fixture',{},1)
            pending=self.get(path)
        self.assertEqual(pending['counts']['epochs'],len(self.ids))
        self.assertIs(jobs[-1][0],original)
        from disco.navigation.overview_durations import fold_duration
        order,rows,publish=jobs[-1];publish(fold_duration(order,rows))
        self.assertEqual(self.get(path),self.reference(path))

    def test_return_to_an_unprepared_full_recipe_refuses_to_guess_its_duration_order(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        delta=history.create_delta(root['revision_uuid'],{},[self.ids[0]],'fixture',name='Removed one')
        history.bind(delta['revision_uuid'],self.protocol,1,'fixture',{},2)
        self.prepare()
        history.bind(root['revision_uuid'],self.protocol,2,'fixture',{},1)
        response=self.client.get(f'/api/protocols/{self.protocol}/overview?cells_limit=1')
        self.assertEqual(response.status_code,202)
        self.assertNotIn('counts',response.get_json())
        self.assertEqual(self.prepare()['status'],'ready')
        self.assertEqual(self.get('/api/overview?cells_limit=1'),self.reference('/api/overview?cells_limit=1'))

    def test_failed_close_does_not_dispose_prepared_reads_or_duration_worker(self):
        import os
        import threading
        from unittest.mock import Mock
        from workspace_api import create_app
        self.service.config['connection']={'credential_provider':{'kind':'native-project'}}
        with patch.dict(os.environ,{'RIEKE_DESKTOP_MODE':'1','RIEKE_DESKTOP_FRONTEND':self.case.temp.name}):
            app=create_app(self.case.temp.name,self.case.temp.name,service=self.service,store=self.case.store,
                explorer_history=self.case.explorer_history,data_stores=self.case.data_stores,
                protocol_suggestions=self.case.protocol_suggestions,shared_annotations=self.shared)
        self.addCleanup(app.extensions['close_overview_publication'])
        self.addCleanup(app.extensions['close_trace_workers'])
        self.addCleanup(app.extensions['disco.navigation.prepared'].close)
        app.extensions['prepare_overview_publication']()
        scheduler=Mock();scheduler.flush.side_effect=RuntimeError('held recovery failure')
        app.extensions['backup_scheduler']=scheduler
        with patch.object(app.extensions['h5_inbox'],'start') as resumed, self.assertRaises(RuntimeError):
            app.extensions['desktop_stop_database']()
        resumed.assert_called_once()
        self.assertFalse(app.extensions['overview_durations'].closed)
        self.assertFalse(app.extensions['disco.navigation.prepared'].closed)
        response=app.test_client().get('/api/overview?cells_limit=1')
        self.assertEqual(response.status_code,200,response.get_json())
        completed=threading.Event();model=app.extensions['prepared_overview']['model']
        app.extensions['overview_durations'].submit(model.duration_orders[self.protocol],model.rows,
            lambda result:completed.set(),key=self.protocol)
        self.assertTrue(completed.wait(2))

    def test_same_revision_rebind_updates_version_without_recomputing_duration(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        root=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(root['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.prepare()
        history.bind(root['revision_uuid'],self.protocol,1,'fixture',{},2)
        with patch.object(self.app.extensions['overview_durations'],'submit',side_effect=AssertionError('Unchanged members need no fold')):
            result=self.get(f'/api/protocols/{self.protocol}/overview?cells_limit=1')
        self.assertEqual(result['binding']['version'],2)
        self.assertNotEqual(result['counts'].get('duration_status'),'pending')

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

    def test_inert_display_checkpoint_is_prepared_once_and_never_serialized_by_pages(self):
        with patch('disco.projects.presentation_cache.save_overview',return_value=True) as saved:
            self.prepare()
            self.assertEqual(saved.call_count,1)
            self.assertEqual(len(saved.call_args.args[1]['cells']),len(self.service.cells))
            with patch('disco.projects.presentation_cache.display_overview',side_effect=AssertionError('Full display on GET')):
                self.get('/api/overview?cells_limit=1')
                self.save_curation(review_state='approved')
                self.get('/api/overview?cells_limit=1')
            self.assertEqual(saved.call_count,1)
            self.prepare()
            self.assertEqual(saved.call_count,2)  # A changed approved count is part of the display allowlist.

    def test_display_checkpoint_failure_does_not_invalidate_prepared_data(self):
        with patch('disco.projects.presentation_cache.save_overview',return_value=False):
            self.assertEqual(self.prepare()['status'],'ready')
        self.assertEqual(self.get('/api/overview?cells_limit=1')['counts']['epochs'],len(self.ids))

    def test_incomplete_feed_returns_preparing_instead_of_rebuilding(self):
        self.prepare();self.capture.lost=True;self.save_curation(included=False)
        with patch('workspace_api.summarize_cell_membership',side_effect=AssertionError('hidden rebuild')):
            response=self.client.get('/api/overview?cells_limit=1')
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.get_json()['preparation']['resource'],'overview')
