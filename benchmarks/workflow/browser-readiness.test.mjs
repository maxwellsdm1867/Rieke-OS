/** Readiness fault tests. Fake DOM only; no browser/server/large fixtures. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readiness} from './browser.mjs';

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
  assert.equal(w.active.evidence.trace.epoch_uuid,'requested');
  assert.equal(w.active.evidence.trace.values_count,2);
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
  w.requests=[{action_id:'current',url:'/api/prepare',status:200,result:{...identity}},
    {action_id:'current',url:'/api/epochs',status:200,result:{query_revision:'scope',epochs:[{epoch_uuid:'a'}],total:1}}];
  return {w,spec:{selector:'button',text:'Select all',enabled:true,requestPath:'/prepare',prepared:true,preparedUuids:['a']}};
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
