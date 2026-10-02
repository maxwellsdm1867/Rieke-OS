import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

async function setup(){
 const h=await createWorkflowHarness();
 h.fixture.respond=(url,options,fallback)=>{
  const route=url.pathname.replace('/api','');
  if(route==='/cells/cell-0/qc')return {cell:{cell_uuid:'cell-0',label:'Cell 0'},counts:{epochs:2},families:[{id:'a',label:'Family A',epoch_count:1},{id:'b',label:'Family B',epoch_count:1}]};
  if(route==='/cells/cell-0/qc/epochs'){
   const id=url.searchParams.get('family')==='a'?'epoch-0':'epoch-1';
   const result={epochs:[{epoch_uuid:id,epoch_number:id==='epoch-0'?1:2}],total:1};
   return h.fixture.holdRows?.(url,options,result)??result;
  }
  if(route==='/cells/cell-0/qc/response'){
   const result={cell_uuid:'cell-0',epoch_uuid:url.searchParams.get('epoch_uuid'),statistics:{pre:{mean:1},stim:{mean:2},delta_mean:1,units:'mV'}};
   return h.fixture.holdSummary?.(url,options,result)??result;
  }
  return fallback();
 };
 const Component=await h.component('CellQC');await h.mount(Component,{cellUuid:'cell-0',revision:0});
 const frame=()=>h.root.findByProps({className:'stable-content qc-recording-frame'});
 await h.waitFor(()=>frame().props['aria-busy']===false&&h.root.findAllByProps({className:'qc-trace-identity'}).length>0);
 return {h,Component,frame,family:name=>h.root.findByProps({className:'qc-families'}).findAllByType('button').find(n=>n.findByType('span').children.join('')===name)};
}

test('QC keeps its list and committed frame through a delayed family change, then publishes a matching epoch/summary',async()=>{
 const {h,frame,family}=await setup();let release;
 try{
  const list=h.root.findByProps({className:'qc-trial-list'}),recording=h.root.findByProps({className:'qc-recording'});
  h.fixture.holdSummary=(url,options,value)=>value.epoch_uuid==='epoch-1'?new Promise(resolve=>release=()=>resolve(value)):value;
  await h.act(()=>family('Family B').props.onClick());await h.waitFor(()=>!!release);
  assert.equal(h.root.findByProps({className:'qc-trial-list'}),list);
  assert.equal(h.root.findByProps({className:'qc-recording'}),recording);
  assert.equal(frame().props['aria-busy'],true);
  assert.equal(frame().findByProps({className:'stable-content-body'}).props.inert,'');
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-0');
  await h.act(()=>release());await h.waitFor(()=>!frame().props['aria-busy']);
  assert.equal(h.root.findByProps({className:'qc-recording'}),recording);
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-1');
  const start=h.fixture.requests.length;await h.act(()=>family('Family B').props.onClick());
  assert.equal(h.fixture.requests.length,start);
 }finally{release?.();await h.close();}
});

test('late QC family responses cannot overwrite latest intent and authority refresh cannot reuse the old frame',async()=>{
 const {h,Component,frame,family}=await setup();let pending;
 try{
  h.fixture.holdRows=(url,options,value)=>url.searchParams.get('family')==='b'?new Promise(resolve=>pending={signal:options.signal,resolve:()=>resolve(value)}):value;
  await h.act(()=>family('Family B').props.onClick());await h.waitFor(()=>!!pending);
  await h.act(()=>family('Family A').props.onClick());await h.waitFor(()=>!frame().props['aria-busy']);
  assert.equal(pending.signal.aborted,true);await h.act(()=>pending.resolve());
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-0');
  h.fixture.holdRows=(_url,_options,value)=>new Promise(resolve=>pending={resolve:()=>resolve(value)});
  await h.render(Component,{cellUuid:'cell-0',revision:1});
  assert.equal(h.root.findAllByProps({className:'qc-trace-identity'}).length,0);
 }finally{pending?.resolve();await h.close();}
});
