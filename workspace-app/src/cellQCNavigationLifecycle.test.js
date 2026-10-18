import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

async function setup(){
 const h=await createWorkflowHarness();
 h.fixture.respond=(url,options,fallback)=>{
  const route=url.pathname.replace('/api','');
  if(route==='/cells/cell-0/qc')return {cell:{cell_uuid:'cell-0',label:'Cell 0',cell_type:'RGC/ON-parasol'},counts:{epochs:2},families:[{id:'a',label:'Family A',epoch_count:1},{id:'b',label:'Family B',epoch_count:1}]};
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
  const identity=h.root.findByProps({className:'qc-cell-type'});
  assert.ok(identity.findAllByType('svg').some(node=>node.props.style?.color==='var(--cell-on)'&&node.props['aria-hidden']===true));
  const list=h.root.findByProps({className:'qc-trial-list'}),recording=h.root.findByProps({className:'qc-recording'});
  h.fixture.holdSummary=(url,options,value)=>value.epoch_uuid==='epoch-1'?new Promise(resolve=>release=()=>resolve(value)):value;
  await h.act(()=>family('Family B').props.onClick());await h.waitFor(()=>!!release);
  assert.equal(h.root.findByProps({className:'qc-trial-list'}),list);
  assert.equal(h.root.findByProps({className:'qc-recording'}),recording);
  assert.equal(frame().props['aria-busy'],true);
  assert.equal(frame().findByProps({className:'stable-content-body'}).props.inert,true);
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

test('a tag-only change reloads the epoch detail but not samples, QC summaries or trial pages',async()=>{
 const {h,Component}=await setup();
 try{
  await h.render(Component,{cellUuid:'cell-0',revision:0,structureRevision:0});
  const start=h.fixture.requests.length;
  await h.render(Component,{cellUuid:'cell-0',revision:1,structureRevision:0});
  await h.waitFor(()=>h.fixture.requests.slice(start).some(r=>r.path.startsWith('/epochs/epoch-0')));
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).length>0);
  const paths=h.fixture.requests.slice(start).map(r=>r.path.split('?')[0]);
  assert.ok(paths.includes('/epochs/epoch-0'),'Epoch detail carries annotations and follows tag edits');
  assert.deepEqual(paths.filter(path=>path.startsWith('/cells/')||path.includes('/trace')),[],paths.join(', '));
  const before=h.fixture.requests.length;
  await h.render(Component,{cellUuid:'cell-0',revision:2,structureRevision:1});
  await h.waitFor(()=>h.fixture.requests.slice(before).some(r=>r.path.startsWith('/cells/cell-0/qc?')||r.path==='/cells/cell-0/qc'));
 }finally{await h.close();}
});

test('a confirmed QC tag is shown from its write receipt with no rereads',async()=>{
 const {h,Component}=await setup();const changes=[];
 try{
  await h.render(Component,{cellUuid:'cell-0',revision:0,structureRevision:0,annotationRevision:0,onAnnotationsChanged:(result,confirmed)=>changes.push(confirmed)});
  const tags=h.root.findAllByType('button').find(node=>node.findAllByType('svg').length&&node.children.some(child=>child==='Tags'||child?.includes?.('Tags')));
  await h.act(()=>tags.props.onClick());
  const input=()=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.startsWith('Tag ')&&!node.props['aria-label'].startsWith('Tag to add'));
  await h.waitFor(()=>{try{return !!input()&&!input().props.disabled;}catch{return false;}});
  const before=h.fixture.requests.length;
  await h.act(()=>input().props.onChange({target:{value:'qc-tag'}}));
  await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>changes.length===1);
  await new Promise(resolve=>setTimeout(resolve,200));
  assert.deepEqual(h.fixture.requests.slice(before).map(row=>row.method+' '+row.path.split('?')[0]),['POST /annotations']);
  assert.equal(changes[0]?.version,1,'The confirmed receipt is passed to the app');
  const text=JSON.stringify(h.root.findByProps({className:'page cell-qc'}).findAll(node=>typeof node.children?.[0]==='string').map(node=>node.children.join('')));
  assert.match(text,/qc-tag/);
 }finally{await h.close();}
});
