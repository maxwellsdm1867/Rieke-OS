"""Exact global revision reuse: fresh inputs, cross-client writes, bounded memory."""
import copy
import contextlib
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from workspace_disk_index import DiskMetadataIndex
from workspace_protocol_state import ProtocolStateReader
from workspace_service import WorkspaceService
import test_workspace_annotations as annotation_fixture


class ProtocolStateTests(unittest.TestCase):
    def setUp(self):
        self.fixture=annotation_fixture.SharedAnnotationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service=self.fixture.service
        # Exercise the native read contract using disposable fixture state.
        # Subclass/overridden adapter policies intentionally use the full oracle.
        self.service.__class__=WorkspaceService
        self.case=self.fixture.case
        self.client=self.fixture.client
        self.protocol=self.service.protocol_id
        self.ids=self.service.ids
        self.store=self.case.store
        self.index=DiskMetadataIndex.build(Path(self.case.temp.name)/'revisions.sqlite',
            self.service.rows,self.service.details,self.service.sources,'revision-generation',self.service.project['project_uuid'])
        self.service.disk_index,self.service.details=self.index,self.index.details
        self.reader=self.fixture.app.extensions['protocol_state_reader']

    def native_generation(self):
        from workspace_state_generation import GenerationToken
        from workspace_recipes import checksum
        owner=self
        class FixtureAuthority:
            def __init__(self):self.locked_checks=0;self.disabled=False;self.in_transaction=False
            def token(self,protocol=None):
                return None if self.disabled or self.in_transaction else self._token(protocol)
            def _token(self,protocol=None):
                saved=checksum(owner.case.curation.rows)
                shared=checksum(json.dumps(owner.fixture.records.rows,sort_keys=True,default=str))
                return GenerationToken('test-native-authority',owner.service.project['project_uuid'],
                    'shared-epoch',int(shared[:12],16),protocol,'protocol-epoch' if protocol else None,
                    int(saved[:12],16) if protocol else None)
            def assert_current_locked(self,expected):
                from workspace_curation import RevisionConflict
                self.locked_checks+=1
                if self._token(expected.protocol_uuid)!=expected:raise RevisionConflict({'generation':'changed'})
        tracker=FixtureAuthority()
        self.store.state_generation=tracker
        return tracker

    def test_native_v3_cold_and_warm_skip_full_curation_oracle_and_agree_with_materialized_state(self):
        tracker=self.native_generation()
        self.save_curation(tags_add=['dense','second'])
        with patch.object(self.reader,'full_state',side_effect=AssertionError('Native pages do not hydrate all curation')):
            first=self.page();second=self.page()
        self.assertEqual(first,second)
        self.assertTrue(first['query_revision'].startswith('protocol-state-v3:'))
        self.assertEqual(first['query_revision_contract'],'protocol-state-v3')
        self.assertEqual(first['query_revision'],self.reader.materialized_state(self.protocol)[2])
        self.case.curation.rows[0]['tags']=['same-version change']
        with patch.object(self.reader,'full_state',side_effect=AssertionError('Generation change still reads selected rows only')):
            changed=self.page()
        self.assertNotEqual(first['query_revision'],changed['query_revision'])
        tracker.disabled=True
        fallback=self.page()
        self.assertFalse(fallback['query_revision'].startswith('protocol-state-v3:'))
        self.assertEqual(first['expected_binding_version'],0)
        self.assertEqual(fallback['expected_binding_version'],0)

    def test_native_page_fences_once_and_reads_selected_curation_once(self):
        tracker=self.native_generation()
        self.page()  # Establish the exact source proof before counting hot reads.
        self.case.curation.read_log.clear()
        with patch.object(tracker,'token',wraps=tracker.token) as token:
            page=self.page()
        self.assertEqual(token.call_count,2)
        self.assertEqual(len(self.case.curation.read_log),1)
        self.assertEqual(self.case.curation.read_log[0]['restrictions'][-1],[{'epoch_uuid':self.ids[0]}])
        self.assertEqual(page['expected_binding_version'],0)

    def test_native_response_scope_rejects_metadata_and_raw_saved_row_races(self):
        from workspace_curation import RevisionConflict
        self.native_generation()
        self.page()
        provider=self.service.curation_provider
        with self.assertRaises(RevisionConflict):
            with self.reader.native_read(self.protocol,provider=provider) as read:
                self.assertIsNotNone(read)
                read.selected(self.ids[:1])
                self.service._fingerprints[self.ids[0]]='e'*64
        with self.assertRaises(RevisionConflict):
            with self.reader.native_read(self.protocol,provider=provider) as read:
                read.selected(self.ids[:1])
                self.case.curation.rows.append({'project_uuid':self.service.project['project_uuid'],
                    'protocol_uuid':self.protocol,'epoch_uuid':self.ids[1],'included':True,
                    'tags':['external'],'review_state':'unreviewed','revision':1,
                    'metadata_fingerprint':self.service._fingerprints[self.ids[1]]})
        with self.assertRaisesRegex(RuntimeError,'closed'):read.selected(self.ids[:1])

    def test_native_response_scope_preserves_order_and_rejects_duplicate_or_foreign_ids(self):
        self.native_generation()
        with self.reader.native_read(self.protocol,provider=self.service.curation_provider) as read:
            self.assertEqual(list(read.selected(list(reversed(self.ids)))),list(reversed(self.ids)))
            with self.assertRaisesRegex(ValueError,'Duplicate'):read.selected([self.ids[0],self.ids[0]])
            with self.assertRaisesRegex(ValueError,'outside'):read.selected([str(uuid.uuid4())])

    def test_native_http_rejects_external_change_after_provenance_hydration(self):
        tracker=self.native_generation()
        self.page()
        code=self.reader.shared.for_epochs.__code__
        changed=[];previous=sys.getprofile()
        def observe(frame,event,arg):
            if event=='return' and frame.f_code is code and not changed:
                changed.append(True)
                self.case.curation.rows.append({'project_uuid':self.service.project['project_uuid'],
                    'protocol_uuid':self.protocol,'epoch_uuid':self.ids[1],'included':True,
                    'tags':['external write after visible provenance'],'review_state':'unreviewed','revision':1,
                    'metadata_fingerprint':self.service._fingerprints[self.ids[1]]})
        try:
            sys.setprofile(observe)
            with patch.object(tracker,'token',wraps=tracker.token) as token:
                response=self.client.get(self.case.base+'/epochs?limit=1')
        finally:sys.setprofile(previous)
        self.assertEqual(changed,[True])
        self.assertEqual(token.call_count,2)  # Native path, with final attestation.
        self.assertEqual(response.status_code,409,response.get_json())

    def test_native_cell_receipt_rejects_unbound_cell_metadata_change_during_projection(self):
        self.native_generation()
        self.page()
        code=self.service.epoch_page.__code__
        previous=sys.getprofile();changed=[]
        def observe(frame,event,arg):
            if event=='return' and frame.f_code is code and not changed:
                changed.append(True)
                self.service.cells[self.service.rows[self.ids[0]]['cell_uuid']]['label']='changed in place'
        try:
            sys.setprofile(observe)
            response=self.client.get(self.case.base+'/epochs?limit=1&include_cells=true')
        finally:sys.setprofile(previous)
        self.assertEqual(changed,[True])
        self.assertEqual(response.status_code,409,response.get_json())
        current=self.client.get(self.case.base+'/epochs?limit=1&include_cells=true')
        self.assertEqual(current.status_code,200,current.get_json())
        self.assertTrue(any(cell['label']=='changed in place' for cell in current.get_json()['cells']))

    def test_scoped_shared_index_rebuilds_after_refresh_provenance_metadata_or_final_sql_race(self):
        from types import SimpleNamespace
        from workspace_state_generation import StateGenerationAuthority
        from workspace_shared_tag_index import SharedTagIndex
        from workspace_recipes import checksum
        self.fixture.edit('epoch',self.ids[0],['keep'])
        original_rows=copy.deepcopy(self.fixture.records.rows)
        original_fingerprints=dict(self.service._fingerprints)
        for phase in ('refresh','membership','metadata','final_sql'):
            with self.subTest(phase=phase):
                self.fixture.records.rows[:]=copy.deepcopy(original_rows)
                self.service._fingerprints.clear();self.service._fingerprints.update(original_fingerprints)
                state={'fired':False,'fail_sql':False}
                tracker=StateGenerationAuthority(SimpleNamespace(_conn=object(),in_transaction=False),
                    self.service.project['project_uuid'])
                tracker.ready=True
                def contract():
                    if state['fail_sql']:
                        state['fail_sql']=False
                        raise RuntimeError('Injected final SQL attestation failure')
                    return 'fixture-authority:'+str(tracker._connection_epoch)
                tracker._contract=contract
                tracker._scope=lambda kind,identity: ('scope epoch',int(checksum(
                    json.dumps(self.fixture.records.rows if kind=='shared_annotations' else self.case.curation.rows,
                        sort_keys=True,default=str))[:12],16))
                self.store.state_generation=tracker;self.reader.shared.state_generation=tracker
                self.assertIsNotNone(self.reader.native_context(self.protocol),tracker.reason)
                def change():
                    if state['fired']:return
                    state['fired']=True
                    if phase in ('refresh','membership'):self.fixture.records.rows[0]['tags']=['changed']
                    elif phase=='metadata':self.service._fingerprints[self.ids[0]]='f'*64
                    else:state['fail_sql']=True
                def records(keys):
                    for row in copy.deepcopy(self.fixture.records.rows):
                        yield row
                        if phase=='refresh':change()
                index=SharedTagIndex(generation=tracker.token,changes=lambda previous:None,
                    records=records,validate=self.reader.shared._index_record_tags)
                self.addCleanup(index.close)
                self.reader.shared._shared_tag_index=index
                self.reader.shared._shared_tag_index_tracker=tracker
                code=(index.matching.__wrapped__.__code__ if phase=='membership'
                    else self.reader.shared.for_epochs.__code__)
                previous=sys.getprofile()
                def observe(frame,event,arg):
                    if phase!='refresh' and event=='return' and frame.f_code is code:change()
                try:
                    sys.setprofile(observe)
                    response=self.client.get(self.case.base+'/epochs?limit=1&tag=keep&include_cells=true')
                finally:sys.setprofile(previous)
                self.assertTrue(state['fired'])
                self.assertEqual(response.status_code,409,response.get_json())
                self.assertIsNone(index.connection)
                expected='changed' if phase in ('refresh','membership') else 'keep'
                response=self.client.get(self.case.base+'/epochs',query_string={'limit':1,'tag':expected,'include_cells':'true'})
                self.assertEqual(response.status_code,200,response.get_json())
                self.assertEqual(response.get_json()['total'],1)
                self.assertEqual(response.get_json()['epochs'][0]['epoch_uuid'],self.ids[0])
                self.assertEqual([item['tag'] for item in response.get_json()['epochs'][0]['annotations']['epoch_tags']],[expected])
                self.assertGreaterEqual(index.stats['full_builds'],2)
                index.close()

    def test_replaced_page_provider_uses_existing_public_service_read(self):
        self.native_generation()
        original=self.service.curation_provider
        with patch.object(self.service,'curation_provider',wraps=original) as provider:
            self.page()
        provider.assert_called_once()

    def test_epoch_page_cell_receipt_covers_full_filtered_membership_in_native_and_fallback(self):
        tracker=self.native_generation()
        cell=self.service.rows[self.ids[0]]['cell_uuid']
        self.fixture.edit('cell',cell,['filtered cell'])
        for disabled in (False,True):
            tracker.disabled=disabled
            for filters in ({},{'cell_uuid':cell},{'tag':'filtered cell'}):
                summary=self.client.get(self.case.base,query_string=filters).get_json()
                response=self.client.get(self.case.base+'/epochs',query_string={**filters,'limit':1,'include_cells':'true'})
                self.assertEqual(response.status_code,200,response.get_json())
                page=response.get_json()
                self.assertEqual({item['cell_uuid']:item['epochs'] for item in page['cells']},
                    {item['cell_uuid']:item['epochs'] for item in summary['cells']})
                self.assertEqual(sum(item['epochs'] for item in page['cells']),page['total'])
                self.assertEqual(page['expected_binding_version'],summary['expected_binding_version'])
                self.assertEqual(page['query_revision'],summary['query_revision'])
                self.assertLessEqual(len(page['epochs']),1)
        for query in ('include_cells=1','include_cells=true&include_cells=false'):
            self.assertEqual(self.client.get(self.case.base+'/epochs?'+query).status_code,400)

    def test_registered_metadata_fields_do_not_load_scope_values_or_saved_state(self):
        expected=self.index.catalog()['fields']
        with patch.object(self.index,'values',side_effect=AssertionError('No epoch value materialization')), \
             patch.object(self.service,'filtered_rows',side_effect=AssertionError('No filtered epoch scan')), \
             patch.object(self.service,'_tree_rows',side_effect=AssertionError('No tree epoch scan')), \
             patch.object(self.reader,'full_state',side_effect=AssertionError('No saved-state scan')):
            response=self.client.get('/api/metadata/fields')
        self.assertEqual(response.status_code,200,response.get_json())
        fields=response.get_json()['fields']
        self.assertEqual([field['id'] for field in fields],[field['id'] for field in expected])
        self.assertEqual([field.get('grouping_role') for field in fields],[field.get('grouping_role') for field in expected])
        self.assertTrue(all('distinct_count' not in field and 'examples' not in field for field in fields))
        fields[0]['label']='changed output'
        self.assertNotEqual(self.service.metadata_fields()['fields'][0]['label'],'changed output')
        self.assertEqual(self.client.get('/api/metadata/fields?tag=hidden').status_code,400)
        self.service._loaded=False
        with self.assertRaises(RuntimeError):self.service.metadata_fields()
        self.service._loaded=True
        with self.index.path.open('ab') as stream:stream.write(b'changed seal')
        with self.assertRaises(ValueError):self.service.metadata_fields()

    def test_native_protocols_share_exact_source_proofs_without_aliasing_mutable_inputs(self):
        from workspace_protocol_state import _retained_bytes,STATE_CACHE_BYTES
        self.native_generation()
        other=str(uuid.uuid4())
        self.service.protocols[other]=copy.deepcopy(self.service.protocols[self.protocol])
        self.service.protocols[other]['definition']['protocol_uuid']=other
        self.service.protocols[other]['result']['protocol_uuid']=other
        first=self.reader.native_context(self.protocol)
        second=self.reader.native_context(other)
        left=self.reader.native_cache[self.protocol];right=self.reader.native_cache[other]
        self.assertIs(left['metadata']['fingerprints'],right['metadata']['fingerprints'])
        self.assertIs(left['metadata']['query']['epochs'],right['metadata']['query']['epochs'])
        self.assertIs(left['members'],right['members']);self.assertIs(left['allowed'],right['allowed'])
        self.assertIsNot(left['metadata']['fingerprints'],self.service._fingerprints)
        self.assertIsNot(left['metadata']['query']['epochs'],self.service.protocols[self.protocol]['result']['epochs'])
        retained=_retained_bytes(self.reader.native_cache,STATE_CACHE_BYTES)+4096*len(self.reader.native_cache)
        repeated=sum(entry['size'] for entry in self.reader.native_cache.values())
        self.assertLess(retained,repeated)
        self.reader.native_cache.clear()
        with patch('workspace_protocol_state.STATE_CACHE_BYTES',retained+256):
            self.reader.native_context(self.protocol);self.reader.native_context(other)
            self.assertEqual(set(self.reader.native_cache),{self.protocol,other})
        self.service._fingerprints[self.ids[0]]='d'*64
        changed=self.reader.native_context(other)
        self.assertNotEqual(second['query_revision'],changed['query_revision'])
        self.assertNotEqual(left['metadata']['fingerprints'][self.ids[0]],'d'*64)
        self.assertNotEqual(first['query_revision'],self.reader.native_context(self.protocol)['query_revision'])
        self.service.protocols[other]['result']['epochs'].reverse()
        changed_again=self.reader.native_context(other)
        self.assertNotEqual(changed['query_revision'],changed_again['query_revision'])

    def test_specialized_epoch_comparison_matches_recursive_type_and_shape_contract(self):
        from workspace_protocol_state import _plain_epoch_records,_epoch_query_equal,_exact_equal
        class StringSubclass(str):pass
        class DictSubclass(dict):pass
        original={'epochs':[{'uuid':'first','metadata_hash':'a'},{'uuid':'second','metadata_hash':'b'}],
            'numeric_guard':0.0,'nested':{'items':[True,1,1.0]}}
        self.assertTrue(_plain_epoch_records(original['epochs']))
        variants=[]
        for field,value in [('uuid',False),('uuid',1),('metadata_hash',StringSubclass('a')),
                ('metadata_hash',None),('extra','x')]:
            candidate=copy.deepcopy(original);candidate['epochs'][0][field]=value;variants.append(candidate)
        candidate=copy.deepcopy(original);candidate['epochs'][0]=DictSubclass(candidate['epochs'][0]);variants.append(candidate)
        candidate=copy.deepcopy(original);candidate['epochs'].reverse();variants.append(candidate)
        candidate=copy.deepcopy(original);candidate['epochs']=tuple(candidate['epochs']);variants.append(candidate)
        for value in (False,0,-0.0):
            candidate=copy.deepcopy(original);candidate['numeric_guard']=value;variants.append(candidate)
        variants.append(copy.deepcopy(original))
        for candidate in variants:
            self.assertEqual(_epoch_query_equal(candidate,original),_exact_equal(candidate,original),candidate)

    def test_native_plain_epoch_proof_preserves_other_query_numeric_types(self):
        self.native_generation()
        revisions=[]
        for value in (1,True,1.0,0.0,-0.0):
            self.service.protocols[self.protocol]['result']['numeric_guard']=value
            revisions.append(self.page()['query_revision'])
            self.assertTrue(self.reader.native_cache[self.protocol]['plain_epochs'])
        self.assertEqual(len(set(revisions)),len(revisions))

    def test_native_v3_mutation_uses_selected_context_and_transaction_preflight(self):
        tracker=self.native_generation()
        before=self.page()
        first=before['epochs'][0]['epoch_uuid']
        body={'epoch_uuids':[first],'changes':{'tags_add':['saved']},'expected_revisions':{first:0},
            'query_revision':before['query_revision'],'expected_binding_version':0}
        with patch.object(self.reader,'full_state',side_effect=AssertionError('Native selected mutation must not materialize protocol')):
            response=self.client.post(self.case.base+'/curation',json=body,headers=self.case.headers)
            after=self.page()
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(tracker.locked_checks,1)
        self.assertNotEqual(before['query_revision'],after['query_revision'])
        rejected=self.client.post(self.case.base+'/curation',json=body,headers=self.case.headers)
        self.assertEqual(rejected.status_code,409)

    def test_native_protocol_summary_matches_legacy_without_full_saved_tag_reads(self):
        tracker=self.native_generation()
        self.save_curation(ids=self.ids[:1],tags_add=['one','two'],included=False,review_state='approved')
        self.save_curation(ids=self.ids[1:],tags_add=['three'],review_state='approved')
        self.service._fingerprints[self.ids[1]]='c'*64  # Approval must become stale.
        self.fixture.edit('cell',self.service.rows[self.ids[0]]['cell_uuid'],['inherited'])
        for query in ('','?cell_uuid='+self.service.rows[self.ids[0]]['cell_uuid'],'?tag=inherited'):
            tracker.disabled=True
            expected=self.client.get(self.case.base+query)
            self.assertEqual(expected.status_code,200,expected.get_json())
            expected=expected.get_json()
            tracker.disabled=False
            self.case.curation.read_log.clear()
            with patch.object(self.reader,'full_state',side_effect=AssertionError('No full state for native summary')), \
                 patch.object(self.service,'filtered_rows',side_effect=AssertionError('No decorated full curation rows')):
                response=self.client.get(self.case.base+query)
            self.assertEqual(response.status_code,200,response.get_json())
            actual=response.get_json()
            self.assertTrue(actual['query_revision'].startswith('protocol-state-v3:'))
            for body in (actual,expected):
                body.pop('query_revision',None);body.pop('expected_query_revision',None);body.pop('query_revision_contract',None)
            self.assertEqual(actual,expected)
            self.assertTrue(self.case.curation.read_log)
            self.assertTrue(all(row['projected'] is not None and 'tags' not in row['projected']
                for row in self.case.curation.read_log),self.case.curation.read_log)

    def test_native_overview_matches_legacy_without_protocol_tag_hydration(self):
        tracker=self.native_generation()
        self.save_curation(ids=self.ids[:1],tags_add=['one','two'],included=False,review_state='approved')
        self.save_curation(ids=self.ids[1:],tags_add=['three'],review_state='approved')
        self.service._fingerprints[self.ids[1]]='c'*64
        self.fixture.edit('epoch',self.ids[0],['project-tag'])
        tracker.disabled=True
        with patch.object(self.service,'events',return_value=[]):
            expected=self.client.get('/api/overview')
        self.assertEqual(expected.status_code,200,expected.get_json());expected=expected.get_json()
        tracker.disabled=False
        self.case.curation.read_log.clear()
        with patch.object(self.reader,'full_state',side_effect=AssertionError('No full state for native overview')), \
             patch.object(self.service,'overview',side_effect=AssertionError('No decorated legacy overview')), \
             patch.object(self.service,'events',return_value=[]):
            response=self.client.get('/api/overview')
        self.assertEqual(response.status_code,200,response.get_json());actual=response.get_json()
        for body in (actual,expected):
            for protocol in body['protocols']:protocol.pop('query_revision',None)
        self.assertEqual(actual,expected)
        self.assertTrue(all(row['projected'] is not None and 'tags' not in row['projected']
            for row in self.case.curation.read_log),self.case.curation.read_log)

    def test_custom_shared_snapshot_policy_does_not_enter_native_revision_contract(self):
        self.native_generation()
        original=self.reader.shared.snapshot
        def custom():return {**original(),'revision':'custom-policy'}
        with patch.object(self.reader.shared,'snapshot',side_effect=custom):
            self.assertIsNone(self.reader.native_context(self.protocol,self.ids))
            result=self.reader.read_selected(self.protocol,self.ids)
            self.assertFalse(result[1].startswith('protocol-state-v3:'))

    def test_native_v3_binding_guard_preserves_revision_inside_transaction(self):
        tracker=self.native_generation()
        connection=self.store.dj.conn()
        connection_type=type(connection)
        original_transaction=connection_type.transaction
        @contextlib.contextmanager
        def transaction(owner):
            with original_transaction.__get__(owner,connection_type):
                tracker.in_transaction=True
                try:yield
                finally:tracker.in_transaction=False
        with patch.object(connection_type,'transaction',property(transaction)), patch.object(self.service,'refresh',return_value={}):
            saved=self.client.post('/api/explore/revisions',json={'predicate':{'all':[]},'splits':'cell'},headers=self.case.headers)
            self.assertEqual(saved.status_code,201,saved.get_json())
            identity=saved.get_json()['revision_uuid']
            comparison=self.client.post('/api/explore/revisions/'+identity+'/compare-to-protocol',
                json={'protocol_uuid':self.protocol},headers=self.case.headers)
            self.assertEqual(comparison.status_code,200,comparison.get_json())
            current=comparison.get_json()
            self.assertTrue(current['expected_query_revision'].startswith('protocol-state-v3:'))
            applied=self.client.post('/api/explore/revisions/'+identity+'/apply-to-protocol',json={
                'protocol_uuid':self.protocol,'expected_binding_version':current['expected_binding_version'],
                'expected_query_revision':current['expected_query_revision']},headers=self.case.headers)
            self.assertEqual(applied.status_code,200,applied.get_json())
        self.assertGreater(tracker.locked_checks,0)

    def test_native_v3_fences_revision_and_visible_provenance(self):
        self.native_generation()
        original=self.fixture.shared.for_epochs if hasattr(self.fixture,'shared') else self.reader.shared.for_epochs
        def racing(rows):
            result=original(rows)
            self.case.curation.rows.append({'project_uuid':self.service.project['project_uuid'],
                'protocol_uuid':self.protocol,'epoch_uuid':self.ids[1], 'included':True,
                'tags':['race'],'review_state':'unreviewed','revision':1,
                'metadata_fingerprint':self.service._fingerprints[self.ids[1]]})
            return result
        with patch.object(self.reader.shared,'for_epochs',side_effect=racing):
            response=self.client.get(self.case.base+'/epochs?limit=1')
        self.assertEqual(response.status_code,409,response.get_json())

    def page(self):
        response=self.client.get(self.case.base+'/epochs?limit=1')
        self.assertEqual(response.status_code,200,response.get_json())
        return response.get_json()

    def assert_oracle(self, actual, ids=None):
        result,states,revision=self.reader.full_state(self.protocol)
        expected=ids or self.ids
        self.assertEqual(actual[0],{key:states[key] for key in expected})
        self.assertEqual(actual[1],revision)
        self.assertEqual(actual[2],result.get('dataset_binding',{}).get('version',0))

    def save_curation(self, ids=None, **changes):
        ids=ids or self.ids[:1]
        return self.store.update(self.protocol,ids,changes,{key:0 for key in ids},
            {key:self.service._fingerprints[key] for key in ids},'fixture')

    def test_warm_http_page_reuses_exact_revision_and_hydrates_only_selected_state(self):
        first=self.page()
        self.assertIn(self.protocol,self.reader.cache)
        calls=[]
        code=self.store._state.__code__
        previous=sys.getprofile()
        def observe(frame,event,arg):
            if event=='call' and frame.f_code is code:calls.append(None)
        with patch.object(self.reader,'full_state',side_effect=AssertionError('No full state on a hit')):
            sys.setprofile(observe)
            try:second=self.page()
            finally:sys.setprofile(previous)
        self.assertEqual(second,first)
        self.assertEqual(len(calls),1)
        self.assertEqual(first['query_revision'],self.reader.full_state(self.protocol)[2])

    def test_sparse_same_revision_sql_edits_and_deletions_invalidate_by_exact_values(self):
        self.save_curation(tags_add=['before'])
        before=self.reader.read_selected(self.protocol,self.ids)
        row=self.case.curation.rows[0]
        row['tags']=['changed outside this process']  # Deliberately no counter bump.
        row['included']=False
        after=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(after[1],before[1])
        self.assert_oracle(after)
        self.assertEqual(after[0][self.ids[0]]['tags'],row['tags'])
        self.case.curation.rows.clear()
        removed=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(removed[1],after[1])
        self.assert_oracle(removed)

    def test_shared_tag_change_invalidates_even_when_target_is_outside_page(self):
        before=self.reader.read_selected(self.protocol,self.ids[:1])
        self.fixture.edit('epoch',self.ids[1],['other page'])
        after=self.reader.read_selected(self.protocol,self.ids[:1])
        self.assertNotEqual(after[1],before[1])
        self.assert_oracle(after,self.ids[:1])
        # Full shared records, not only numeric revisions, determine freshness.
        self.fixture.records.rows[0]['tags']=['same revision, new tag']
        changed=self.reader.read_selected(self.protocol,self.ids[:1])
        self.assertNotEqual(changed[1],after[1])
        self.assert_oracle(changed,self.ids[:1])

    def test_metadata_membership_sources_and_numeric_representation_invalidate(self):
        before=self.reader.read_selected(self.protocol,self.ids)
        self.service._fingerprints[self.ids[0]]='c'*64
        changed=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(before[1],changed[1]);self.assert_oracle(changed)
        self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}})
        excluded=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(changed[1],excluded[1]);self.assert_oracle(excluded)
        # Query values preserve JSON numeric type and signed-zero semantics.
        query=self.service.protocols[self.protocol]['result']
        revisions=[]
        for value in (1,1.0,True,0.0,-0.0):
            query['numeric_guard']=value
            actual=self.reader.read_selected(self.protocol,self.ids)
            self.assert_oracle(actual);revisions.append(actual[1])
        self.assertEqual(len(set(revisions)),len(revisions))
        query['epochs'].pop()
        with self.assertRaisesRegex(ValueError,'outside'):
            self.reader.read_selected(self.protocol,self.ids)
        self.assert_oracle(self.reader.read_selected(self.protocol,self.ids[:1]),self.ids[:1])

    def test_cache_never_hides_seal_corruption_or_failed_refresh(self):
        self.reader.read_selected(self.protocol,self.ids)
        self.service._loaded=False
        with self.assertRaises(RuntimeError):self.reader.read_selected(self.protocol,self.ids)
        self.service._loaded=True
        with self.index.path.open('ab') as stream:stream.write(b'changed')
        with self.assertRaises(ValueError):self.reader.read_selected(self.protocol,self.ids)

    def test_cached_revision_cannot_allow_detail_from_outside_current_query(self):
        self.reader.read_selected(self.protocol,self.ids)
        self.service.protocols[self.protocol]['result']['epochs'].pop()
        response=self.client.get('/api/epochs/'+self.ids[1]+'?protocol_uuid='+self.protocol)
        self.assertEqual(response.status_code,400,response.get_json())
        self.assertIn('outside',response.get_json()['error'])

    def test_warm_cache_does_not_bypass_stale_mutation_or_batch_revision_guards(self):
        page=self.page()
        self.fixture.edit('epoch',self.ids[1],['changed'])
        response=self.client.post(self.case.base+'/curation',json={
            'epoch_uuids':self.ids[:1],'query_revision':page['query_revision'],
            'changes':{'included':False},'expected_revisions':{self.ids[0]:0}},headers=self.case.headers)
        self.assertEqual(response.status_code,409,response.get_json())
        self.assertFalse(self.case.curation.rows)
        response=self.client.post(self.case.base+'/curation/read',json={
            'epoch_uuids':self.ids[:1],'query_revision':page['query_revision'],
            'expected_binding_version':0,'selection_scope':{'filters':{},'cell_uuid':None}},headers=self.case.headers)
        self.assertEqual(response.status_code,409,response.get_json())

    def test_racing_writer_prevents_admission_of_a_mixed_proof(self):
        self.save_curation(tags_add=['before'])
        oracle=self.reader.full_state
        def racing(protocol):
            result=oracle(protocol)
            self.case.curation.rows[0]['tags']=['after']
            return result
        with patch.object(self.reader,'full_state',side_effect=racing):
            older=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotIn(self.protocol,self.reader.cache)
        self.assertEqual(older[0][self.ids[0]]['tags'],['before'])
        newer=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(newer[1],older[1]);self.assert_oracle(newer)

    def test_byte_pressure_evicts_scopes_and_large_saved_values_are_not_retained(self):
        expected=self.reader.read_selected(self.protocol,self.ids)
        size=self.reader.cache[self.protocol]['size']
        other=str(uuid.uuid4())
        self.service.protocols[other]=copy.deepcopy(self.service.protocols[self.protocol])
        self.service.protocols[other]['result']['protocol_uuid']=other
        self.service.protocols[other]['definition']['protocol_uuid']=other
        self.reader.cache.clear()
        with patch('workspace_protocol_state.STATE_CACHE_BYTES',size+4096):
            self.reader.read_selected(self.protocol,self.ids)
            self.reader.read_selected(other,self.ids)
            self.assertEqual(list(self.reader.cache),[other])
            self.assertEqual(self.reader.read_selected(self.protocol,self.ids),expected)
            self.assertEqual(list(self.reader.cache),[self.protocol])
        self.save_curation(tags_add=['before'])
        self.case.curation.rows[0]['tags']=['x'*100000]
        self.reader.cache.clear()
        with patch('workspace_protocol_state.STATE_CACHE_BYTES',size+4096), \
             patch.object(self.reader,'full_state',wraps=self.reader.full_state) as oracle:
            first=self.reader.read_selected(self.protocol,self.ids)
            second=self.reader.read_selected(self.protocol,self.ids)
        self.assertEqual(first,second)
        self.assertEqual(oracle.call_count,2)
        self.assertFalse(self.reader.cache)

    def test_binding_change_and_mutable_bound_cell_metadata_invalidate(self):
        before=self.reader.read_selected(self.protocol,self.ids)
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        history=self.case.explorer_history
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        bound=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(bound[1],before[1]);self.assert_oracle(bound)
        self.service.cells[self.service.cell_ids[0]]['label']='Changed label'
        changed=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(bound[1],changed[1]);self.assert_oracle(changed)
        self.service.rows[self.ids[1]]['cell_uuid']=self.service.cell_ids[0]
        ownership=self.reader.read_selected(self.protocol,self.ids)
        self.assertNotEqual(ownership[1],changed[1]);self.assert_oracle(ownership)

    def test_public_read_only_and_overridden_store_policies_use_full_oracle(self):
        class PublicReadOnly:
            def read(inner,*args,**kwargs):return self.store.read(*args,**kwargs)
        reader=ProtocolStateReader(self.service,PublicReadOnly(),self.fixture.store,self.reader.full_state)
        self.assert_oracle(reader.read_selected(self.protocol,self.ids))
        self.assertFalse(reader.cache)
        native=self.store.read
        policy={'included':True}
        def custom(*args,**kwargs):
            states=native(*args,**kwargs)
            for state in states.values():state['included']=policy['included']
            return states
        with patch.object(self.store,'read',side_effect=custom):
            first=self.reader.read_selected(self.protocol,self.ids)
            policy['included']=False
            second=self.reader.read_selected(self.protocol,self.ids)
            self.assertNotEqual(first[1],second[1]);self.assert_oracle(second)
            self.assertFalse(self.reader.cache)

    def test_overridden_service_policy_and_unmatched_binding_headers_fall_back(self):
        native=self.service.query_result
        policy={'changed':False}
        def custom(protocol):
            result=native(protocol)
            if policy['changed']:result['custom_policy']='new'
            return result
        with patch.object(self.service,'query_result',side_effect=custom):
            first=self.reader.read_selected(self.protocol,self.ids)
            policy['changed']=True
            second=self.reader.read_selected(self.protocol,self.ids)
            self.assertNotEqual(first[1],second[1]);self.assert_oracle(second)
            self.assertFalse(self.reader.cache)
        history=self.case.explorer_history
        self.service.set_binding_provider(history.protocol_binding,header_provider=lambda protocol:None)
        first=self.reader.read_selected(self.protocol,self.ids)
        preview=self.service.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
        created=history.create(preview,self.service.sources,'catalog.json','fixture')
        history.bind(created['revision_uuid'],self.protocol,0,'fixture',{},2)
        second=self.reader.read_selected(self.protocol,self.ids)
        self.assertEqual(second[2],1)
        self.assertNotEqual(first[1],second[1]);self.assert_oracle(second)
        self.assertFalse(self.reader.cache)

    def test_rejected_scope_uses_one_full_read_and_generation_change_retries(self):
        self.save_curation(tags_add=['before'])
        self.case.curation.rows[0]['tags']=['x'*100000]
        with patch('workspace_protocol_state.STATE_CACHE_BYTES',20000):
            first=self.reader.read_selected(self.protocol,self.ids)
            self.assertIn(self.protocol,self.reader.rejected)
            self.case.curation.read_log.clear()
            with patch.object(self.reader,'_metadata',side_effect=AssertionError('Skip futile admission')):
                second=self.reader.read_selected(self.protocol,self.ids)
                self.case.curation.rows[0]['included']=False
                changed=self.reader.read_selected(self.protocol,self.ids)
                with self.assertRaisesRegex(ValueError,'outside'):
                    self.reader.read_selected(self.protocol,[str(uuid.uuid4())])
            self.assertEqual(first,second)
            self.assertNotEqual(changed[1],second[1])
            self.assertEqual(len(self.case.curation.read_log),3)
            self.assert_oracle(changed)
            self.service._fingerprints=dict(self.service._fingerprints)
            with patch.object(self.reader,'_metadata',wraps=self.reader._metadata) as metadata:
                self.reader.read_selected(self.protocol,self.ids)
                self.assertGreater(metadata.call_count,0)
        # A changed/custom adapter cannot retain a previous native proof.
        with patch.object(self.store,'read',wraps=self.store.read):
            self.assert_oracle(self.reader.read_selected(self.protocol,self.ids))
            self.assertNotIn(self.protocol,self.reader.rejected)

    def test_rejection_memo_is_bounded(self):
        with patch('workspace_protocol_state.STATE_CACHE_BYTES',1):
            for _ in range(12):
                protocol=str(uuid.uuid4())
                self.service.protocols[protocol]=copy.deepcopy(self.service.protocols[self.protocol])
                self.service.protocols[protocol]['result']['protocol_uuid']=protocol
                self.reader.read_selected(protocol,self.ids)
        self.assertEqual(len(self.reader.rejected),8)
        self.assertFalse(self.reader.cache)


if __name__=='__main__':unittest.main()
