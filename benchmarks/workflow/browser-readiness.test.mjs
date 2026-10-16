/** Readiness fault tests. Fake DOM only; no browser/server/large fixtures. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readiness,snapshotAction,assertFinalizedRequests,resetPreparation,options,phasePlan,moduleTimingEnabled,armAction,observationFinished} from './browser.mjs';
import {installObserver,installTraceControlReader,installBinaryTraceOracle} from './fixture-app.mjs';

function element(text='', attributes={}) {
  return {textContent:text, disabled:false, ...attributes,
    getBoundingClientRect:()=>({width:20,height:20}),
    querySelectorAll:selector=>attributes.children?.[selector]||[],
    getAttribute(name){return attributes[name]??null;}};
}
function setup(t, selectors={}, streams=[{uuid:'response',device:'Amp1',units:'pA'}]) {
  const previous={window:globalThis.window,document:globalThis.document,getComputedStyle:globalThis.getComputedStyle};
  const w={active:{action_id:'current',intent:0,frames:0},requests:[],draws:[]};
  globalThis.window={__workflow:w};
  globalThis.document={body:{textContent:''},querySelectorAll:s=>selectors[s]||[],querySelector:s=>(selectors[s]||[])[0]||null};
  globalThis.getComputedStyle=()=>({visibility:'visible'});
  installTraceControlReader({streams});
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

function trace(t, control=element('',{tagName:'SELECT',value:'response'}),streams){
  const expected={epoch_uuid:'requested',stream_uuid:'response',start:0,count:2,sample_rate:10,units:'pA',values_first:1,values_last:2};
  const w=setup(t,{'.tv-base':[element()], '[aria-label="Response stream"]':[control]},streams);
  const request={action_id:'current',end:10,status:200,result:{...expected,values:[1,2]}};
  w.requests.push(request);w.draws.push({at:11,action_id:'current',stream_uuid:'response'});
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

test('single-stream label uses the independent fixture identity',t=>{
  const {w,spec}=trace(t,element('Amp1 · pA',{tagName:'DIV',children:{span:[element('Amp1 · pA')]}}));
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
  assert.equal(w.completed.current.trace_control.kind,'single-label');
});

test('multiple-stream buttons require one exact pressed UUID',t=>{
  const streams=[{uuid:'other',device:'Amp2',units:'mV'},{uuid:'response',device:'Amp1',units:'pA'}];
  const buttons=streams.map(row=>element(row.device,{title:row.uuid,'aria-pressed':String(row.uuid==='response')}));
  const {w,spec}=trace(t,element('',{tagName:'DIV',children:{button:buttons}}),streams);
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
  assert.equal(w.completed.current.trace_control.kind,'buttons');
});

for(const [name,control,streams] of [
  ['obsolete value assumption',element('',{tagName:'DIV',value:'response'})],
  ['wrong single-stream label',element('',{tagName:'DIV',children:{span:[element('Amp2 · mV')]}})],
  ['ambiguous single-stream identity',element('',{tagName:'DIV',children:{span:[element('Amp1 · pA')]}}),[{uuid:'response'},{uuid:'other'}]],
  ['unknown pressed UUID',element('',{tagName:'DIV',children:{button:[element('',{title:'wrong','aria-pressed':'true'})]}})],
])test(`trace fails promptly for ${name}`,t=>{
  const {spec}=trace(t,control,streams);
  assert.throws(()=>readiness(spec),/Harness incompatible with Response stream/);
});

for(const key of ['epoch_uuid','stream_uuid'])test(`trace cannot borrow wrong ${key}`,t=>{
  const {request,spec}=trace(t);request.result[key]='wrong';
  assert.equal(readiness(spec),false);
});
for(const key of ['start','count','sample_rate','units'])test(`trace refuses incorrect ${key}`,t=>{
  const {request,spec}=trace(t);request.result[key]='wrong';
  assert.throws(()=>readiness(spec),new RegExp('Trace mismatch '+key));
});
test('trace refuses incorrect waveform values and prior-action drawings',t=>{
  const {w,request,spec}=trace(t);request.result.values=[99,2];
  assert.throws(()=>readiness(spec),/Incorrect first waveform sample/);
  request.result.values=[1,2];w.draws[0].action_id='previous';
  assert.equal(readiness(spec),false);
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
  const meta={fixture:'workflow-owned-v4',port:1234,epochs:1000,main_count:900,incoming_count:100};
  globalThis.fetch=async(url,options)=>{assert.equal(url,'http://127.0.0.1:1234/__benchmark__/reset-preparation');assert.equal(options.headers['X-Workspace-Request'],'1');calls++;return calls===1?{status:409,ok:false,text:async()=>'Other owned fixture requests are still active'}:{status:200,ok:true,text:async()=>JSON.stringify({reset:true,ready:true,epochs:1000,main_count:900,incoming_count:100})};};
  const result=await resetPreparation(meta,{timeoutMs:3000});assert.equal(result.attempts,2);assert.equal(result.included_in_headline,false);
});

test('owned preparation reset never retries changed authority or wrong counts',async t=>{
  const previous=globalThis.fetch;t.after(()=>{globalThis.fetch=previous;});let calls=0;
  const meta={fixture:'workflow-owned-v4',port:1234,epochs:1000,main_count:900,incoming_count:100};
  globalThis.fetch=async()=>{calls++;return {status:409,ok:false,text:async()=>'Main/source/annotation authority changed; refusing reset'};};
  await assert.rejects(resetPreparation(meta),/changed/);assert.equal(calls,1);
  globalThis.fetch=async()=>({status:200,ok:true,text:async()=>JSON.stringify({reset:true,ready:true,epochs:1000,main_count:899,incoming_count:100})});
  await assert.rejects(resetPreparation(meta),/did not attest/);
});


test('browser CLI defaults to ordinary-only and supports explicit profile boolean',()=>{
  const required=['--source-root','source','--server-json','server.json','--output','output'];
  const defaults=options(required);
  assert.equal(defaults.profile,false);
  assert.deepEqual(phasePlan(defaults),[{phase:'ordinary',samples:3}]);
  const disabled=options([...required,'--profile','false','--samples','2']);
  assert.deepEqual(phasePlan(disabled),[{phase:'ordinary',samples:2}]);
  assert.throws(()=>options([...required,'--profile','true']),/requires explicit --runtime development/);
  const enabled=options([...required,'--runtime','development','--profile','true','--samples','2']);
  assert.equal(enabled.profile,true);
  assert.deepEqual(phasePlan(enabled),[{phase:'ordinary',samples:2},{phase:'profile',samples:1}]);
  assert.throws(()=>options([...required,'--profile','yes']),/true or false/);
});

test('direct browser phase plan never enables profiling from an omitted or false setting',()=>{
  assert.deepEqual(phasePlan({samples:3}),[{phase:'ordinary',samples:3}]);
  assert.deepEqual(phasePlan({samples:3,profile:false,profile_samples:5}),[{phase:'ordinary',samples:3}]);
  assert.deepEqual(phasePlan({samples:3,profile:true,profile_samples:2}),[{phase:'ordinary',samples:3},{phase:'profile',samples:2}]);
  assert.throws(()=>phasePlan({samples:3,profile:true,profile_samples:0}),/positive/);
  assert.throws(()=>phasePlan({samples:3,profile:'enabled'}),/true or false/);
});


test('lightweight module timing is independently opt-in and adds no profiling phase',()=>{
  const required=['--source-root','source','--server-json','server.json','--output','output'];
  assert.equal(options(required).module_timing,false);
  assert.equal(options([...required,'--module-timing','false']).module_timing,false);
  const enabled=options([...required,'--module-timing','true']);
  assert.equal(enabled.module_timing,true);assert.equal(enabled.profile,false);
  assert.deepEqual(phasePlan(enabled),[{phase:'ordinary',samples:3}]);
  assert.equal(moduleTimingEnabled(),false);assert.equal(moduleTimingEnabled(true),true);
  assert.throws(()=>options([...required,'--module-timing','yes']),/true or false/);
});

test('observer sends lightweight timing header only when enabled and keeps action correlation',async t=>{
  const previous={window:globalThis.window,location:globalThis.location,CanvasRenderingContext2D:globalThis.CanvasRenderingContext2D};
  t.after(()=>{for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}});
  for(const enabled of [false,true]){
    const calls=[];
    globalThis.CanvasRenderingContext2D=class {stroke(){}};
    globalThis.location={href:'http://127.0.0.1:1234/__workflow__'};
    globalThis.window={fetch:async(input,options={})=>{calls.push({input,headers:new Headers(options.headers)});return new Response('{}',{headers:{'X-Benchmark-Request-Id':'request'}});}};
    installObserver({phase:'ordinary',module_timing:enabled});
    assert.equal(window.__workflow.profile,false);
    window.__workflow.active={action_id:'ordinary-action',phase:'ordinary'};
    await (await window.fetch('/api/epochs')).json();
    assert.equal(calls[0].headers.get('X-Disco-Timing'),enabled?'1':null);
    assert.equal(calls[0].headers.get('X-Benchmark-Action'),'ordinary-action');
    assert.equal(calls[0].headers.get('X-Benchmark-Profile'),'0');
    window.__workflow.active=null;
    await (await window.fetch('/api/setup')).json();
    assert.equal(calls[1].headers.get('X-Disco-Timing'),enabled?'1':null);
    assert.equal(calls[1].headers.get('X-Benchmark-Action'),null);
    await window.fetch('/assets/example.js');
    assert.equal(calls[2].headers.get('X-Disco-Timing'),null);
  }
});

function combinedPrepared(t,{returning=false}={}){
  const fixture=prepared(t),{w,spec}=fixture;
  const saved=w.incomingSession.prepared;
  saved.root='/protocols/protocol/workbench/candidates/candidate';saved.actor='actor';
  Object.assign(saved.context,{publication_blocked:false,candidate_revision_uuid:'candidate',candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,
    generation:{metadata:'metadata',binding:'binding'},protocol:{definition:{protocol_uuid:'protocol',project_uuid:'project'},query_revision:'scope',expected_binding_version:2}});
  const bootstrap={contract_version:1,kind:'workbench_initial_page',root:saved.root,actor:'actor',protocol_uuid:'protocol',project_uuid:'project',candidate_revision_uuid:'candidate',
    request:{filters:{},offset:0,limit:60,include_cells:true},context:structuredClone(saved.context),
    page:{candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,generation:{metadata:'metadata',binding:'binding'},total:1,offset:0,limit:60,epochs:[{epoch_uuid:'a',cell_uuid:'cell'}],cells:[{cell_uuid:'cell',epochs:1}]}};
  w.requests.splice(1);
  Object.assign(w.requests[0],{start:0,end:1,request_id:'combined',method:returning?'GET':'POST',url:returning?'/api'+saved.root+'/context?include_initial_page=true':'/api/protocols/protocol/workbench/prepare?include_initial_page=true'});
  w.requests[0].result.bootstrap=bootstrap;
  if(returning){delete spec.prepared;delete spec.requestPath;spec.savedPrepared={candidate_revision_uuid:'candidate',candidate_scope_revision:'scope',queue_revision:'queue'};}
  return {...fixture,bootstrap};
}

for(const returning of [false,true])test(`combined ${returning?'return context':'prepare'} accepts the exact page after two visible observations without a fabricated request`,t=>{
  const {w,spec}=combinedPrepared(t,{returning});
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
  assert.equal(w.requests.length,1);assert.equal(w.completed.current.captured_requests.length,1);
  assert.match(w.completed.current.captured_requests[0].url,returning?/\/context\?/:/\/prepare\?/);
});

test('combined receipt replay keeps reuse operation and HTTP status assertions',t=>{
  const {w,spec}=combinedPrepared(t);Object.assign(spec,{expectedReused:true,expectedOperation:'operation',expectedCandidate:'candidate',expectedPrepareStatus:200});
  Object.assign(w.requests[0].result,{reused:true,operation_uuid:'operation'});
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
  assert.equal(w.completed.current.evidence.prepared.operation_uuid,'operation');
});

const bootstrapFaults={
  version:b=>{b.contract_version=2;},kind:b=>{b.kind='other';},root:b=>{b.root='/other';},
  candidate:b=>{b.candidate_revision_uuid='other';},project:b=>{b.project_uuid='other';},protocol:b=>{b.protocol_uuid='other';},actor:b=>{b.actor='other';},
  contextCount:b=>{b.context.counts.incoming_epochs=2;},blocked:b=>{b.context.publication_blocked=true;},
  contextCandidate:b=>{b.context.candidate_revision_uuid='other';},contextScope:b=>{b.context.candidate_scope_revision='other';},
  contextQuery:b=>{b.context.query_revision='other';},contextProtocol:b=>{b.context.protocol.definition.protocol_uuid='other';},
  contextBinding:b=>{b.context.expected_binding_version=3;},pageBinding:b=>{b.page.expected_binding_version=3;},
  pageScope:b=>{b.page.candidate_scope_revision='other';},pageQuery:b=>{b.page.query_revision='other';},
  pageGeneration:b=>{b.page.generation.metadata='other';},missingGeneration:b=>{delete b.context.generation;},
  offset:b=>{b.page.offset=1;},limit:b=>{b.page.limit=1;},total:b=>{b.page.total=2;},truncated:b=>{b.page.epochs=[];},
  wrongUuid:b=>{b.page.epochs[0].epoch_uuid='wrong';},unknownCell:b=>{b.page.epochs[0].cell_uuid='other';},
  missingCells:b=>{delete b.page.cells;},wrongCellCount:b=>{b.page.cells[0].epochs=2;},
  requestFilters:b=>{b.request.filters={cell_uuid:'other'};},requestOffset:b=>{b.request.offset=1;},requestCells:b=>{b.request.include_cells=false;},
};
for(const [name,mutate] of Object.entries(bootstrapFaults))test(`combined page refuses ${name}`,t=>{
  const {spec,bootstrap}=combinedPrepared(t,{returning:true});mutate(bootstrap);
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});
for(const fault of ['prior-action','unrelated-endpoint','wrong-candidate-endpoint'])test(`combined page cannot borrow ${fault} evidence`,t=>{
  const {w,spec}=combinedPrepared(t,{returning:true});
  if(fault==='prior-action')w.requests[0].action_id='previous';
  else w.requests[0].url=fault==='unrelated-endpoint'?'/api/unrelated':'/api/protocols/protocol/workbench/candidates/other/context';
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});
for(const fault of ['permuted','duplicate'])test(`combined first page refuses ${fault} UUIDs`,t=>{
  const {spec,bootstrap}=combinedPrepared(t,{returning:true});spec.preparedUuids=['a','b'];bootstrap.context.counts.incoming_epochs=2;bootstrap.page.total=2;bootstrap.page.cells[0].epochs=2;
  bootstrap.page.epochs=(fault==='permuted'?['b','a']:['a','a']).map(epoch_uuid=>({epoch_uuid,cell_uuid:'cell'}));
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});
test('combined backend evidence cannot finish before incoming membership is rendered',t=>{
  const {spec}=combinedPrepared(t);const query=globalThis.document.querySelector;
  globalThis.document.querySelector=selector=>selector.includes('data-inspection-membership-ready')?null:query(selector);
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});

for(const key of ['candidate_revision_uuid','candidate_scope_revision'])test(`combined context envelope refuses mismatched ${key}`,t=>{
  const {w,spec}=combinedPrepared(t,{returning:true});w.requests[0].result[key]='other';
  assert.equal(readiness(spec),false);assert.equal(readiness(spec),false);
});

function longTrace(t){
  const {w,spec}=trace(t);const root='/protocols/p/workbench/candidates/c';
  Object.assign(spec,{traceRoot:root,traceRevision:'revision'});
  Object.assign(spec.trace,{start:0,count:300000,values_first:0,values_last:299999,ramp:true,source_sha256:'source'});
  w.requests=Array.from({length:3},(_,i)=>({action_id:'current',status:200,end:10+i,url:'/api'+root+'/epochs/requested/trace?candidate_scope_revision=revision',result:{epoch_uuid:'requested',stream_uuid:'response',start:i*100000,count:100000,sample_rate:10,units:'pA',source_sha256:'source',total_samples:300000,decimated:false,values:Array.from({length:100000},(_,n)=>i*100000+n)}}));
  w.draws=[{at:13,action_id:'current',stream_uuid:'response'}];return {w,spec};
}
test('frozen 300k trace requires every exact consecutive chunk before final drawing',t=>{
 const {w,spec}=longTrace(t),last=w.requests.pop();
 assert.equal(readiness(spec),false);w.requests.push(last);
 assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
 assert.equal(w.completed.current.evidence.trace.values_count,300000);
 assert.equal(w.completed.current.evidence.trace.chunks,3);
 assert.equal(w.completed.current.evidence.trace.candidate_scope_revision,'revision');
});
for(const defect of ['scope','gap','overlap','source','interior sample','draw'])test('long trace rejects '+defect,t=>{
 const {w,spec}=longTrace(t),r=w.requests[1];
 if(defect==='scope')r.url=r.url.replace('revision=revision','revision=stale');
 if(defect==='gap')r.result.start++;
 if(defect==='overlap')r.result.start--;
 if(defect==='source')r.result.source_sha256='wrong';
 if(defect==='interior sample')r.result.values[123]=0;
 if(defect==='draw'){w.draws[0].at=11;assert.equal(readiness(spec),false);}
 else assert.throws(()=>readiness(spec),/mismatch|Incorrect/);
});

test('300k frozen batch validates envelope and all windows before one-request drawing',t=>{
 const {w,spec}=longTrace(t),windows=w.requests.map(r=>r.result),r=w.requests[0];
 r.result={...windows[0],values:undefined,count:300000,candidate_scope_revision:'revision',windows};r.end=12;w.requests=[r];
 assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
 assert.equal(w.completed.current.evidence.trace.requests,1);assert.equal(w.completed.current.evidence.trace.chunks,3);
});
for(const defect of ['scope','header','missing'])test('long batch refuses '+defect,t=>{
 const {w,spec}=longTrace(t),windows=w.requests.map(r=>({...r.result})),r=w.requests[0];
 r.result={...windows[0],values:undefined,count:300000,candidate_scope_revision:'revision',windows};w.requests=[r];
 if(defect==='scope')r.result.candidate_scope_revision='stale';
 if(defect==='header')windows[1].source_sha256='wrong';
 if(defect==='missing')windows.pop();
 assert.throws(()=>readiness(spec),/batch .*mismatch/);
});

// Wire fixtures are constructed independently of product codecs.
function binaryFixture(){
 const base={epoch_uuid:'epoch',stream_uuid:'response',source_sha256:'a'.repeat(64),sample_rate:10,units:'pA',total_samples:3,decimated:false};
 return {header:{...base,start:0,count:3,candidate_scope_revision:'revision',windows:[{...base,start:0,count:2,byte_offset:0,byte_length:16},{...base,start:2,count:1,byte_offset:16,byte_length:8}]},values:[-0,Math.PI,Number.MIN_VALUE]};
}
function wire(header,values){
 const text=new TextEncoder().encode(JSON.stringify(header)),offset=Math.ceil((8+text.length)/8)*8,buffer=new ArrayBuffer(offset+values.length*8),view=new DataView(buffer);
 new Uint8Array(buffer).set([68,84,70,49]);view.setUint32(4,text.length,true);new Uint8Array(buffer).set(text,8);values.forEach((value,i)=>view.setFloat64(offset+i*8,value,true));return buffer;
}
test('independent binary oracle preserves exact finite doubles and signed zero',t=>{
 setup(t);installBinaryTraceOracle();const {header,values}=binaryFixture(),result=window.__workflowDecodeBinaryTrace(wire(header,values));
 assert(result.windows[0].values instanceof Float64Array);assert(Object.is(result.windows[0].values[0],-0));assert.equal(result.windows[0].values[1],Math.PI);assert.equal(result.windows[1].values[0],Number.MIN_VALUE);
});
for(const defect of ['magic','length','padding','trailing','offset','missing','source','count','nan'])test('independent binary oracle refuses '+defect,t=>{
 setup(t);installBinaryTraceOracle();const {header,values}=binaryFixture();
 if(defect==='offset')header.windows[1].byte_offset=8;
 if(defect==='missing')header.windows.pop();
 if(defect==='source')header.windows[1].source_sha256='b'.repeat(64);
 if(defect==='count')header.count=1000001;
 if(defect==='nan')values[1]=NaN;
 let buffer=wire(header,values),view=new DataView(buffer);
 if(defect==='magic')view.setUint8(0,0);
 if(defect==='length')view.setUint32(4,65537,true);
 if(defect==='padding'){const at=8+view.getUint32(4,true);assert(at%8);view.setUint8(at,1);}
 if(defect==='trailing'){const extra=new Uint8Array(buffer.byteLength+8);extra.set(new Uint8Array(buffer));buffer=extra.buffer;}
 assert.throws(()=>window.__workflowDecodeBinaryTrace(buffer),/Invalid binary/);
});

test('million-sample gate admits exactly two bounded binary batches only after every sample and final draw',t=>{
 const {w,spec}=longTrace(t);installBinaryTraceOracle();
 Object.assign(spec.trace,{count:1000000,values_last:999999,source_sha256:'a'.repeat(64)});
 const root=spec.traceRoot;w.requests=[];
 for(let batch=0;batch<2;batch++){
  const base={epoch_uuid:'requested',stream_uuid:'response',source_sha256:'a'.repeat(64),sample_rate:10,units:'pA',total_samples:1000000,decimated:false};
  const header={...base,start:batch*500000,count:500000,candidate_scope_revision:'revision',windows:Array.from({length:5},(_,i)=>({...base,start:batch*500000+i*100000,count:100000,byte_offset:i*800000,byte_length:800000}))};
  w.requests.push({action_id:'current',status:200,end:10+batch,url:'/api'+root+'/epochs/requested/trace?candidate_scope_revision=revision',content_type:'application/vnd.disco.trace-f64le.v1',binary:wire(header,Array.from({length:500000},(_,i)=>batch*500000+i))});
 }
 const second=w.requests.pop();assert.equal(readiness(spec),false);w.requests.push(second);
 w.draws=[{at:12,action_id:'current',stream_uuid:'response'}];
 assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
 const result=w.completed.current.evidence.trace;assert.equal(result.values_count,1000000);assert.equal(result.chunks,10);assert.equal(result.requests,2);
});

function millionBinaryBatch(total=1000000){
 const base={epoch_uuid:'requested',stream_uuid:'response',source_sha256:'a'.repeat(64),sample_rate:10,units:'pA',total_samples:total,decimated:false};
 const header={...base,start:0,count:total,candidate_scope_revision:'revision',windows:Array.from({length:Math.ceil(total/100000)},(_,i)=>({...base,start:i*100000,count:Math.min(100000,total-i*100000),byte_offset:i*800000,byte_length:Math.min(100000,total-i*100000)*8}))};
 return {header,values:Float64Array.from({length:total},(_,i)=>i)};
}
test('million-sample gate admits one bounded ten-window binary response only after every sample and final draw',t=>{
 const {w,spec}=longTrace(t);installBinaryTraceOracle();
 Object.assign(spec.trace,{count:1000000,values_last:999999,source_sha256:'a'.repeat(64)});
 const {header,values}=millionBinaryBatch();
 w.requests=[{action_id:'current',status:200,end:10,url:'/api'+spec.traceRoot+'/epochs/requested/trace?candidate_scope_revision=revision',content_type:'application/vnd.disco.trace-f64le.v1',binary:wire(header,values)}];
 w.draws=[];assert.equal(readiness(spec),false);
 w.draws=[{at:12,action_id:'current',stream_uuid:'response'}];
 assert.equal(readiness(spec),false);assert.equal(readiness(spec),true);
 const result=w.completed.current.evidence.trace;assert.equal(result.values_count,1000000);assert.equal(result.chunks,10);assert.equal(result.requests,1);
});
test('single million-sample binary gate rejects an incorrect interior sample',t=>{
 const {w,spec}=longTrace(t);installBinaryTraceOracle();
 Object.assign(spec.trace,{count:1000000,values_last:999999,source_sha256:'a'.repeat(64)});
 const {header,values}=millionBinaryBatch();values[500001]=-123;
 w.requests=[{action_id:'current',status:200,end:10,url:'/api'+spec.traceRoot+'/epochs/requested/trace?candidate_scope_revision=revision',content_type:'application/vnd.disco.trace-f64le.v1',binary:wire(header,values)}];
 assert.throws(()=>readiness(spec),/Incorrect waveform sample/);
});
test('independent binary oracle refuses a complete response exceeding one million samples',t=>{
 setup(t);installBinaryTraceOracle();const {header,values}=millionBinaryBatch(1000001);
 assert.throws(()=>window.__workflowDecodeBinaryTrace(wire(header,values)),/Invalid binary/);
});
test('independent binary oracle refuses more than ten windows even below the sample limit',t=>{
 setup(t);installBinaryTraceOracle();const {header}=millionBinaryBatch(11),base=header.windows[0];
 header.windows=Array.from({length:11},(_,i)=>({...base,start:i,count:1,byte_offset:i*8,byte_length:8}));
 assert.throws(()=>window.__workflowDecodeBinaryTrace(wire(header,Float64Array.from({length:11},(_,i)=>i))),/Invalid binary/);
});

// Deterministic browser frame/clock model: each step executes only the RAFs
// queued before that frame. Driver retrieval can be delayed independently.
function actionClock(t,selectors){
  const w=setup(t,selectors);w.active=null;w.completed={};window.__workflowReadiness=readiness;
  const keys=['performance','requestAnimationFrame','cancelAnimationFrame','setTimeout','clearTimeout'];
  const previous=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
  let now=100,id=0;const frames=new Map(),timers=new Map();
  Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>now}});
  globalThis.requestAnimationFrame=fn=>{frames.set(++id,fn);return id;};
  globalThis.cancelAnimationFrame=id=>frames.delete(id);
  globalThis.setTimeout=(fn,delay)=>{timers.set(++id,{fn,at:now+delay});return id;};
  globalThis.clearTimeout=id=>timers.delete(id);
  t.after(()=>{for(const k of keys){if(previous[k])Object.defineProperty(globalThis,k,previous[k]);else delete globalThis[k];}});
  return {w,frames,timers,advance(ms){now+=ms;for(const [id,v] of [...timers])if(v.at<=now){timers.delete(id);v.fn();}},frame(){now+=16;const batch=[...frames.values()];frames.clear();for(const fn of batch)fn(now);}};
}
const armData=spec=>({action_id:'owned',phase:'ordinary',spec,timeoutMs:1000});

test('prearmed oracle completes on two distinct RAFs before a delayed driver returns',async t=>{
  const selectors={'.epochs':[]},clock=actionClock(t,selectors),{w}=clock;
  const el={isConnected:true,disabled:false,click(){
    assert.equal(clock.frames.size,1,'observer is scheduled before click');
    assert.ok(w.active.observer_armed_at<=w.active.intent);
    selectors['.epochs']=[element('',{'data-epoch-uuid':'a'})];
  }};
  await armAction(el,armData({selector:'.epochs',uuids:['a']}));
  assert.equal(w.active.frames,0,'no synchronous readiness observation');
  clock.frame();assert.equal(w.active.frames,1);assert.equal(w.completed.owned,undefined);
  clock.frame();assert.equal(w.active,null);assert.equal(w.completed.owned.observer_raf_count,2);
  const ready=w.completed.owned.ready;clock.advance(160);
  assert.equal(observationFinished('owned'),true);
  const result=snapshotAction('owned');
  assert.equal(result.total_ms,32);assert.equal(result.observer.driver_retrieval_lag_ms,160);
  assert.equal(result.observer.first_correct_ms,16);assert.equal(w.completed.owned.ready,ready);
  assert.deepEqual(result.correctness.uuids,['a']);assert.equal(clock.frames.size,0);assert.equal(clock.timers.size,0);
});

test('a correct one-frame flash cannot complete and a pending frame resets the streak',async t=>{
  const selectors={'.epochs':[element('',{'data-epoch-uuid':'a'})]},clock=actionClock(t,selectors);
  await armAction({isConnected:true,click(){}},armData({selector:'.epochs',uuids:['a']}));
  clock.frame();selectors['.epochs']=[];clock.frame();
  assert.equal(clock.w.completed.owned,undefined);assert.equal(clock.w.active.frames,0);
  selectors['.epochs']=[element('',{'data-epoch-uuid':'a'})];clock.frame();
  assert.equal(clock.w.completed.owned,undefined);clock.frame();
  assert.equal(clock.w.completed.owned.ready-clock.w.completed.owned.intent,64);
});

test('prearmed checks preserve exact membership order and current-action response freshness',async t=>{
  const selectors={'.epochs':[element('',{'data-epoch-uuid':'b'}),element('',{'data-epoch-uuid':'a'})]},clock=actionClock(t,selectors);
  clock.w.requests.push({action_id:'old',url:'/api/query',result:{count:2}});
  await armAction({isConnected:true,click(){}},armData({selector:'.epochs',uuids:['a','b'],requestPath:'/query',expectedCount:2}));
  clock.frame();clock.frame();assert.equal(clock.w.active.frames,0);
  selectors['.epochs'].reverse();clock.frame();assert.equal(clock.w.active.frames,0,'old response cannot satisfy current action');
  clock.w.requests.push({action_id:'owned',request_id:'fresh',url:'/api/query',status:200,start:100,end:148,result:{count:2}});
  clock.frame();assert.equal(clock.w.completed.owned,undefined);clock.frame();
  const result=snapshotAction('owned');assertFinalizedRequests(result);
  assert.deepEqual(result.correctness.uuids,['a','b']);assert.deepEqual(result.correctness.response,{count:2});
  assert.equal(result.requests.length,1);assert.equal(result.requests[0].request_id,'fresh');
});

test('prearmed oracle failures propagate and cancel polling',async t=>{
  const clock=actionClock(t,{button:[element('Ready')]});
  clock.w.requests.push({action_id:'owned',url:'/api/query',status:500,error:'failed'});
  await armAction({isConnected:true,click(){}},armData({selector:'button'}));clock.frame();
  assert.throws(()=>observationFinished('owned'),/Action API request failed/);
  assert.equal(clock.frames.size,0);assert.equal(clock.timers.size,0);assert.equal(clock.w.completed.owned,undefined);
});

test('prearmed readiness has a page-owned timeout even without another driver call',async t=>{
  const clock=actionClock(t,{});
  await armAction({isConnected:true,click(){}},armData({selector:'button'}));
  clock.advance(1001);assert.throws(()=>observationFinished('owned'),/readiness timed out/);
  assert.equal(clock.frames.size,0);assert.equal(clock.timers.size,0);
});

test('prearmed readiness refuses changed action ownership',async t=>{
  const clock=actionClock(t,{button:[element('Ready')]});
  await armAction({isConnected:true,click(){}},armData({selector:'button'}));
  clock.w.active={action_id:'replacement',frames:0};clock.frame();
  assert.throws(()=>observationFinished('owned'),/ownership changed/);assert.equal(clock.w.active.action_id,'replacement');
});
