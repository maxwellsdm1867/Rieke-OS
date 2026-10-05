import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import React,{act,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {createServer} from './test-support/isolatedVite.js';
const {JSDOM}=await import(process.env.RIEKE_TEST_DOM_MODULE||'jsdom');
const root=fileURLToPath(new URL('..',import.meta.url));
const protocol='strict-protocol',base=`/protocols/${protocol}/workbench`;
const context=id=>({candidate_revision_uuid:id,protocol:{definition:{protocol_uuid:protocol}},candidate_scope_revision:`scope-${id}`,draft:{draft_version:1,selection_mode:'selected'},counts:{pending_epochs:2}});
const prepared=token=>({contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:`prepare-${token}`,candidate_revision_uuid:`union-${token}`,root:`${base}/candidates/union-${token}`,candidate_scope_revision:`scope-union-${token}`,queue_revision:token,context:context(`union-${token}`)});
const queue=token=>({data:{queue_revision:token,pending_epoch_count:2,total_candidate_count:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}},loading:false});
const deferred=()=>{let resolve;const promise=new Promise(value=>{resolve=value;});return {promise,resolve};};
const response=(value,status=200)=>({ok:status===200,status,json:async()=>value});
const probes={name:'strict-frozen-browser-probe',enforce:'pre',resolveId(source,importer){if(importer?.endsWith('/FrozenIncomingReview.jsx')&&['../../components/Inspector.jsx','../../typed-query/ui/ProtocolViewFilter.jsx'].includes(source))return `\0strict-${source}`;},load(id){if(id==='\0strict-../../components/Inspector.jsx')return `import React from 'react';export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=true;export default function Inspector({readContext}){return React.createElement('div',{'data-inspector-scope':readContext.candidate_scope_revision});}`;if(id==='\0strict-../../typed-query/ui/ProtocolViewFilter.jsx')return 'export default function Filter(){return null;}';}};
async function harness(fetch){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost/'});
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,fetch};
 const previous=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const server=await createServer({root,configFile:false,plugins:[probes],optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx');
 const container=dom.window.document.getElementById('root');let mounted=createRoot(container),setups=0,cleanups=0,saved;
 function Proof(props){useEffect(()=>{setups++;return()=>{cleanups++;};},[]);return React.createElement(Review,{protocolId:protocol,onSession:value=>{saved=value;},...props});}
 return {container,get saved(){return saved;},get setups(){return setups;},get cleanups(){return cleanups;},
  async render(props){await act(async()=>mounted.render(React.createElement(React.StrictMode,null,React.createElement(Proof,props))));},
  async unmount(){if(mounted){await act(async()=>mounted.unmount());mounted=null;}},
  remount(){assert.equal(mounted,null);mounted=createRoot(container);},
  async close(){if(mounted)await act(async()=>mounted.unmount());await server.close();dom.window.close();for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}
 };
}
function contextResponse(endpoint){assert.ok(endpoint.endsWith('/context'),`No global fallback: ${endpoint}`);return response(context(endpoint.split('/').at(-2)));}

test('ReactDOM StrictMode first entry rejoins one preparation and opens Inspector without Retry',async()=>{
 const gate=deferred(),bodies=[];
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){bodies.push(options.body);await gate.promise;return response(prepared('one'));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('one')});assert.equal(view.setups,2);assert.equal(view.cleanups,1,'ReactDOM really replayed effects');assert.equal(bodies.length,1);
  assert.doesNotMatch(view.container.textContent,/interrupted|Retry cumulative/);
  await act(async()=>gate.resolve());
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'scope-union-one');assert.equal(bodies.length,1);assert.doesNotMatch(view.container.textContent,/Retry cumulative/);
 }finally{await view.close();}
});

test('changed authority supersedes pending display and ignores a late old completion',async()=>{
 const gates={old:deferred(),new:deferred()},bodies=[];
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){const token=JSON.parse(options.body).expected_queue_revision;bodies.push(options.body);await gates[token].promise;return response(prepared(token));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('old')});await view.render({queue:queue('new')});assert.equal(bodies.length,2);
  await act(async()=>gates.new.resolve());assert.equal(view.saved.prepared.queue_revision,'new');
  await act(async()=>gates.old.resolve());assert.equal(view.saved.prepared.queue_revision,'new');assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'scope-union-new');
 }finally{await view.close();}
});

test('genuine unmount detaches late response and remount retries the identical server-idempotent body',async()=>{
 const first=deferred(),bodies=[],receipts=new Map();let writes=0;
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){bodies.push(options.body);if(!receipts.has(options.body)){writes++;receipts.set(options.body,prepared('one'));}if(bodies.length===1)await first.promise;return response(receipts.get(options.body));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('one')});const saved=view.saved;await view.unmount();
  await act(async()=>first.resolve());assert.equal(view.container.childNodes.length,0);assert.equal(view.saved,saved,'unmounted subscriber cannot publish a result');
  view.remount();await view.render({queue:queue('one'),session:saved});
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);assert.equal(writes,1,'server receipt identity derives from the unchanged request');assert.equal(view.saved.prepared.queue_revision,'one');
 }finally{await view.close();}
});

test('lost preparation response requires explicit retry with identical body and recovers one receipt',async()=>{
 const bodies=[],receipt=prepared('one');let writes=0;
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){bodies.push(options.body);if(bodies.length===1){writes++;return response({error:'Reply lost after commit'},503);}return response(receipt);}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('one')});assert.equal(bodies.length,1);assert.match(view.container.textContent,/Reply lost/);
  await view.render({queue:{...queue('one')}});assert.equal(bodies.length,1,'ordinary rerender does not repeat failed mutations');
  const retry=[...view.container.querySelectorAll('button')].find(button=>button.textContent==='Retry cumulative preparation');assert.ok(retry);
  await act(async()=>retry.dispatchEvent(new window.MouseEvent('click',{bubbles:true})));
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);assert.equal(writes,1);assert.equal(view.saved.prepared.prepare_operation_uuid,receipt.prepare_operation_uuid);
 }finally{await view.close();}
});

test('StrictMode preserves an uncertain acceptance body before preparing newer authority',async()=>{
 const old=prepared('old'),acceptBodies=[];let prepares=0;
 const preview={expected_candidate_scope_revision:old.candidate_scope_revision,expected_draft_version:1,mode:'selected',preview_sha256:'sealed-preview',expected_binding_version:1,expected_query_revision:'main-old',selected_epoch_count:1,accepted_epoch_count:1,already_present_epoch_count:0,retained_epoch_count:1,next_epoch_count:2,accepted_cell_count:1};
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===old.root+'/accept'){acceptBodies.push(JSON.parse(options.body));return response({operation_uuid:'same-operation',candidate_revision_uuid:old.candidate_revision_uuid,event_uuid:'accepted',binding:{revision_uuid:'main-new',version:2}});}if(endpoint===base+'/prepare'){prepares++;return response(prepared('new'));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('new'),session:{prepared:old,drafts:{[old.candidate_revision_uuid]:{unconfirmed:true,operation:'same-operation',preview}}}});
  assert.equal(prepares,0);assert.deepEqual(view.saved.drafts[old.candidate_revision_uuid].preview,preview);
  const retry=[...view.container.querySelectorAll('button')].find(button=>button.textContent==='Recover acceptance receipt');assert.ok(retry);
  await act(async()=>retry.dispatchEvent(new window.MouseEvent('click',{bubbles:true})));
  assert.equal(acceptBodies.length,1);assert.equal(acceptBodies[0].operation_uuid,'same-operation');for(const [key,value] of Object.entries(preview))if(key.startsWith('expected_')||key==='mode'||key==='preview_sha256')assert.equal(acceptBodies[0][key],value);
  assert.equal(prepares,1);assert.equal(view.saved.prepared.queue_revision,'new');
 }finally{await view.close();}
});
