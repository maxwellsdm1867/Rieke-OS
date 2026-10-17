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

    def test_unchanged_inputs_skip_the_metadata_rebuild_with_identical_revision(self):
        first=self.context()
        self.assertIsNotNone(self.reader.native_cache[self.protocol]['witness'])
        with patch.object(self.reader,'_metadata',side_effect=AssertionError('fast path rebuilt metadata')):
            second=self.context()
            detail=self.get(f'/api/epochs/{self.ids[0]}?protocol_uuid={self.protocol}')
        self.assertEqual(first,second)
        self.assertEqual(detail['curation']['revision'],0)

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

    def test_unmarshallable_inputs_disable_the_witness_but_keep_exact_reuse(self):
        class Mapping(dict):pass
        class Text(str):pass
        for value in (Mapping(a=1),Text('x')):
            self.service.rows[self.ids[0]]['custom']=value
            first=self.context()
            self.assertIsNone(self.reader.native_cache[self.protocol]['witness'])
            self.assertEqual(self.context(),first)
        self.service.rows[self.ids[0]]['custom']='plain'
        changed=self.context()
        self.assertNotEqual(changed['query_revision'],first['query_revision'])
        self.assertIsNotNone(self.reader.native_cache[self.protocol]['witness'])

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
