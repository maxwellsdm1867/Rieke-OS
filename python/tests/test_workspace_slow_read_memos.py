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


if __name__=='__main__':
    unittest.main()
