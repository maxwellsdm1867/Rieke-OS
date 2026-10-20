"""Generation-keyed read memos: exact equality, invalidation and fail-closed fences.

Uses the production StateGenerationAuthority class with only its two SQL leaf
reads replaced: schema attestation is counted and scope generations follow the
content of the transactional table doubles, as native triggers would.
"""
import contextlib
import copy
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from disco.metadata.disk_index import DiskMetadataIndex
from disco.navigation.tag_predicates import TagPredicates
from disco.workbench.recipes import checksum
from workspace_service import WorkspaceService
from workspace_state_generation import StateGenerationAuthority
import test_workspace_annotations as annotation_fixture


class MemoFixture(unittest.TestCase):
    def setUp(self):
        self.fixture=annotation_fixture.SharedAnnotationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service=self.fixture.service
        self.service.__class__=WorkspaceService
        self.case=self.fixture.case
        self.client=self.fixture.client
        self.app=self.fixture.app
        self.protocol=self.service.protocol_id
        self.ids=self.service.ids
        self.store=self.case.store
        self.shared=self.fixture.store
        self.index=DiskMetadataIndex.build(Path(self.case.temp.name)/'memos.sqlite',
            self.service.rows,self.service.details,self.service.sources,'memo-generation',self.service.project['project_uuid'])
        self.service.disk_index,self.service.details=self.index,self.index.details
        self.service.Event=self.case.events
        self.reader=self.app.extensions['protocol_state_reader']
        self.attestations=0
        self.closing_contract=None
        self.tracker=self.authority()

    def authority(self):
        owner=self
        project=self.service.project['project_uuid']
        tracker=StateGenerationAuthority(SimpleNamespace(_conn=object(),in_transaction=False),project)
        tracker.ready=True;tracker.reason=None

        def attest():
            owner.attestations+=1
            return 'memo-authority'
        def scope(kind,identity):
            if kind=='protocol_curation':
                rows=[row for row in owner.case.curation.rows if row['protocol_uuid']==identity]
            else:
                rows=[owner.fixture.records.rows,owner.fixture.profiles.rows]
            return 'scope-epoch',int(checksum(json.loads(json.dumps(rows,default=str)))[:12],16)
        tracker._attest_contract=attest
        tracker._scope=scope
        tracker.shared_changes=lambda token,limit=10000:None
        original=self.shared._index_records
        def records(keys):
            if keys is not None:
                yield from original(keys);return
            yield from sorted((row for row in self.fixture.records.to_dicts() if row['project_uuid']==project),
                key=lambda row:(row['target_kind'],row['target_uuid'],row['profile_uuid']))
        self.shared._index_records=records
        self.store.state_generation=tracker
        self.shared.state_generation=tracker
        self.service._explore_state_generation=tracker
        return tracker

    def save_curation(self, ids=None, **changes):
        ids=ids or self.ids[:1]
        current=self.store.read(self.protocol,ids,{key:self.service._fingerprints[key] for key in ids})
        return self.store.update(self.protocol,ids,changes,{key:current[key]['revision'] for key in ids},
            {key:self.service._fingerprints[key] for key in ids},'fixture')

    def get(self, path):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200,response.get_json())
        return response.get_json()

    @contextlib.contextmanager
    def unmemoized(self):
        """Reference result from the unchanged recomputation path."""
        self.tracker.ready=False
        try:yield
        finally:self.tracker.ready=True


class PredicateFieldMemoTests(MemoFixture):
    def fields(self):
        return self.get('/api/explore/predicate-fields')

    def reference(self):
        with self.unmemoized():
            memo=getattr(self.service,'_annotation_catalog_memo',None)
            self.service._annotation_catalog_memo=None
            try:return self.fields()
            finally:self.service._annotation_catalog_memo=memo

    def test_hit_is_exact_and_skips_annotation_reads(self):
        self.save_curation(tags_add=['first'])
        self.fixture.edit('cell',self.service.rows[self.ids[0]]['cell_uuid'],['shared'])
        cold=self.fields()
        with patch.object(TagPredicates,'catalog_fields',side_effect=AssertionError('memo hit rereads tags')), \
             patch.object(TagPredicates,'snapshot',side_effect=AssertionError('memo hit snapshots tags')):
            warm=self.fields()
            search=self.get('/api/search?q=first')
        self.assertEqual(warm,cold)
        self.assertEqual(warm,self.reference())
        self.assertTrue(any(item.get('field_id')==f'curation/{self.protocol}/tags' for item in search['results']))

    def test_each_scope_write_recomputes_only_its_fields_and_matches_reference(self):
        self.fields()
        calls=[]
        original=TagPredicates.catalog_fields
        def observed(instance,ids,only=None):
            calls.append(frozenset(only) if only is not None else None)
            return original(instance,ids,only=only)
        with patch.object(TagPredicates,'catalog_fields',observed):
            self.save_curation(tags_add=['protocol-write'])
            after_protocol=self.fields()
            self.fixture.edit('epoch',self.ids[1],['shared-write'])
            after_shared=self.fields()
        self.assertEqual(calls,[frozenset({f'curation/{self.protocol}/tags'}),
            frozenset(field for field in annotation_fixture_shared_fields())])
        self.assertEqual(after_shared,self.reference())
        protocol_field=next(field for field in after_protocol['fields'] if field['id']==f'curation/{self.protocol}/tags')
        self.assertIn('protocol-write',json.dumps(protocol_field))
        shared_field=next(field for field in after_shared['fields'] if field['id']=='annotations/epoch/tags')
        self.assertIn('shared-write',json.dumps(shared_field))

    def test_source_scope_publication_and_protocol_set_invalidate_all_fields(self):
        self.fields()
        calls=[]
        original=TagPredicates.catalog_fields
        def observed(instance,ids,only=None):
            calls.append(only);return original(instance,ids,only=only)
        with patch.object(TagPredicates,'catalog_fields',observed):
            self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}})
            excluded=self.fields()
            self.service.set_source_state_provider(lambda:{})
            self.fields()
            self.service._explore_publication='replaced-publication'
            self.fields()
            entry=self.service.protocols[self.protocol]
            entry['definition']={**entry['definition'],'name':'Renamed protocol'}
            renamed=self.fields()
        self.assertEqual(len(calls),4)
        self.assertTrue(all(len(only)==len([field for field in TagPredicates(self.service).definitions() if field.get('value_shape')!='tag_time']) for only in calls))
        self.assertEqual(excluded['source_scope']['excluded_source_revisions'],['a'*64])
        self.assertIn('Tags · Renamed protocol',[field['label'] for field in renamed['fields']])
        self.assertEqual(renamed,self.reference())

    def test_unavailable_authority_custom_provider_or_racing_build_never_store(self):
        self.tracker.ready=False
        self.fields();self.fields()
        self.assertIsNone(getattr(self.service,'_annotation_catalog_memo',None))
        self.tracker.ready=True
        provider=self.service.annotation_provider
        self.service.annotation_provider=lambda protocol,fingerprints:provider(protocol,fingerprints)
        self.fields()
        self.assertIsNone(getattr(self.service,'_annotation_catalog_memo',None))
        self.service.annotation_provider=provider
        original=TagPredicates.catalog_fields
        def racing(instance,ids,only=None):
            result=original(instance,ids,only=only)
            self.save_curation(tags_add=['during build'])
            return result
        with patch.object(TagPredicates,'catalog_fields',racing):
            self.fields()
        self.assertIsNone(getattr(self.service,'_annotation_catalog_memo',None))
        self.assertIn('during build',json.dumps(self.fields()))


def annotation_fixture_shared_fields():
    from disco.navigation.tag_predicates import SHARED_FIELDS
    return SHARED_FIELDS


class ProtocolContextFastPathTests(MemoFixture):
    def context(self):
        return self.reader.native_context(self.protocol)

    def publish(self):
        """Publish the fixture maps as production refresh does (deep-frozen)."""
        from workspace_service import publish_frozen
        service=self.service
        service.rows=publish_frozen(service.rows,rows=True)
        service.cells,service.protocols,service._fingerprints=(publish_frozen(service.cells),
            publish_frozen(service.protocols),publish_frozen(service._fingerprints))
        self.assertIsNotNone(service.rows)

    def test_unchanged_inputs_skip_the_metadata_rebuild_with_identical_revision(self):
        self.publish()
        first=self.context()
        entry=self.reader.native_cache[self.protocol]
        self.assertIsNotNone(entry['key'])
        self.assertNotIn('metadata',entry)  # Digest + member set only, never rows.
        with patch.object(self.reader,'_metadata',side_effect=AssertionError('fast path rebuilt metadata')):
            second=self.context()
            detail=self.get(f'/api/epochs/{self.ids[0]}?protocol_uuid={self.protocol}')
        self.assertEqual(first,second)
        self.assertEqual(detail['curation']['revision'],0)

    def test_published_maps_refuse_in_place_mutation_and_republish_advances_serial(self):
        from workspace_service import publication_serial
        self.publish()
        before=self.context()
        serial=publication_serial(self.service)
        row=self.service.rows[self.ids[0]]
        mutations=[lambda:row.__setitem__('duration_seconds',2),lambda:row.update(group_label='x'),
            lambda:self.service.rows.pop(self.ids[0]),lambda:self.service._fingerprints.__setitem__(self.ids[0],'e'*64),
            lambda:self.service.cells[row['cell_uuid']].__setitem__('label','x'),
            lambda:self.service.protocols[self.protocol]['result']['epochs'].reverse(),
            lambda:self.service.protocols[self.protocol]['result']['epochs'][0].__setitem__('uuid','x'),
            lambda:self.service.protocols[self.protocol]['definition'].setdefault('x',1),
            lambda:self.service.protocols.__ior__({})]
        for mutate in mutations:
            with self.assertRaises(TypeError):mutate()
        self.assertEqual(self.context(),before)
        self.assertEqual(publication_serial(self.service),serial)
        # Replacing a map (the only way to change content) advances the serial.
        changed={**self.service.rows,self.ids[0]:{**row,'duration_seconds':2.0}}
        from workspace_service import publish_frozen
        self.service.rows=publish_frozen(changed,rows=True)
        self.assertGreater(publication_serial(self.service),serial)
        with patch.object(self.reader,'_metadata',wraps=self.reader._metadata) as metadata:
            after=self.context()
        self.assertTrue(metadata.called)
        self.assertNotEqual(after['query_revision'],before['query_revision'])
        # Unfrozen replacement disables the key path entirely (exact contents).
        self.service.rows=dict(self.service.rows)
        self.assertIsNone(publication_serial(self.service))
        self.assertEqual(self.context()['query_revision'],after['query_revision'])
        self.assertIsNone(self.reader.native_cache[self.protocol]['key'])

    def test_query_view_is_one_shared_read_only_value_per_binding(self):
        self.publish()
        service=self.service
        with patch.object(WorkspaceService,'query_result',autospec=True,side_effect=WorkspaceService.query_result) as copies:
            first=service.query_view(self.protocol);second=service.query_view(self.protocol)
        self.assertIs(first,second);self.assertEqual(copies.call_count,0)
        self.assertEqual(first,service.query_result(self.protocol))
        with self.assertRaises(TypeError):first['epochs'].append({})
        history=self.case.explorer_history
        preview=service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        bound=service.query_view(self.protocol)
        self.assertEqual(bound['dataset_binding']['version'],1)
        self.assertEqual(bound,service.query_result(self.protocol))
        self.assertIs(service.query_view(self.protocol),bound)
        service.cells=service.cells  # Republish: a new serial never reuses the view.
        self.assertIsNot(service.query_view(self.protocol),bound)
        self.assertEqual(service.query_view(self.protocol),bound)

    def test_frozen_copies_are_plain_mutable_values(self):
        import copy as copying, json as encoding, pickle
        self.publish()
        row=self.service.rows[self.ids[0]]
        for value in (copying.deepcopy(row),copying.copy(row),dict(row),{**row},pickle.loads(pickle.dumps(row))):
            self.assertIs(type(value),dict);value['changed']=1
        self.assertEqual(encoding.loads(encoding.dumps(self.service.protocols[self.protocol]['result'])),
                         copying.deepcopy(self.service.protocols[self.protocol]['result']))

    def test_debug_verification_detects_content_differing_from_the_key(self):
        self.publish()
        self.context()
        entry=self.reader.native_cache[self.protocol]
        entry['digest']='tampered'
        with patch.dict('os.environ',{'DISCO_PROTOCOL_STATE_VERIFY':'1'}):
            with self.assertRaisesRegex(AssertionError,'differs'):self.context()

    def test_in_place_value_and_numeric_type_changes_take_the_exact_path(self):
        baseline=self.context()['query_revision']
        revisions={baseline}
        row=self.service.rows[self.ids[0]]
        self.assertEqual(row['duration_seconds'],1)
        for value in (1.0,True,0.0,-0.0):
            row['duration_seconds']=value
            calls=[]
            original=self.reader._metadata
            def observed(*args,**kwargs):
                calls.append(None);return original(*args,**kwargs)
            with patch.object(self.reader,'_metadata',observed):
                revision=self.context()['query_revision']
            self.assertTrue(calls,value)
            self.assertNotIn(revision,revisions,value)
            revisions.add(revision)
        self.service._fingerprints[self.ids[1]]='e'*64
        self.assertNotIn(self.context()['query_revision'],revisions)
        self.service.cells[self.service.rows[self.ids[0]]['cell_uuid']]['label']='changed in place'
        self.assertNotIn(self.context()['query_revision'],revisions)

    def test_racing_publication_prevents_admission_of_a_key_proof(self):
        self.publish()
        original=self.reader._metadata
        def republish(*args,**kwargs):
            result=original(*args,**kwargs)
            self.service._fingerprints=self.service._fingerprints  # Any assignment republishes.
            return result
        with patch.object(self.reader,'_metadata',republish):
            self.assertIsNone(self.context())
        self.assertNotIn(self.protocol,self.reader.native_cache)
        self.assertIsNotNone(self.context())

    def test_oversized_proof_uses_negative_memo_until_next_publication(self):
        self.publish()
        with patch('workspace_protocol_state.STATE_CACHE_BYTES',10):
            self.assertIsNone(self.context())
            self.assertIn(self.protocol,self.reader.native_rejected)
            with patch.object(self.reader,'_metadata',side_effect=AssertionError('futile admission retried')):
                self.assertIsNone(self.context())
            self.service.cells=self.service.cells  # Publish drops the memo.
            with patch.object(self.reader,'_metadata',wraps=self.reader._metadata) as metadata:
                self.assertIsNone(self.context())
            self.assertTrue(metadata.called)

    def test_witness_is_not_admitted_when_inputs_change_during_the_proof(self):
        original=self.reader._metadata
        calls=[]
        def changing(*args,**kwargs):
            result=original(*args,**kwargs)
            calls.append(None)
            if len(calls)==2:self.service.rows[self.ids[0]]['group_label']='changed during proof'
            return result
        with patch.object(self.reader,'_metadata',changing):
            self.assertIsNone(self.context())
        self.assertNotIn(self.protocol,self.reader.native_cache)
        self.assertIsNotNone(self.context())

    def test_curation_write_changes_revision_and_closing_fence_still_rejects(self):
        from disco.decisions.curation import RevisionConflict
        before=self.context()
        self.save_curation(tags_add=['moved'])
        after=self.context()
        self.assertNotEqual(before['query_revision'],after['query_revision'])
        table=type(self.case.curation)
        original=table.to_dicts
        def racing(relation):
            result=original(relation)
            if not self.case.curation.rows or self.case.curation.rows[-1]['epoch_uuid']!=self.ids[1]:
                self.case.curation.rows.append({'project_uuid':self.service.project['project_uuid'],
                    'protocol_uuid':self.protocol,'epoch_uuid':self.ids[1],'included':False,'tags':[],
                    'review_state':'unreviewed','revision':1,'metadata_fingerprint':self.service._fingerprints[self.ids[1]]})
            return result
        with patch.object(table,'to_dicts',racing):
            with self.assertRaises(RevisionConflict):
                self.reader.read_selected(self.protocol,[self.ids[0]])


class ResponseContractTests(MemoFixture):
    def test_read_routes_attest_once_at_each_end(self):
        paths=['/api/search?q=Cell','/api/explore/predicate-fields','/api/overview',
               f'/api/epochs/{self.ids[0]}?protocol_uuid={self.protocol}',f'/api/protocols/{self.protocol}',
               f'/api/protocols/{self.protocol}?projection=browse']
        for path in paths:
            self.get(path)
        for path in paths:
            before=self.attestations
            self.get(path)
            self.assertEqual(self.attestations-before,2,path)

    def test_every_get_route_holds_one_lazy_lease(self):
        paths=[f'/api/protocols/{self.protocol}/overview',f'/api/protocols/{self.protocol}/epochs?limit=5',
               '/api/tags',f'/api/protocols/{self.protocol}/tree?splits=cell',
               f'/api/protocols/{self.protocol}/tree-fields','/api/metadata/fields','/api/metadata/status']
        for path in paths:
            self.get(path)
        for path in paths:
            before=self.attestations
            self.get(path)
            self.assertLessEqual(self.attestations-before,2,path)
        # Routes that never read a native token never attest.
        before=self.attestations
        self.get('/api/metadata/fields')
        self.assertEqual(self.attestations,before)

    def test_closing_attestation_change_discards_the_response(self):
        self.get(f'/api/epochs/{self.ids[0]}?protocol_uuid={self.protocol}')
        state={'calls':0}
        def changing():
            state['calls']+=1
            return 'memo-authority' if state['calls']==1 else 'changed-authority'
        self.tracker._attest_contract=changing
        response=self.client.get(f'/api/epochs/{self.ids[0]}?protocol_uuid={self.protocol}')
        self.assertEqual(response.status_code,400)
        self.assertIn('contract changed',response.get_json()['error'])


class TypedReadinessErrorTests(MemoFixture):
    def test_not_ready_is_retryable_503_and_never_served_from_previous_state(self):
        self.get('/api/overview')
        self.service._loaded=False
        for path in ('/api/overview','/api/metadata/fields',f'/api/protocols/{self.protocol}'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,503,path)
            body=response.get_json()
            self.assertEqual(body['code'],'workspace_not_ready');self.assertTrue(body['retryable'])

    def test_lock_busy_is_retryable_409(self):
        from workspace_service import LockBusy
        with patch.object(self.service,'metadata_fields',side_effect=LockBusy('Another operation is running')):
            response=self.client.get('/api/metadata/fields')
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.get_json()['code'],'lock_busy')

    def test_failed_route_refresh_stays_not_ready_and_uses_manager_recovery(self):
        recovered=[]
        with patch.object(self.service,'refresh',side_effect=ValueError('Source recording changed')), \
             patch.object(self.service,'manager_recovery',side_effect=lambda error:recovered.append(str(error))):
            self.service._loaded=False
            response=self.client.get(f'/api/protocols/{self.protocol}/masks/export')
        self.assertEqual(response.status_code,400)
        self.assertEqual(recovered,['Source recording changed'])
        self.assertEqual(self.client.get('/api/overview').status_code,503)


class RouteRefreshScopingTests(MemoFixture):
    def publish(self):
        ProtocolContextFastPathTests.publish(self)

    def test_approve_verifies_sources_without_republishing_and_reads_stay_warm(self):
        from workspace_service import publication_serial
        self.publish()
        # The fixture authority cannot open SQL transactions; use the legacy
        # mutation path (the route preflight under test is identical).
        self.tracker.ready=False
        page=self.get(self.case.base+'/epochs?limit=1')
        view=self.service.query_view(self.protocol)
        rows,serial=self.service.rows,publication_serial(self.service)
        current=self.store.read(self.protocol,self.ids[:1],{self.ids[0]:self.service._fingerprints[self.ids[0]]})[self.ids[0]]['revision']
        verified=[]
        with patch.object(self.service,'verify_sources',side_effect=lambda:verified.append(1) or True), \
             patch.object(self.service,'refresh',side_effect=AssertionError('approve must not run a full refresh')):
            response=self.client.post(self.case.base+'/curation',json={'epoch_uuids':self.ids[:1],
                'query_revision':page['query_revision'],'changes':{'review_state':'approved'},
                'expected_revisions':{self.ids[0]:current}},headers=self.case.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(verified,[1])
        self.assertIs(self.service.rows,rows);self.assertEqual(publication_serial(self.service),serial)
        self.assertIs(self.service.query_view(self.protocol),view)  # Identity-keyed caches stay warm.

    def test_unchanged_check_for_updates_persists_no_revision(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        revisions=len(history.Revision.rows)
        with patch.object(self.service,'refresh',return_value={}), \
             patch.object(self.service,'explore_preview',wraps=self.service.explore_preview) as previews:
            response=self.client.post(self.case.base+'/refresh',json={'filters':{}},headers=self.case.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        body=response.get_json()
        self.assertIsNone(body['candidate_revision_uuid'])
        self.assertEqual(body['diff_counts'],{'added':0,'removed':0,'changed':0})
        self.assertEqual(len(history.Revision.rows),revisions)
        self.assertEqual(previews.call_count,1)
        self.assertFalse(previews.call_args.kwargs.get('include_tree',True))


class NavigationScopeCacheTests(MemoFixture):
    def setUp(self):
        super().setUp()
        ProtocolContextFastPathTests.publish(self)
        from disco.navigation.tree_pages import TreePages
        self.pager=TreePages(self.service)

    def builds(self):
        from disco.navigation.tree_pages import TreePages
        return patch.object(TreePages,'_build_scope',autospec=True,side_effect=TreePages._build_scope)

    def test_pages_at_every_depth_anchor_and_selection_share_one_scope(self):
        body={'protocol_uuid':self.protocol,'splits':'cell,parameters/example'}
        with self.builds() as builds:
            root=self.pager.page(body)
            branch=root['branches'][0]
            child=self.pager.page({**body,'path':branch['path'],'revision':root['revision']})
            self.pager.page({**body,'anchor_uuid':self.ids[0]})
            chosen=self.pager.selection({**body,'path':branch['path'],'revision':root['revision']},branch['count'])
        self.assertEqual(builds.call_count,1)
        self.assertEqual(len(chosen['epoch_uuids']),branch['count'])
        self.assertEqual(child['revision'],root['revision'])

    def test_frozen_hits_compare_no_fingerprint_dictionaries(self):
        from workspace_service import FrozenDict
        body={'splits':'cell,parameters/example'}
        self.pager.page(body)
        compared=[]
        original=FrozenDict.__eq__
        def eq(left,right):
            if left is self.service._fingerprints or right is self.service._fingerprints:compared.append(1)
            return original(left,right)
        with patch.object(FrozenDict,'__eq__',eq),patch.object(FrozenDict,'__ne__',lambda a,b:not eq(a,b)), \
             self.builds() as builds:
            self.pager.page(body)
        self.assertEqual((builds.call_count,compared),(0,[]))

    def test_tag_filtered_scope_is_cached_under_its_annotation_generation(self):
        body={'protocol_uuid':self.protocol,'splits':'cell','filters':{'tag':'chosen'}}
        with self.builds() as builds:
            first=self.pager.page(body);self.pager.page(body)
        self.assertEqual(builds.call_count,1)
        self.fixture.edit('epoch',self.ids[0],['chosen'])
        with self.builds() as builds:
            changed=self.pager.page(body)
        self.assertEqual(builds.call_count,1)
        self.assertEqual((first['count'],changed['count']),(0,1))
        self.assertNotEqual(first['revision'],changed['revision'])

    def test_structural_selection_reuses_page_groupings(self):
        import cProfile
        body={'protocol_uuid':self.protocol,'splits':'cell,date,block'}
        root=self.pager.page(body)
        branch=root['branches'][0]
        profile=cProfile.Profile()
        with profile:
            chosen=self.pager.selection({**body,'path':branch['path'],'revision':root['revision']},branch['count'])
        keyed=sum(entry.callcount for entry in profile.getstats() if getattr(entry.code,'co_name','')=='value_key')
        self.assertEqual(len(chosen['epoch_uuids']),branch['count'])
        # Only the branch's own two descendant levels are grouped, never the scope.
        self.assertLessEqual(keyed,2*branch['count'])
        self.assertLess(branch['count'],root['count'])

    def test_frozen_epoch_page_hits_compare_no_fingerprints(self):
        from workspace_service import FrozenDict
        path=f'{self.case.base}/epochs?limit=5'
        self.get(path)
        visits=[]
        original=FrozenDict.get
        def get(mapping,*args):
            if mapping is self.service._fingerprints:visits.append(1)
            return original(mapping,*args)
        with patch.object(FrozenDict,'get',get):
            self.service._epoch_page_identities(self.protocol)
        self.assertEqual(visits,[])

    def test_frozen_epoch_page_cache_keeps_only_identities_and_reads_no_recipe(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        self.service._epoch_page_cache=None
        self.service.query_view(self.protocol)  # The shared view's own one-time binding read.
        first=self.service._epoch_page_identities(self.protocol)
        entry=next(iter(self.service._epoch_page_cache[1].values()))
        self.assertIsNone(entry[0]);self.assertIsNone(entry[3])
        with patch.object(self.service,'binding',side_effect=AssertionError('page read the binding recipe')):
            self.assertEqual(self.service._epoch_page_identities(self.protocol),first)

    def test_unfrozen_read_model_never_caches_annotation_scopes(self):
        self.service.rows=dict(self.service.rows)
        body={'protocol_uuid':self.protocol,'splits':'cell','filters':{'tag':'chosen'}}
        with self.builds() as builds:
            self.pager.page(body);self.pager.page(body)
        self.assertEqual(builds.call_count,2)


class OverviewMemoTests(MemoFixture):
    def overview(self):
        return self.get('/api/overview')

    def rebuilt(self):
        self.app.extensions['overview_memo'].clear()
        return self.overview()

    def test_hit_is_exact_live_lists_stay_fresh_and_cache_file_is_not_rewritten(self):
        self.save_curation(tags_add=['x'],review_state='approved')
        self.fixture.edit('epoch',self.ids[0],['project-tag'])
        with patch('disco.projects.presentation_cache.save_overview',return_value=True) as save:
            first=self.overview()
            with patch.object(self.reader,'native_context',side_effect=AssertionError('hit reran protocol proofs')):
                second=self.overview()
            self.assertEqual(save.call_count,1)
            self.assertEqual(second,first)
            self.assertEqual(second,self.rebuilt())
            self.assertEqual(save.call_count,1)
            self.case.events.insert1({'event_uuid':'00000000-0000-4000-8000-000000000001',
                'project_uuid':self.service.project['project_uuid'],'occurred_at':dt.datetime(2099,1,1),
                'actor':'fixture','action':'fixture.event','payload':{}})
            live=self.overview()
            self.assertEqual(live['events'][0]['action'],'fixture.event')
            self.assertEqual(save.call_count,2)

    def test_every_generation_input_invalidates(self):
        self.overview()
        memo=self.app.extensions['overview_memo']
        def changed(mutate):
            key=memo.get('key')
            mutate()
            payload=self.overview()
            self.assertNotEqual(memo.get('key'),key)
            self.assertEqual(payload,self.rebuilt())
            return payload
        changed(lambda:self.save_curation(review_state='approved'))
        tagged=changed(lambda:self.fixture.edit('cell',self.service.rows[self.ids[0]]['cell_uuid'],['cell-tag']))
        self.assertTrue(tagged['annotation_summary']['tags'])
        changed(lambda:self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}}))
        changed(lambda:self.service.cells[self.service.rows[self.ids[0]]['cell_uuid']].update(label='Renamed cell'))
        changed(lambda:setattr(self.service,'_explore_publication','next-publication'))
        with patch.object(self.store,'export_signature',return_value=('export',)):
            # Patched readers are outside the native contract: no memo key.
            self.overview()
            self.assertIsNone(self.app.extensions['overview_memo_witness']())

    def test_change_between_opening_and_closing_witness_rejects(self):
        self.overview()
        original=self.service.events
        def racing(limit=100):
            self.save_curation(review_state='approved')
            return original(limit)
        with patch.object(self.service,'events',racing):
            response=self.client.get('/api/overview')
        self.assertEqual(response.status_code,409)


class IncrementalOverviewTests(MemoFixture):
    """Frozen publications assemble the overview from separately keyed parts."""
    def setUp(self):
        super().setUp()
        import uuid as uuidlib
        from workspace_service import publish_frozen
        other=str(uuidlib.uuid4())
        entry=copy.deepcopy(self.service.protocols[self.protocol])
        entry['definition'].update(protocol_uuid=other,name='Second protocol')
        entry['result'].update(protocol_uuid=other,epochs=entry['result']['epochs'][:1])
        self.other=other
        self.service.protocols={**self.service.protocols,other:entry}
        ProtocolContextFastPathTests.publish(self)
        self.parts=self.app.extensions['overview_parts']

    def reference(self):
        """The full (non-incremental) overview for the same state."""
        with patch.dict(self.app.extensions,{}),patch('workspace_service.publication_serial',return_value=None):
            self.app.extensions['overview_memo'].clear()
            return self.get('/api/overview')

    def test_incremental_overview_matches_the_full_build_after_each_write(self):
        first=self.get('/api/overview')
        self.assertIn('base',self.parts)
        self.assertEqual(first,self.reference())
        self.save_curation(tags_add=['x'],review_state='approved')
        self.assertEqual(self.get('/api/overview'),self.reference())
        self.fixture.edit('epoch',self.ids[0],['project-tag'])
        tagged=self.get('/api/overview')
        self.assertEqual(tagged,self.reference())
        self.assertTrue(tagged['annotation_summary']['tags'])
        self.fixture.edit('cell',self.service.rows[self.ids[1]]['cell_uuid'],['cell-tag'])
        self.assertEqual(self.get('/api/overview'),self.reference())

    def test_curation_write_recomputes_only_that_protocol(self):
        self.get('/api/overview')
        base=self.parts['base'];other=self.parts['protocols'][self.other]
        before=self.parts['protocols'][self.protocol]
        self.save_curation(review_state='approved')
        self.get('/api/overview')
        self.assertIs(self.parts['base'],base)
        self.assertIs(self.parts['protocols'][self.other],other)
        self.assertIsNot(self.parts['protocols'][self.protocol],before)

    def test_shared_tag_write_recomputes_only_tag_counts(self):
        self.get('/api/overview')
        kept={key:self.parts[key] for key in ('base','approval','exports')}
        protocols=dict(self.parts['protocols']);tags=self.parts['tags']
        self.fixture.edit('epoch',self.ids[0],['shared'])
        with patch.object(self.reader,'native_context',side_effect=AssertionError('protocol summaries recomputed')):
            payload=self.get('/api/overview')
        for key,value in kept.items():self.assertIs(self.parts[key],value,key)
        self.assertEqual(self.parts['protocols'],protocols)
        self.assertIsNot(self.parts['tags'],tags)
        self.assertEqual(payload['counts']['shared_tagged_epochs'],1)

    def test_summary_scope_token_skips_rereading_rows_and_targets_match_records(self):
        self.fixture.edit('epoch',self.ids[0],['shared'])
        self.fixture.edit('cell',self.service.rows[self.ids[1]]['cell_uuid'],['cell-tag'])
        reads=[]
        rows=lambda:reads.append(1) or list(self.service.rows.values())
        first=self.shared.summary(rows,scope_token=('test',1))
        second=self.shared.summary(rows,scope_token=('test',1))
        self.assertEqual((first,len(reads)),(second,1))
        self.assertEqual(self.shared.summary(rows,scope_token=('test',2)),first)
        self.assertEqual(len(reads),2)
        self.assertEqual(first,self.shared.summary(list(self.service.rows.values())))
        targets=self.shared.tagged_targets()
        self.assertEqual(targets['epoch'],{self.ids[0]})
        self.assertEqual(targets['cell'],{self.service.rows[self.ids[1]]['cell_uuid']})

    def test_cell_chips_reread_only_cells_named_by_the_change_feed(self):
        """A tag write re-reads only the written cell, never every cell's chips."""
        start=self.tracker.token();feed=[]
        original_edit=self.fixture.edit
        def edit(kind,target,*args,**kwargs):
            result=original_edit(kind,target,*args,**kwargs)
            feed.append((self.tracker.token(),{'target_kind':kind,'target_uuid':target,
                'profile_uuid':self.fixture.author,'last_generation':len(feed)+1,'deleted':0}))
            return result
        self.fixture.edit=edit
        lost={'value':False}
        def changes(after,limit=10000):
            if lost['value']:return None
            if after==start:position=0
            else:
                matches=[index for index,(token,_) in enumerate(feed) if token==after]
                if not matches:return None
                position=matches[-1]+1
            return [row for _,row in feed[position:]],self.tracker.token()
        self.tracker.shared_changes=changes
        reads=[]
        # read_targets itself is a contract-checked method; its first step,
        # the per-kind identity scope check, records which targets it reads.
        original_scope=self.shared._scope
        def scope(kind,ids):
            reads.append((kind,list(ids)))
            return original_scope(kind,ids)
        self.shared._scope=scope
        self.get('/api/overview')
        self.assertTrue(reads)
        cells=self.parts['tag_cells'][2]
        self.fixture.edit('epoch',self.ids[0],['epoch-only'])
        reads.clear()
        payload=self.get('/api/overview')
        self.assertEqual([kind for kind,_ in reads if kind=='cell'],[])
        for identity,value in self.parts['tag_cells'][2].items():self.assertIs(value,cells[identity])
        self.assertEqual(payload,self.reference())
        cell=self.service.rows[self.ids[1]]['cell_uuid']
        self.fixture.edit('cell',cell,['cell-only'])
        reads.clear()
        payload=self.get('/api/overview')
        self.assertEqual([entry for entry in reads if entry[0]=='cell'],[('cell',[cell])])
        self.assertEqual(payload,self.reference())
        self.assertEqual([chip['tag'] for chip in next(item for item in payload['cells'] if item['cell_uuid']==cell)['annotations']['cell_tags']],['cell-only'])
        lost['value']=True
        self.fixture.edit('cell',cell,remove=['cell-only'],revision=1)
        reads.clear()
        payload=self.get('/api/overview')
        self.assertEqual(sorted(sum((ids for kind,ids in reads if kind=='cell'),[])),sorted(self.parts['base'][1]['order']))
        self.assertEqual(payload,self.reference())

class SourcePreverificationRouteTests(MemoFixture):
    def test_trace_route_hashes_first_access_outside_the_database_lock(self):
        lock=self.app.extensions['workspace_db_lock']
        calls=[]
        def preverify(epoch):
            calls.append((epoch,lock._is_owned()))
            return 0
        with patch.object(self.service,'preverify_epoch_source',side_effect=preverify):
            self.client.get(f'/api/epochs/{self.ids[0]}/trace?stream_uuid={self.ids[0]}')
        self.assertEqual(calls,[(self.ids[0],False)])

    def test_prewarm_runs_in_a_background_thread(self):
        done=[]
        with patch.object(self.service,'preverify_sources',side_effect=lambda:done.append(1)):
            worker=self.app.extensions['prewarm_source_signatures']()
            worker.join(5)
        self.assertEqual(done,[1])


class LargeProtocolReadMemoTests(MemoFixture):
    """Per-request protocol reads reuse aggregates of the same frozen view."""
    def setUp(self):
        super().setUp()
        ProtocolContextFastPathTests.publish(self)

    def test_browse_and_cell_counts_reuse_aggregates_until_republication(self):
        first=self.service.protocol_browse(self.protocol)
        memo=self.service.__dict__['_browse_aggregates']
        self.assertEqual(self.service.protocol_browse(self.protocol),first)
        self.assertIs(self.service.__dict__['_browse_aggregates'],memo)
        self.service.cells=self.service.cells  # Republish.
        self.service.protocol_browse(self.protocol)
        self.assertIsNot(self.service.__dict__['_browse_aggregates'],memo)
        page=self.service.epoch_page(self.protocol,include_cells=True)
        counts=self.service.__dict__['_page_cell_counts']
        self.assertEqual(self.service.epoch_page(self.protocol,include_cells=True)['cells'],page['cells'])
        self.assertIs(self.service.__dict__['_page_cell_counts'],counts)

    def test_unchanged_overview_reuses_its_encoded_response(self):
        first=self.client.get('/api/overview')
        with patch('disco.projects.presentation_cache.display_overview',side_effect=AssertionError('re-encoded')):
            second=self.client.get('/api/overview')
        self.assertEqual(second.get_data(),first.get_data())
        self.save_curation(review_state='approved')
        third=self.client.get('/api/overview')
        self.assertNotEqual(third.get_data(),first.get_data())


class PredicateContractRefusalTests(MemoFixture):
    def bind(self, predicate, version):
        history=self.case.explorer_history
        preview=self.service.explore_preview(predicate,'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        recipe=history.get(created['revision_uuid'])['recipe']
        history._recipe_cache[created['revision_uuid']]={**recipe,'predicate_version':version}
        return created

    def test_old_contract_saved_selection_is_refused_not_reinterpreted(self):
        self.bind({'not':{'field':'cell type','operator':'missing'}},1)
        with patch.object(self.service,'refresh',return_value={}):
            response=self.client.post(self.case.base+'/refresh',json={'filters':{}},headers=self.case.headers)
        self.assertEqual(response.status_code,409,response.get_json())
        self.assertIn('Re-run its search',response.get_json()['error'])

    def test_suggestions_and_propagation_skip_old_contract_selections_visibly(self):
        affected={'not':{'field':'cell type','operator':'missing'}}
        created=self.bind(affected,1)
        suggestions=self.app.extensions.get('protocol_suggestions') or self.case.protocol_suggestions
        from disco.navigation.predicates import reinterpretation_required
        suggestions.reinterpretation_required=reinterpretation_required
        recipe=self.case.explorer_history._recipe_cache[created['revision_uuid']]
        with patch.object(self.service,'explore_preview',side_effect=AssertionError('re-ran an old-contract predicate')):
            result=suggestions.rerun([{'protocol_uuid':self.protocol,'recipe':recipe,'revision_uuid':created['revision_uuid'],
                'binding_version':1,'protocol_name':'Fixture'}],'a'*64,'fixture.h5','fixture')
            plan=self.case.data_stores.propagation_preview()
        self.assertEqual(result['counts']['skipped_count'],1)
        self.assertEqual(result['warnings'][0]['code'],'predicate_contract_rerun_required')
        self.assertIn("old 'missing' meaning",result['warnings'][0]['message'])
        self.assertEqual([item['protocol_uuid'] for item in plan['skipped_protocols']],[self.protocol])
        self.assertNotIn(self.protocol,[item['protocol_uuid'] for item in plan['protocols']])

    def test_export_snapshots_record_their_predicate_contract(self):
        from disco.workbench.recipes import capture_query
        self.bind({'all':[]},2)
        result=self.service.query_result(self.protocol)
        snapshot=capture_query(self.service.protocols[self.protocol]['definition'],result,'catalog.json')
        self.assertEqual(snapshot['predicate_contract_version'],2)

    def test_export_reuse_refuses_an_old_contract_frozen_predicate(self):
        record={'recipe':{'protocol_uuid':self.protocol,'options':{},'query_snapshot':{},
            'query':{'version':2,'kind':'source_predicate','predicate':{'field':'group label','operator':'ne','value':'x'}}}}
        with patch.object(self.store,'get_dataset_revision',return_value=record):
            refused=self.client.get('/api/exports/'+'0'*8+'-0000-4000-8000-000000000000/reuse')
        self.assertEqual(refused.status_code,409,refused.get_json())
        record['recipe']['query_snapshot']={'predicate_contract_version':2}
        with patch.object(self.store,'get_dataset_revision',return_value=record):
            allowed=self.client.get('/api/exports/'+'0'*8+'-0000-4000-8000-000000000000/reuse')
        self.assertNotEqual(allowed.status_code,409,allowed.get_json())

    def test_unaffected_old_contract_selection_still_checks_for_updates(self):
        self.bind({'all':[]},1)
        with patch.object(self.service,'refresh',return_value={}):
            response=self.client.post(self.case.base+'/refresh',json={'filters':{}},headers=self.case.headers)
        self.assertEqual(response.status_code,200,response.get_json())


class ProtocolStateV5Tests(MemoFixture):
    """Bound mains on a frozen publication: identity-based protocol-state-v5."""
    def setUp(self):
        super().setUp()
        ProtocolContextFastPathTests.publish(self)

    def bind(self):
        history=self.case.explorer_history
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        current=history.protocol_binding_header(self.protocol)
        history.bind(created['revision_uuid'],self.protocol,current['version'] if current else 0,'fixture',{},2)
        return created

    def test_unbound_stays_v4_and_bound_uses_v5_without_a_metadata_digest(self):
        unbound=self.reader.native_context(self.protocol)
        self.assertEqual(unbound['query_revision_contract'],'protocol-state-v4')
        self.bind()
        with patch.object(self.reader,'_metadata',side_effect=AssertionError('v5 computed a metadata digest')):
            bound=self.reader.native_context(self.protocol,self.ids[:1])
            again=self.reader.native_context(self.protocol,self.ids[:1])
        self.assertTrue(bound['query_revision'].startswith('protocol-state-v5:'))
        self.assertEqual(bound['query_revision_contract'],'protocol-state-v5')
        self.assertEqual(bound,again)
        page=self.get(self.case.base+'/epochs?limit=5')
        self.assertEqual(page['query_revision_contract'],'protocol-state-v5')
        self.assertEqual(page['query_revision'],bound['query_revision'])

    def test_v5_bare_revision_reads_no_members_and_prefers_revision_headers(self):
        from disco.decisions.explorer import ExplorerHistory
        created=self.bind()
        self.reader.native_cache.clear()
        bare=self.reader.native_context(self.protocol)
        entry=self.reader.native_cache[self.protocol]
        self.assertIsNone(entry['members'])  # A bare revision read never builds the member set.
        self.reader.native_context(self.protocol,self.ids[:1])
        self.assertIsNotNone(entry['members'])
        # A history with sealed revision headers/members is read through them.
        self.reader.native_cache.clear()
        seal=self.case.explorer_history._recipe_cache[created['revision_uuid']]['content_sha256']
        calls=[]
        with patch.object(ExplorerHistory,'header',create=True,side_effect=lambda revision:calls.append('header') or
                          {'content_sha256':seal,'source_revisions':['a'*64]}), \
             patch.object(ExplorerHistory,'members',create=True,side_effect=lambda revision:calls.append('members') or list(self.ids)):
            self.case.explorer_history._recipe_cache.clear()
            context=self.reader.native_context(self.protocol,self.ids[:1])
        self.assertEqual(calls,['header','members'])
        self.assertEqual(context['query_revision'],self.reader.native_context(self.protocol)['query_revision'])
        self.assertEqual(bare['query_revision'],context['query_revision'])

    def test_v5_changes_with_each_named_input(self):
        self.bind()
        seen={self.reader.native_context(self.protocol)['query_revision']}
        def changed(mutate):
            mutate()
            revision=self.reader.native_context(self.protocol)['query_revision']
            self.assertNotIn(revision,seen);seen.add(revision)
        changed(lambda:self.save_curation(review_state='approved'))       # curation generation
        changed(lambda:self.bind())                                        # binding revision/version/seal
        changed(lambda:setattr(self.service,'cells',self.service.cells))   # publication token
        changed(lambda:self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}}))  # source scope
        # Shared-tag writes do not retire the curation authority (as in v4).
        before=self.reader.native_context(self.protocol)['query_revision']
        self.fixture.edit('epoch',self.ids[0],['shared'])
        self.assertEqual(self.reader.native_context(self.protocol)['query_revision'],before)

    def test_v5_refuses_outside_members_and_locked_assertion_uses_the_key(self):
        self.bind()
        with self.assertRaisesRegex(ValueError,'outside'):
            self.reader.native_context(self.protocol,['00000000-0000-4000-8000-000000000123'])
        context=self.reader.native_context(self.protocol)
        from disco.decisions.curation import RevisionConflict
        self.tracker.assert_current_locked=lambda expected:None
        self.assertEqual(self.reader.assert_context_locked(self.protocol,context),context['query_revision'])
        self.service.cells=self.service.cells  # Republish: the key no longer matches.
        with self.assertRaises(RevisionConflict):
            self.reader.assert_context_locked(self.protocol,context)


if __name__=='__main__':
    unittest.main()
