import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {epochPageRequest} from './epoch-browser/epochBrowserSource.js';
import {advanceEpochIntent} from './epoch-browser/epochNavigationIntent.js';
import {inspectionNavigation,inspectionPageOffset} from './epoch-browser/inspectionNavigation.js';
import {epochSelectionRange} from './epochSelection.js';
import {treePageRequest} from './pagedTreeRequest.js';

async function harness(){
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const api=await server.ssrLoadModule('/src/api.js');
 const ports=await server.ssrLoadModule('/src/workspaceRequest.js');
 const {epochResourceCache:cache}=await server.ssrLoadModule('/src/resourceCache.js');
 const {useEpochBrowserPage}=await server.ssrLoadModule('/src/epoch-browser/useEpochBrowserPage.js');
 const previousFetch=globalThis.fetch,globalRequests=[],renders=[];
 globalThis.fetch=async path=>{globalRequests.push(path);return new Response(JSON.stringify({from:'legacy'}),{status:200});};
 let renderer,current;
 function Probe({paused=false}){
  const resource=api.useResource('/epochs/same',1,0,{cache:true,warmEpoch:true,paused});
  const page=useEpochBrowserPage({kind:'protocol',protocolId:'p',queryRevision:'q'},{offset:50});
  api.useEpochPrefetch(['/epochs/neighbor'],1,0);
  api.useEpochPrefetch(['/epochs/trace-neighbor'],1,0,{traces:true});
  api.useEpochPrefetch(['/epochs/trace-neighbor/trace?stream_uuid=s&start=0&count=3'],1,0,{traceOnly:true});
  current={resource,page,request:ports.useWorkspaceRequest(api.api),scope:ports.useWorkspaceRequestScope()};
  renders.push(current);return null;
 }
 return {cache,globalRequests,renders,get current(){return current;},
  async render(port,props={}){await act(async()=>{const probe=React.createElement(Probe,props);const element=port===undefined?probe:React.createElement(ports.WorkspaceRequestProvider,{port},probe);if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});},
  async close(){await act(async()=>renderer?.unmount());globalThis.fetch=previousFetch;await server.close();},
 };
}
test('scoped resources, pages and commands share one port without cache warmth or speculative global reads',async()=>{
 const h=await harness(),calls=[];
 const port={identity:'project/publication/A',request:async(path,options)=>{calls.push({path,options});return {from:'snapshot',path};}};
 try{
  h.cache.put('/epochs/same',1,{from:'global-cache'});
  await h.render(port);
  assert.equal(h.current.resource.data.from,'snapshot');
  assert.equal(h.cache.peek('/epochs/same',1).from,'global-cache');
  assert.equal(h.current.scope.pageSize,50);
  assert.equal(calls.length,2);assert.match(calls.find(call=>call.path.includes('/protocols/')).path,/limit=50/);
  assert.equal(calls.some(call=>call.path.includes('neighbor')||call.path.includes('/trace')),false);
  await act(async()=>h.current.request('/annotations',{method:'POST',body:{target_uuids:['same']}}));
  assert.equal(calls.at(-1).options.method,'POST');
  assert.deepEqual(h.globalRequests,[]);
  await act(async()=>h.current.resource.reload());assert.equal(calls.length,4);
  assert.equal(h.cache.peek('/epochs/same',1).from,'global-cache','scoped reload cannot invalidate global cache');
 }finally{await h.close();}
});
test('same logical path and revision cannot publish a retired owner or consume its late completion',async()=>{
 const h=await harness();let finish;const calls=[];
 const old={identity:'historical-A',request:(path,options)=>{calls.push({path,options});return path==='/epochs/same'?new Promise(resolve=>{finish=resolve;}):Promise.resolve({from:'A'});}};
 const next={identity:'historical-B',request:async()=>({from:'B'})};
 try{
  await h.render(old);const first=h.renders.length;
  await h.render(next);
  assert.equal(calls[0].options.signal.aborted,true);
  assert.equal(h.renders[first].resource.data,null,'render fence precedes replacement effects');
  assert.equal(h.current.resource.data.from,'B');
  await act(async()=>finish({from:'A'}));assert.equal(h.current.resource.data.from,'B');
  assert.deepEqual(h.globalRequests,[]);
 }finally{await h.close();}
});
test('present malformed owner rejects reads and actions rather than using the legacy adapter',async()=>{
 const h=await harness();
 try{await h.render({identity:'missing-port'});assert.match(h.current.resource.error,/unavailable/);assert.match(h.current.page.error,/unavailable/);await assert.rejects(h.current.request('/annotations',{method:'POST'}),/unavailable/);await assert.rejects(h.current.scope.download('/annotations/export',{}),/unavailable/);assert.deepEqual(h.globalRequests,[]);}
 finally{await h.close();}
});
test('fifty-row pagination preserves keyboard, restored position, and complete range selection',async()=>{
 const pageSize=50;
 assert.match(epochPageRequest({kind:'protocol',protocolId:'p',pageSize},{offset:50}).path,/offset=50/);
 assert.equal(treePageRequest({protocolId:'p',pageSize}).limit,50);
 assert.deepEqual(advanceEpochIntent({page:{offset:0,total:120,epochs:[{epoch_uuid:'last'}]},focused:'last',intent:{index:49,total:120},direction:1,pageSize}),{index:50,total:120,offset:50});
 const restored=inspectionNavigation({scope:'s',cells:['c'],offsets:{c:100}},'s',50);
 assert.equal(restored.offsets.c,100);assert.equal(inspectionPageOffset(100,120,50),100);
 const reads=[];
 const ids=await epochSelectionRange({pageSize,cells:[{cell_uuid:'c',epochs:120}],anchor:{cellUuid:'c',index:48,uuid:'e48',revision:'q'},target:{cellUuid:'c',index:101,uuid:'e101',revision:'q'},loadPage:async(cell,offset)=>{reads.push(offset);return {query_revision:'q',offset,total:120,epochs:Array.from({length:Math.min(50,120-offset)},(_,i)=>({cell_uuid:cell,epoch_uuid:`e${offset+i}`}))};}});
 assert.deepEqual(reads,[0,50,100]);assert.deepEqual(ids,Array.from({length:54},(_,i)=>`e${48+i}`));
});

test('existing trace viewer requests the restored selection naturally and refuses another historical receipt',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const id=n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
 const context={kind:'imported_snapshot',project_uuid:id(1),publication_revision:id(2),scope_data_revision:id(3),protocol_uuid:id(4),source_sha256:'a'.repeat(64),processing_version:'stored-v1'};
 const epoch={epoch_uuid:id(5),streams:[{kind:'responses',uuid:id(6),sample_count:25000,sample_rate:10000,units:'pA'}]};
 const calls=[],previousFetch=globalThis.fetch;let renderer;
 globalThis.fetch=()=>{throw Error('Global transport must not be called');};
 const port={identity:'historical-trace',traceReadContext:context,request:async(path)=>{calls.push(path);return {epoch_uuid:id(5),stream_uuid:id(6),start:0,count:20000,sample_rate:10000,values:Array(20000).fill(1),read_context:{...context,scope_data_revision:id(7)}};}};
 try{
  await act(async()=>{renderer=TestRenderer.create(React.createElement(WorkspaceRequestProvider,{port},React.createElement(Trace,{epoch})));});
  assert.equal(calls.length,1);assert.match(calls[0],/\/snapshot\/protocols\//);assert.match(calls[0],/count=20000/);assert.match(calls[0],new RegExp(`scope_data_revision=${id(3)}`));
  const alerts=renderer.root.findAll(node=>node.props.role==='alert');
  assert.equal(alerts.length,1);assert.match(alerts[0].props.children.filter(value=>typeof value==='string').join(''),/Trace identity, sample rate, units or window does not match/);
  assert.equal(renderer.root.findAll(node=>node.type==='button'&&node.props.children==='Read trace').length,0);
  const wrongRate={...port,request:async()=>({epoch_uuid:id(5),stream_uuid:id(6),start:0,count:20000,sample_rate:9999,values:Array(20000).fill(1),read_context:context})};
  await act(async()=>renderer.update(React.createElement(WorkspaceRequestProvider,{port:wrongRate},React.createElement(Trace,{epoch}))));
  assert.equal(renderer.root.findAll(node=>node.props.role==='alert').length,1,'matching context cannot admit a different indexed sample rate');
  const wrongUnits={...port,request:async()=>({epoch_uuid:id(5),stream_uuid:id(6),start:0,count:20000,sample_rate:10000,units:null,values:Array(20000).fill(1),read_context:context})};
  await act(async()=>renderer.update(React.createElement(WorkspaceRequestProvider,{port:wrongUnits},React.createElement(Trace,{epoch}))));
  assert.equal(renderer.root.findAll(node=>node.props.role==='alert').length,1,'canonical null units must not equal recorded pA');
  const exact={...port,request:async path=>{const query=new URLSearchParams(path.split('?')[1]),start=Number(query.get('start')),count=Number(query.get('count'));return {epoch_uuid:id(5),stream_uuid:id(6),start,count,total_samples:25000,source_sha256:context.source_sha256,decimated:false,sample_rate:10000,units:'pA',values:Array(count).fill(1),read_context:context};}};
  await act(async()=>renderer.update(React.createElement(WorkspaceRequestProvider,{port:exact},React.createElement(Trace,{epoch}))));
  assert.equal(renderer.root.findAll(node=>node.props.role==='alert').length,0,'exact recorded context, rate and units are admitted');


 }finally{await act(async()=>renderer?.unmount());globalThis.fetch=previousFetch;await server.close();}
});

test('authority remount restores externally owned Inspector focus and unfinished shared annotation drafts',async()=>{
 const {createInspectorHarness}=await import('./test-support/inspectorHarness.js');
 const h=await createInspectorHarness(),calls=[];
 const request=async(path,options)=>{calls.push({path,options});throw Error('Unexpected stale command');};
 const portA={identity:'project/protocol/publication-A/scope-A/processing',request};
 const portB={identity:'project/protocol/publication-B/scope-A/processing',request};
 let saved;
 const props={protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-A',expected_binding_version:2,cells:[]},filters:{},revision:0,initialEpochUuid:'epoch-A',onSessionChange:value=>{saved=value;}};
 try{
  await h.render(props,{port:portA});
  await h.act(()=>h.viewer.tags.props.composer.onChange('epoch-A-shared','unfinished scientific note'));
  await h.act(()=>h.tags.onValue('unfinished dataset tag'));
  assert.equal(saved.annotationDrafts['epoch-A-shared'],'unfinished scientific note');
  assert.equal(saved.curationTagDraft,'unfinished dataset tag');
  const oldAction=h.tags.onAdd,restore=saved;
  await h.render({...props,initialNavigation:restore},{port:portB});
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-A');
  assert.equal(h.viewer.tags.props.composer.values['epoch-A-shared'],'unfinished scientific note');
  assert.equal(h.tags.value,'unfinished dataset tag');
  await h.act(()=>oldAction('must not save'));
  assert.deepEqual(calls,[],'an old action cannot invoke a previous scientific owner');
 }finally{await h.close();}
});


test('supplied owner with missing, blank or non-string identity cannot call otherwise valid transports',async()=>{
 const h=await harness();let calls=0;
 try{
  for(const identity of [undefined,'','   ',42,{}]){
   const port={identity,request:async()=>{calls++;return {};},download:async()=>{calls++;}};
   await h.render(port);assert.match(h.current.resource.error,/unavailable/);
   await assert.rejects(h.current.request('/annotations',{method:'POST'}),/unavailable/);
   await assert.rejects(h.current.scope.download('/annotations/export',{}),/unavailable/);
  }
  assert.equal(calls,0);assert.deepEqual(h.globalRequests,[]);
 }finally{await h.close();}
});

test('scoped actual shared-tag save uses its request and never invalidates the global epoch cache',async()=>{
 const {createWorkflowHarness}=await import('./test-support/workflowHarness.js');
 const h=await createWorkflowHarness();
 const {WorkspaceRequestProvider}=await h.module('workspaceRequest.js');
 const {epochResourceCache}=await h.module('resourceCache.js');
 const Tags=await h.component('AnnotationTags');
 const ownedFetch=globalThis.fetch,oldInvalidate=epochResourceCache.invalidateAnnotations;let invalidations=0,globals=0,receipt;
 epochResourceCache.invalidateAnnotations=()=>{invalidations++;};
 globalThis.fetch=()=>{globals++;throw Error('Global transport must not be used');};
 const port={identity:'annotation-scope',request:async(path,options={})=>{
  const response=await ownedFetch(`/api${path}`,{...options,body:options.body===undefined?undefined:JSON.stringify(options.body)});
  return response.json();
 }};
 function ScopedTags(){return React.createElement(WorkspaceRequestProvider,{port},React.createElement(Tags,{selectedCells:['cell-0'],targetScope:'selected-cells',revision:'fresh',reconcileReceipt:true,onChange:(_,value)=>{receipt=value;}}));}
 try{
  await h.mount(ScopedTags,{});
  const input=()=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.includes('selected cells'));
  await h.waitFor(()=>input()&&!input().props.disabled);
  await h.act(()=>input().props.onChange({target:{value:'scoped note'}}));
  await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>receipt);
  assert.equal(h.fixture.cellAnnotations.get('cell-0')[0],'scoped note');
  assert.equal(globals,0);assert.equal(invalidations,0);
 }finally{epochResourceCache.invalidateAnnotations=oldInvalidate;await h.close();}
});
