"""Independent service/HTTP small-fixture gates against an exact committed target."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
from truth import Truth,canonical,digest,kind,validation_rejections
from service_checks import assert_registry,assert_summary_state,assert_generation_compatible

TARGET=None
RECEIPTS=[]


def browser_safe(value):
    # Frozen existing browser transport contract: exact unsafe integers become strings.
    if type(value) is int and abs(value)>2**53-1:return str(value)
    if isinstance(value,dict):return {k:browser_safe(v) for k,v in value.items()}
    if isinstance(value,list):return [browser_safe(v) for v in value]
    return value


class IntegratedServiceTruth(unittest.TestCase):
    def setUp(self):
        import test_workspace_annotations as fixtures
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.metadata.typed_lifecycle import prepare
        self.truth=Truth();data=self.truth.fixture()
        self.case=fixtures.SharedAnnotationTests();self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service=self.case.service;self.client=self.case.client;self.headers=self.case.headers
        self.store=self.case.store;self.author=self.store.default_profile['profile_uuid']
        self.source_rows={r['epoch_uuid']:{**r,'metadata_hash':'b'*64} for r in data['rows']}
        self.service.rows=copy.deepcopy(self.source_rows);self.service.details=data['details']
        self.service.ids=list(self.source_rows);self.service.sources=data['sources']
        self.service._fingerprints={i:'b'*64 for i in self.source_rows}
        self.service.cells={r['cell_uuid']:dict(cell_uuid=r['cell_uuid'],label=r['cell_label'],
            cell_type=r['cell_type'],date=r['date'],start_time=r['start_time']) for r in data['rows']}
        self.service.cell_ids=list(self.service.cells)
        self.service.manifests={s['source_sha256']:{'source_path':str(Path(self.case.case.temp.name)/(s['source_sha256']+'.h5'))} for s in data['sources']}
        result=self.service.protocols[self.service.protocol_id]['result']
        result['epochs']=[dict(uuid=i,metadata_hash='b'*64) for i in self.truth.ids]
        result['cells']=[dict(uuid=i) for i in self.service.cells]
        result['source_revisions']=['source-A','source-B']
        self.states={};self.service.set_source_state_provider(lambda:self.states)
        path=Path(self.case.case.temp.name)/'cache'/'metadata'/('d'*64+'.sqlite')
        index=DiskMetadataIndex.build(path,self.service.rows,self.service.details,self.service.sources,
                                      'd'*64,self.service.project['project_uuid'])
        self.service.disk_index=index;self.service.typed_index,status=prepare(index)
        self.addCleanup(index.close)
        self.addCleanup(self.service.typed_index.reader.close)
        self.addCleanup(self.service.typed_index.lease.close)
        self.manager=self.case.app.extensions['metadata_summary_jobs'];self.manager.autostart=False
        self.source_before=digest((self.service.rows,self.service.details))
        self.record=dict(test=self._testMethodName,status='running',truth_sha256=self.truth.sha256,
                         integrated_service=True,real_million=False)
        RECEIPTS.append(self.record)

    def tearDown(self):
        self.assertEqual(digest((self.service.rows,self.service.details)),self.source_before)
        if self.record['status']=='running':self.record['status']='completed; see unittest outcome'

    def registry(self):
        response=self.client.get('/api/explore/field-registry');self.assertEqual(response.status_code,200,response.get_json())
        result=response.get_json();assert_registry(result,self.truth.fields)
        return result

    def request(self,predicate=None,fields=None,**context):
        body=dict(predicate={'all':[]} if predicate is None else predicate,
                  summary_fields=['parameters/mixed','parameters/optional'] if fields is None else fields,
                  generation=self.registry()['generation'],**context)
        response=self.client.post('/api/explore/summaries',json=body,headers=self.headers)
        self.assertEqual(response.status_code,202,response.get_json())
        ack=response.get_json();assert_generation_compatible(body['generation'],ack['generation'])
        assert_summary_state(ack,ack['request_id'],ack['generation'],'pending')
        return body,ack

    def ready(self,predicate=None,fields=None,expected_ids=None,**context):
        body,ack=self.request(predicate,fields,**context);self.manager.drive_worker()
        response=self.client.get('/api/explore/summaries/'+ack['request_id']);payload=response.get_json()
        expected_ids=self.truth.membership(predicate) if expected_ids is None else expected_ids
        expected=dict(count=len(expected_ids),facets=browser_safe(self.truth.facets(expected_ids,body['summary_fields'])))
        assert_summary_state(payload,ack['request_id'],ack['generation'],'ready',expected)
        return body,ack,payload

    def page(self,predicate,**context):
        response=self.client.post('/api/explore/page',data=json.dumps(dict(predicate=predicate,**context)),content_type='application/json',headers=self.headers)
        return response

    def test_complete_registry_requested_and_full_facets_and_detail(self):
        registry=self.registry();native={f['id']:f for f in registry['fields'] if f['id'] in self.truth.fields}
        self.assertEqual(set(native),set(self.truth.fields))
        for field,definition in native.items():
            expected=sorted({kind(v[field]) for v in self.truth.values.values() if field in v})
            self.assertEqual(definition['types'],expected,field)
        full=self.ready(fields=self.truth.fields)[2]['result']
        selected=self.ready()[2]['result']
        self.assertEqual(full['matched_count'],selected['matched_count'])
        for field,facet in selected['summaries'].items():self.assertEqual(facet,full['summaries'][field])
        count=self.ready(fields=[])[2]['result'];self.assertEqual(count,dict(matched_count=12,summaries={}))
        self.assertNotIn('parameters/a~1b~0',selected['summaries'])
        for i,raw in self.truth.fixture()['details'].items():
            response=self.client.get('/api/epochs/'+i);self.assertEqual(response.status_code,200,response.get_json())
            payload=response.get_json()
            for key,value in raw.items():self.assertEqual(canonical(payload[key]),canonical(browser_safe(value)),key)
            self.assertEqual(payload['source_reference']['sha256'],self.source_rows[i]['source_sha256'])
        self.record.update(status='passed',native_fields=len(native),detail_checks=12,all_field_summary=True)

    def test_all_native_predicates_structural_pages_and_exact_errors(self):
        comparisons=0
        first=self.truth.ids[0]
        scopes=[(None,None),({'cell':self.truth.values[first]['cell']},{'cell_uuid':self.truth.values[first]['cell']}),
                ({'block':self.truth.values[first]['block']},{'block_uuid':self.truth.values[first]['block']}),
                ({'group':self.truth.values[first]['group']},{'group_uuid':self.truth.values[first]['group']})]
        for native_scope,scope in scopes:
            for predicate in self.truth.scenarios():
                predicate=predicate or {'all':[]}
                page=self.service.explore_page(predicate,scope=scope,limit=100)
                expected=self.truth.membership(predicate,native_scope)
                self.assertEqual(canonical(page['rows']),canonical([self.source_rows[i] for i in expected]))
                self.assertIsNone(page['cursor']);comparisons+=1
        for predicate,error in validation_rejections():
            response=self.page(predicate)
            self.assertEqual(response.status_code,400,response.get_json());self.assertEqual(response.get_json()['error'],error)
        cursor=None;seen=[];page_hashes=[]
        while True:
            body=dict(limit=3)
            if cursor:body['cursor']=cursor
            response=self.page({'all':[]},**body);self.assertEqual(response.status_code,200,response.get_json())
            payload=response.get_json();seen.extend(row['epoch_uuid'] for row in payload['rows']);page_hashes.append(digest(payload['rows']))
            cursor=payload['cursor']
            if cursor is None:break
            self.assertIsInstance(cursor,str)
        self.assertEqual(seen,self.truth.ids)
        self.record.update(status='passed',predicate_page_comparisons=comparisons,validation_rejections=8,
                           full_pagination_rows=12,page_hashes=page_hashes)

    def test_cursor_query_publication_source_and_tamper_faults(self):
        first=self.page({'all':[]},limit=1).get_json();cursor=first['cursor']
        response=self.page({'field':'cell','operator':'eq','value':self.truth.values[self.truth.ids[0]]['cell']},limit=1,cursor=cursor)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.page({'all':[]},cursor=cursor+'tamper').status_code,400)
        self.assertEqual(self.page({'all':[]},cursor=1).status_code,400)
        self.service._explore_publication='replacement'
        self.assertEqual(self.page({'all':[]},cursor=cursor).status_code,409)
        cursor=self.page({'all':[]},limit=1).get_json()['cursor']
        self.states['source-B']={'query_excluded':True}
        self.assertEqual(self.page({'all':[]},cursor=cursor).status_code,409)
        self.record.update(status='passed',query_generation_tamper_faults=5)

    def test_excluded_source_and_frozen_protocol_binding_context(self):
        self.states['source-B']={'query_excluded':True}
        expected=self.truth.membership(eligible_sources=['source-A'])
        self.assertEqual(self.page({'all':[]}).get_json()['rows'],[self.source_rows[i] for i in expected])
        self.ready(expected_ids=expected)
        body,ack,ready=self.ready(protocol_uuid=self.service.protocol_id,expected_ids=self.truth.ids)
        self.assertNotEqual(body['generation']['binding'],ack['generation']['binding'])
        self.assertEqual(ready['generation'],ack['generation'])
        # Exact frozen membership under a custom native binding policy: fallback is explicit.
        frozen=[self.truth.ids[10],self.truth.ids[8]]
        binding=dict(recipe=dict(epochs=[dict(uuid=i,metadata_hash='b'*64) for i in frozen],
            source_revisions=['source-B'],predicate={'all':[]},tree_view={'fields':['cell']},
            name='isolated binding',splits='cell'),revision_uuid=str(uuid.uuid4()),version=1)
        self.service.set_binding_provider(lambda _:binding)
        body,ack,_=self.ready(protocol_uuid=self.service.protocol_id,expected_ids=sorted(frozen))
        self.assertNotEqual(body['generation']['binding'],ack['generation']['binding'])
        self.record.update(status='passed',new_query_epochs=8,original_protocol_epochs=12,frozen_epochs=2,
                           custom_binding_native_fallback=True,broadscale_fallback_qualified=False)

    def test_pending_ready_cancel_read_failure_and_stale_generation_fences(self):
        _,ack=self.request();identity=ack['request_id']
        payload=self.client.post('/api/explore/summaries/'+identity+'/cancel',json={},headers=self.headers).get_json()
        assert_summary_state(payload,identity,ack['generation'],'cancelled');self.manager.drive_worker()
        assert_summary_state(self.manager.poll(identity),identity,ack['generation'],'cancelled')
        _,ack,_=self.ready();identity=ack['request_id']
        payload=self.client.post('/api/explore/summaries/'+identity+'/cancel',json={},headers=self.headers).get_json()
        assert_summary_state(payload,identity,ack['generation'],'cancelled')
        _,ack=self.request()
        with patch.object(self.manager,'_calculate',side_effect=RuntimeError('independent read fault')):self.manager.drive_worker()
        assert_summary_state(self.manager.poll(ack['request_id']),ack['request_id'],ack['generation'],'failed')
        _,ack=self.request();self.service._explore_publication='before-worker';self.manager.drive_worker()
        assert_summary_state(self.manager.poll(ack['request_id']),ack['request_id'],ack['generation'],'stale')
        _,ack=self.request();original=self.manager._calculate
        def mutation(*args,**kwargs):
            result=original(*args,**kwargs);self.service._explore_publication='before-publication';return result
        with patch.object(self.manager,'_calculate',mutation):self.manager.drive_worker()
        assert_summary_state(self.manager.poll(ack['request_id']),ack['request_id'],ack['generation'],'stale')
        _,ack,_=self.ready();self.states['source-B']={'query_excluded':True}
        assert_summary_state(self.manager.poll(ack['request_id']),ack['request_id'],ack['generation'],'stale')
        self.record.update(status='passed',cancelled_pending_and_ready=True,read_fault=True,
                           generation_before_worker=True,generation_before_publication=True,source_after_ready=True)

    def test_annotation_native_fallback_equal_membership_and_protocol_curation_ownership(self):
        cell=self.truth.values[self.truth.ids[0]]['cell'];direct=self.truth.ids[5]
        self.store.update('cell',[cell],self.author,{'tags_add':['inherited']},{cell:0},'isolated actor')
        self.store.update('epoch',[direct],self.author,{'tags_add':['direct']},{direct:0},'isolated actor')
        predicate=dict(field='annotations/effective/tags',operator='contains',value='inherited')
        expected=self.truth.membership(scope={'cell':cell})
        fields=['annotations/cell/tags','annotations/epoch/tags','annotations/effective/tags']
        body,ack=self.request(predicate,fields);self.manager.drive_worker()
        payload=self.manager.poll(ack['request_id']);self.assertEqual(payload['status'],'ready',payload)
        self.assertEqual(payload['result'],dict(matched_count=4,summaries={
            'annotations/cell/tags':dict(values=[dict(value=['inherited'],type='array',count=4)],present_count=4,missing_count=0,values_truncated=False),
            'annotations/epoch/tags':dict(values=[dict(value=[],type='array',count=4)],present_count=4,missing_count=0,values_truncated=False),
            'annotations/effective/tags':dict(values=[dict(value=['inherited'],type='array',count=4)],present_count=4,missing_count=0,values_truncated=False)}))
        self.assertEqual([r['epoch_uuid'] for r in self.page(predicate).get_json()['rows']],expected)
        cursor=self.page(predicate,limit=1).get_json()['cursor']
        self.store.update('cell',[cell],self.author,{'tags_add':['unrelated']},{cell:1},'isolated actor')
        stale=self.manager.poll(ack['request_id']);assert_summary_state(stale,ack['request_id'],ack['generation'],'stale')
        self.assertEqual([r['epoch_uuid'] for r in self.page(predicate).get_json()['rows']],expected)
        self.assertEqual(self.page(predicate,limit=1,cursor=cursor).status_code,409)
        curation='curation/'+self.service.protocol_id+'/tags'
        before=self.request(dict(field=curation,operator='contains',value='reviewed'),[curation])[1]
        self.manager.drive_worker();self.assertEqual(self.manager.poll(before['request_id'])['result']['matched_count'],0)
        self.case.case.curation.insert1(dict(project_uuid=self.service.project['project_uuid'],protocol_uuid=self.service.protocol_id,
                                            epoch_uuid=self.truth.ids[0],tags=['reviewed'],revision=1))
        assert_summary_state(self.manager.poll(before['request_id']),before['request_id'],before['generation'],'stale')
        self.assertEqual(self.page(dict(field='annotations/effective/tags',operator='contains',value='reviewed')).get_json()['rows'],[])
        self.record.update(status='passed',shared_ownership=True,protocol_curation_distinct=True,
                           equal_membership_annotation_stales=True,broadscale_native_fallback_qualified=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--implementation-root',type=Path,required=True)
    parser.add_argument('--expected-commit',required=True);parser.add_argument('--receipt',type=Path,required=True);args=parser.parse_args()
    git=lambda *cmd:subprocess.check_output(['git','-C',str(args.implementation_root),*cmd],text=True).strip()
    if git('rev-parse','HEAD')!=args.expected_commit or git('status','--porcelain'):parser.error('Exact clean committed target required')
    sys.path[:0]=[str(args.implementation_root/'python'),str(args.implementation_root/'python'/'tests')]
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120 second small-fixture worker cap')));signal.alarm(120)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegratedServiceTruth));signal.alarm(0)
    receipt=dict(status='passed' if result.wasSuccessful() else 'failed',target_commit=args.expected_commit,
        target=str(args.implementation_root),tests_run=result.testsRun,failures=[str(x) for x in result.failures],errors=[str(x) for x in result.errors],
        checks=RECEIPTS,real_million=False,rendered_ui=False,legacy_matching_epochs='unbounded/unqualified',
        code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.implementation_root/'python').glob('workspace_*.py')},
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runtime=dict(python=sys.version,sqlite=sqlite3.sqlite_version,platform=platform.platform()))
    args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()
