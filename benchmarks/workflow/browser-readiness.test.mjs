/** Readiness fault tests. Fake DOM only; no browser/server/large fixtures. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readiness,snapshotAction,assertFinalizedRequests,resetPreparation} from './browser.mjs';

function element(text='', attributes={}) {
  return {textContent:text, disabled:false, ...attributes,
    getBoundingClientRect:()=>({width:20,height:20}),
    getAttribute(name){return attributes[name]??null;}};
}
function setup(t, selectors={}) {
  const previous={window:globalThis.window,document:globalThis.document,getComputedStyle:globalThis.getComputedStyle};
  const w={active:{action_id:'current',intent:0,frames:0},requests:[],draws:[]};
  globalThis.window={__workflow:w};
  globalThis.document={body:{textContent:''},querySelectorAll:s=>selectors[s]||[],querySelector:s=>(selectors[s]||[])[0]||null};
  globalThis.getComputedStyle=()=>({visibility:'visible'});
  t.after(()=>{for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}});
  return w;
}

test('disabled matching button cannot borrow enabled state from shell button',t=>{
  setup(t,{button:[element('Edit Tree',{disabled:true}),element('Benchmark Main')]});
  assert.equal(readiness({selector:'button',text:'Edit Tree',enabled:true}),false);
});

test('correct result needs two observations and current nonbusy tree',t=>{
  const selectors={button:[element('Edit Tree')]};setup(t,selectors);
  const spec={selector:'button',text:'Edit Tree',enabled:true};
  assert.equal(readiness(spec),false);
  selectors['.column-tree[aria-busy="true"]']=[element()];
  assert.equal(readiness(spec),false);
  selectors['.column-tree[aria-busy="true"]']=[];
  // A busy observation must invalidate the earlier readiness streak.
  assert.equal(readiness(spec),false);
  assert.equal(readiness(spec),true);
});

test('old split labels cannot satisfy remove grouping action',t=>{
  setup(t,{'.tb-steps':[element('Recording date Cell Epoch block')],
    '.tb-steps [aria-label^="Reorder "]':[element('',{'aria-label':'Reorder Recording date, level 1'}),element('',{'aria-label':'Reorder Cell, level 2'}),element('',{'aria-label':'Reorder Epoch block, level 3'})]});
  assert.equal(readiness({selector:'.tb-steps',splitLabels:['Reorder Recording date, level 1','Reorder Cell, level 2']}),false);
});

test('same count but wrong epoch membership or ordering is not ready',t=>{
  setup(t,{'.epochs':[element('',{'data-epoch-uuid':'b'}),element('',{'data-epoch-uuid':'a'})]});
  assert.equal(readiness({selector:'.epochs',uuids:['a','b']}),false);
});

test('prior action response cannot satisfy current predicate submission',t=>{
  const w=setup(t,{'.results':[element()]});
  w.requests.push({action_id:'previous',url:'/api/explore/run',result:{matched_count:100},status:200});
  assert.equal(readiness({selector:'.results',requestPath:'/explore/run',expectedCount:100}),false);
});

function trace(t){
  const expected={epoch_uuid:'requested',stream_uuid:'response',start:0,count:2,sample_rate:10,units:'pA',values_first:1,values_last:2};
  const w=setup(t,{'.tv-base':[element()], '[aria-label="Response stream"]':[element('',{value:'response'})]});
  const request={action_id:'current',end:10,status:200,result:{...expected,values:[1,2]}};
  w.requests.push(request);w.draws.push({at:11,stream_uuid:'response'});
  return {w,request,spec:{selector:'.tv-base',trace:expected}};
}

test('trace rejects prior action response even with a fresh draw',t=>{
  const {request,spec}=trace(t);request.action_id='previous';
  assert.equal(readiness(spec),false);
});

test('trace rejects drawing before current response consumption',t=>{
  const {w,spec}=trace(t);w.draws[0].at=9;
  assert.equal(readiness(spec),false);
});

test('trace rejects wrong stream draw',t=>{
  const {w,spec}=trace(t);w.draws[0].stream_uuid='other';
  assert.equal(readiness(spec),false);
});

test('trace requires correct values and full requested window',t=>{
  const {request,spec}=trace(t);request.result.values=[1];
  assert.throws(()=>readiness(spec),/Incomplete/);
});

test('correct trace observations record current identity at readiness',t=>{
  const {w,spec}=trace(t);
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
  assert.equal(w.completed.current.evidence.trace.epoch_uuid,'requested');
  assert.equal(w.completed.current.evidence.trace.values_count,2);
});

test('predicate backend result cannot finish before membership is rendered',t=>{
  const w=setup(t,{'.results':[element()]});
  w.requests.push({action_id:'current',url:'/api/explore/epochs',status:200,result:{epochs:[{epoch_uuid:'a'}],total:1}});
  assert.equal(readiness({selector:'.results',searchUuids:['a']}),false);
});

test('predicate rejects wrong current result membership',t=>{
  const w=setup(t,{'.results':[element()],'.matching-epochs .inspection-cell-tree[data-inspection-membership-ready="true"]':[element()]});
  w.requests.push({action_id:'current',url:'/api/explore/epochs',status:200,result:{epochs:[{epoch_uuid:'wrong'}],total:1}});
  assert.equal(readiness({selector:'.results',searchUuids:['a']}),false);
});

function prepared(t){
  const w=setup(t,{button:[element('Select all')],'.incoming-browser .inspection-cell-tree[data-inspection-membership-ready="true"]':[element()]});
  const identity={candidate_revision_uuid:'candidate',queue_revision:'queue',candidate_scope_revision:'scope'};
  w.incomingSession={prepared:{...identity,context:{counts:{incoming_epochs:1}}},drafts:{candidate:{selected:[]}}};
  w.requests=[{action_id:'current',url:'/api/prepare',status:200,result:{...identity,reused:false}},
    {action_id:'current',url:'/api/epochs',status:200,result:{query_revision:'scope',epochs:[{epoch_uuid:'a'}],total:1}}];
  return {w,spec:{selector:'button',text:'Select all',enabled:true,requestPath:'/prepare',prepared:true,preparedUuids:['a'],expectedReused:false}};
}

test('prepare rejects an unrelated candidate even with ready-looking controls',t=>{
  const {w,spec}=prepared(t);w.incomingSession.prepared.candidate_revision_uuid='wrong';
  assert.equal(readiness(spec),false);
});

test('prepare must not silently select or merge the cohort',t=>{
  const {w,spec}=prepared(t);w.incomingSession.drafts.candidate.selected=['a'];
  assert.throws(()=>readiness(spec),/silently selected or merged/);
});

test('positive prepared cohort cannot use empty first-page evidence',t=>{
  const {w,spec}=prepared(t);w.requests[1].result.epochs=[];
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});

test('predicate first page cannot be an arbitrary correct prefix',t=>{
  const w=setup(t,{'.results':[element()],'.matching-epochs .inspection-cell-tree[data-inspection-membership-ready="true"]':[element()]});
  w.requests.push({action_id:'current',url:'/api/explore/epochs',status:200,result:{epochs:[{epoch_uuid:'a'}],total:2}});
  const spec={selector:'.results',searchUuids:['a','b']};
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});

test('prepared first page cannot be an arbitrary correct prefix',t=>{
  const {w,spec}=prepared(t);spec.preparedUuids=['a','b'];
  w.incomingSession.prepared.context.counts.incoming_epochs=2;w.requests[1].result.total=2;
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});

test('return to prepared review checks retained candidate identity',t=>{
  const {w,spec}=prepared(t);delete spec.prepared;delete spec.requestPath;
  spec.savedPrepared={candidate_revision_uuid:'other',queue_revision:'queue',candidate_scope_revision:'scope'};
  assert.equal(readiness(spec),false);
});

test('return to prepared review accepts exact current page and retained identity',t=>{
  const {spec}=prepared(t);delete spec.prepared;delete spec.requestPath;
  spec.savedPrepared={candidate_revision_uuid:'candidate',queue_revision:'queue',candidate_scope_revision:'scope'};
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
});


test('readiness atomically closes action capture and excludes later requests',t=>{
  const w=setup(t,{button:[element('Ready')]});
  const first={action_id:'current',start:0,method:'GET',url:'/api/current'};
  w.requests.push(first);
  const spec={selector:'button',text:'Ready'};
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
  assert.equal(w.active,null);
  assert.equal(w.last_completed_action_id,'current');
  const observed=JSON.parse(JSON.stringify(snapshotAction('current')));
  assert.equal(observed.requests.length,1);assert.equal(observed.requests[0].end_ms,null);
  assert.throws(()=>assertFinalizedRequests(observed),/correlation/);
  w.requests.push({action_id:'current',start:w.completed.current.ready+1,url:'/api/late'});
  Object.assign(first,{request_id:'one',status:200,end:w.completed.current.ready+10});
  const finalized=snapshotAction('current');
  assert.equal(finalized.requests.length,1);
  assert.equal(finalized.total_ms,observed.total_ms);
  assert.equal(finalized.frontend_spans[0].end_ms,finalized.total_ms);
  assert.equal(finalized.frontend_spans[0].clipped_at_ready,true);
  assertFinalizedRequests(finalized);
  assert.equal(observed.requests[0].end_ms,null,'persisted observation remains a pending snapshot');
});

test('strict finalization refuses missing IDs, request failure and incomplete bodies',()=>{
  const sample={action_id:'x',requests:[{action_id:'x',request_id:'r',status:200,end_ms:1}]};
  assertFinalizedRequests(sample);
  sample.requests[0].end_ms=null;
  assert.throws(()=>assertFinalizedRequests(sample),/incomplete/);
  sample.requests[0].end_ms=1;sample.requests[0].status=500;
  assert.throws(()=>assertFinalizedRequests(sample),/Failed/);
  sample.requests[0].status=200;sample.requests[0].request_id=null;
  assert.throws(()=>assertFinalizedRequests(sample),/correlation/);
});


test('fresh preparation cannot admit a reused backend workload',t=>{
  const {w,spec}=prepared(t);w.requests[0].result.reused=true;
  assert.throws(()=>readiness(spec),/reuse classification/);
});

test('reuse preparation requires reuse and the same prepared candidate',t=>{
  const {w,spec}=prepared(t);spec.expectedReused=true;spec.expectedCandidate='candidate';
  assert.throws(()=>readiness(spec),/reuse classification/);
  w.requests[0].result.reused=true;spec.expectedCandidate='other';
  assert.throws(()=>readiness(spec),/changed candidate/);
  spec.expectedCandidate='candidate';
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
});


test('receipt replay must retain operation identity and use replay HTTP status',t=>{
  const {w,spec}=prepared(t);spec.expectedOperation='original';spec.expectedPrepareStatus=200;
  w.requests[0].result.operation_uuid='different';
  assert.throws(()=>readiness(spec),/changed operation/);
  w.requests[0].result.operation_uuid='original';w.requests[0].status=201;
  assert.throws(()=>readiness(spec),/HTTP status/);
  w.requests[0].status=200;assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
});


test('owned preparation reset retries only explicit busy refusal and records setup',async t=>{
  const previous=globalThis.fetch;t.after(()=>{globalThis.fetch=previous;});let calls=0;
  const meta={fixture:'workflow-owned-v2',port:1234,epochs:1000,main_count:900,incoming_count:100};
  globalThis.fetch=async(url,options)=>{assert.equal(url,'http://127.0.0.1:1234/__benchmark__/reset-preparation');assert.equal(options.headers['X-Workspace-Request'],'1');calls++;return calls===1?{status:409,ok:false,text:async()=>'Other owned fixture requests are still active'}:{status:200,ok:true,text:async()=>JSON.stringify({reset:true,ready:true,epochs:1000,main_count:900,incoming_count:100})};};
  const result=await resetPreparation(meta,{timeoutMs:3000});assert.equal(result.attempts,2);assert.equal(result.included_in_headline,false);
});

test('owned preparation reset never retries changed authority or wrong counts',async t=>{
  const previous=globalThis.fetch;t.after(()=>{globalThis.fetch=previous;});let calls=0;
  const meta={fixture:'workflow-owned-v2',port:1234,epochs:1000,main_count:900,incoming_count:100};
  globalThis.fetch=async()=>{calls++;return {status:409,ok:false,text:async()=>'Main/source/annotation authority changed; refusing reset'};};
  await assert.rejects(resetPreparation(meta),/changed/);assert.equal(calls,1);
  globalThis.fetch=async()=>({status:200,ok:true,text:async()=>JSON.stringify({reset:true,ready:true,epochs:1000,main_count:899,incoming_count:100})});
  await assert.rejects(resetPreparation(meta),/did not attest/);
});
