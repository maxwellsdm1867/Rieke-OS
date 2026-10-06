import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
const create=()=>createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
const comparison={contract_version:1,review_kind:'replacement',candidate_revision_uuid:'candidate',expected_candidate_scope_revision:'scope',expected_binding_version:2,expected_query_revision:'query',preview_sha256:'hash',previous_count:2,next_count:0,diff_counts:{added:0,removed:2,changed:0},compatibility:{compatible:true,epoch_count:0,expected_protocol_id:'Noise'},diff_summary:{current:{epochs:2,cells:1},proposed:{epochs:0,cells:0},delta:{epochs:-2,cells:-1},cell_changes:{removed:[{cell_uuid:'cell',previous_epoch_count:2,proposed_epoch_count:0}],counts:{removed:1}}}};
const response=value=>({ok:true,status:200,json:async()=>value});
test('predicate submit freezes a proposal without approving removals or applying membership',async()=>{
 const server=await create(),oldFetch=globalThis.fetch,calls=[],applied=[];let renderer;
 globalThis.fetch=async(path,options={})=>{calls.push({path:String(path),body:options.body&&JSON.parse(options.body)});return response(String(path).endsWith('/compare-to-protocol')?comparison:{contract_version:1,candidate_revision_uuid:'candidate',review_kind:'replacement',protocol_uuid:'protocol',operation_uuid:JSON.parse(options.body).operation_uuid});};
 try{
  const {default:Panel}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolApplyPanel.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Panel,{candidate:{revision_uuid:'candidate'},protocols:[{protocol_uuid:'protocol',name:'Noise'}],initialProtocolId:'protocol',onApplied:(...args)=>applied.push(args)}));});
  assert.equal(calls.length,1);
  const button=renderer.root.findAllByType('button').find(node=>label(node)==='Review in Workbench');assert.equal(button.props.disabled,false);
  await act(async()=>button.props.onClick());
  assert.ok(calls[1].path.endsWith('/propose-to-protocol'));assert.equal(calls[1].body.expected_binding_version,2);assert.ok(calls[1].body.operation_uuid);assert.equal(applied[0][1].candidate_revision_uuid,'candidate');
  assert.ok(calls.every(call=>!call.path.endsWith('/apply-to-protocol')&&!call.path.endsWith('/replacement-accept')));
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('removal-only frozen review requires explicit consent and recovers exact lost acceptance',async()=>{
 const server=await create(),oldFetch=globalThis.fetch,calls=[],sessions=[];let renderer,attempt=0;
 globalThis.fetch=async(path,options={})=>{if(options.method==='POST'){const body=JSON.parse(options.body);calls.push({path:String(path),body});if(++attempt===1)throw new Error('Reply lost');return response({contract_version:1,candidate_revision_uuid:'candidate',operation_uuid:body.operation_uuid,event_uuid:'accepted'});}return response(comparison);};
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/ReplacementIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'protocol',item:{candidate_revision_uuid:'candidate'},onSession:value=>sessions.push(value)}));});
  const button=text=>renderer.root.findAllByType('button').find(node=>label(node)===text);
  assert.equal(button('Accept protocol changes').props.disabled,true);assert.deepEqual(calls,[]);assert.match(label(renderer.root),/−1/);
  await act(async()=>renderer.root.findByType('input').props.onChange({target:{checked:true}}));
  await act(async()=>button('Accept protocol changes').props.onClick());assert.equal(calls[0].body.confirm_removals,true);assert.equal(button('Refresh comparison').props.disabled,true);
  const saved=sessions.at(-1);assert.ok(saved.replacementPending.body.operation_uuid);
  await act(async()=>renderer.unmount());
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'protocol',item:{candidate_revision_uuid:'candidate'},session:saved}));});
  assert.equal(calls.length,1);
  await act(async()=>button('Recover approval receipt').props.onClick());assert.deepEqual(calls[1],calls[0]);assert.match(label(renderer.root),/Protocol changes accepted/);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('Workbench exposes removal-only proposals even with zero pending additions',async()=>{
 const server=await create();let renderer;
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,{protocolId:'protocol',authority:{contract_version:1,queue_revision:'queue',pending_epoch_count:0,pending_cell_count:0,candidates:[],replacement_reviews:[{candidate_revision_uuid:'candidate',diff_counts:{added:0,removed:2,changed:0}}],capabilities:{replacement_review:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true,cumulative_pending_browse:true}}}));});
  assert.ok(renderer.root.findAllByType('button').some(node=>label(node)==='Review protocol changes'));assert.match(label(renderer.root),/−2 removed/);
 }finally{if(renderer)await act(async()=>renderer.unmount());await server.close();}
});
test('stale preview after changing the review target cannot publish or grant consent',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer,release;
 globalThis.fetch=async(path)=>{if(String(path).includes('/candidates/old/'))await new Promise(resolve=>{release=resolve;});return response({...comparison,candidate_revision_uuid:String(path).includes('/old/')?'old':'candidate'});};
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/ReplacementIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'protocol',item:{candidate_revision_uuid:'old'}}));});
  await act(async()=>renderer.update(React.createElement(Review,{protocolId:'protocol',item:{candidate_revision_uuid:'candidate'}})));
  await act(async()=>release());
  const button=renderer.root.findAllByType('button').find(node=>label(node)==='Accept protocol changes');assert.equal(button.props.disabled,true);
  assert.equal(renderer.root.findAllByProps({role:'alert'}).length,0);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('definitive stale acceptance rejection releases the request for fresh explicit review',async()=>{
 const server=await create(),oldFetch=globalThis.fetch,calls=[];let renderer;
 globalThis.fetch=async(path,options={})=>{if(options.method==='POST'){calls.push(JSON.parse(options.body));return {ok:false,status:409,json:async()=>({error:'Baseline advanced'})};}return response(comparison);};
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/ReplacementIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'protocol',item:{candidate_revision_uuid:'candidate'}}));});
  const button=text=>renderer.root.findAllByType('button').find(node=>label(node)===text);
  await act(async()=>renderer.root.findByType('input').props.onChange({target:{checked:true}}));
  await act(async()=>button('Accept protocol changes').props.onClick());assert.equal(button('Refresh comparison').props.disabled,false);
  await act(async()=>button('Refresh comparison').props.onClick());assert.equal(button('Accept protocol changes').props.disabled,true);
  await act(async()=>renderer.root.findByType('input').props.onChange({target:{checked:true}}));await act(async()=>button('Accept protocol changes').props.onClick());assert.notEqual(calls[0].operation_uuid,calls[1].operation_uuid);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('a late predicate proposal reply cannot navigate after the candidate changed',async()=>{
 const server=await create(),oldFetch=globalThis.fetch,applied=[];let renderer,release,submission;
 globalThis.fetch=async(path,options={})=>{if(String(path).endsWith('/propose-to-protocol')){const body=JSON.parse(options.body);await new Promise(resolve=>{release=resolve;});return response({contract_version:1,review_kind:'replacement',protocol_uuid:'protocol',candidate_revision_uuid:'frozen-old',operation_uuid:body.operation_uuid});}return response(comparison);};
 try{
  const {default:Panel}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolApplyPanel.jsx');
  const props={protocols:[{protocol_uuid:'protocol',name:'Noise'}],initialProtocolId:'protocol',onApplied:(...args)=>applied.push(args)};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Panel,{...props,candidate:{revision_uuid:'old'}}));});
  await act(async()=>{submission=renderer.root.findAllByType('button').find(node=>label(node)==='Review in Workbench').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Panel,{...props,candidate:{revision_uuid:'new'}})));
  await act(async()=>{release();await submission;});assert.deepEqual(applied,[]);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
for(const capability of [undefined,false,true])test(`replacement deep links require explicitly advertised capability (${capability})`,async()=>{
 const server=await create(),oldFetch=globalThis.fetch,calls=[];let renderer;
 globalThis.fetch=async(path)=>{calls.push(String(path));return response(comparison);};
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
  const authority={contract_version:1,queue_revision:'queue',pending_epoch_count:0,pending_cell_count:0,candidates:[],replacement_reviews:[{candidate_revision_uuid:'candidate',diff_counts:{added:0,removed:2,changed:0}}],capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true,...(capability===undefined?{}:{replacement_review:capability})}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,{protocolId:'protocol',initialCandidateId:'candidate',authority}));});
  if(capability===true){assert.equal(calls.length,1);assert.ok(calls[0].endsWith('/replacement-preview'));}
  else{
   assert.deepEqual(calls,[]);assert.match(label(renderer.root),/Protocol change review is unavailable/);
   await act(async()=>renderer.root.findAllByType('button').find(node=>label(node)==='Back to proposal history').props.onClick());
   assert.equal(renderer.root.findAllByType('button').find(node=>label(node)==='Review protocol changes').props.disabled,true);assert.deepEqual(calls,[]);
  }
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('a preview without the replacement discriminator cannot authorize acceptance',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer;
 globalThis.fetch=async()=>response({...comparison,review_kind:'additive'});
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/ReplacementIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'protocol',item:{candidate_revision_uuid:'candidate'}}));});
  assert.match(label(renderer.root),/frozen change preview is incomplete/);assert.equal(renderer.root.findAllByType('button').find(node=>label(node)==='Accept protocol changes').props.disabled,true);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
