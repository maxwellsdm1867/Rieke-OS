import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
const root=fileURLToPath(new URL('..',import.meta.url));
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
const caps={cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true};
const candidates=[{protocol_uuid:'protocol',candidate_revision_uuid:'fresh',status:'pending',pending_epoch_count:136,eligible_pending_epoch_count:136,source_filename:'fresh.h5'}, {protocol_uuid:'protocol',candidate_revision_uuid:'historical',status:'conflict',pending_epoch_count:136,eligible_pending_epoch_count:0,source_filename:'historical.h5'}];
const queue={contract_version:1,queue_revision:'authority',pending_epoch_count:136,pending_cell_count:4,total_candidate_count:2,candidates,capabilities:caps};
const create=()=>createServer({root,configFile:false,plugins:[{name:'scope-probe',enforce:'pre',resolveId(source,importer){if(importer?.endsWith('/FrozenIncomingReview.jsx')&&['./Inspector.jsx','./ProtocolViewFilter.jsx'].includes(source))return '\0probe-'+source;},load(id){if(id==='\0probe-./Inspector.jsx')return "import React from 'react';export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=true;export default ({readContext})=>React.createElement('div',{'data-root':readContext.root});";if(id==='\0probe-./ProtocolViewFilter.jsx')return 'export default ()=>null;';}}],optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});

test('blocked combined preparation exposes explicit fresh-proposal review without mutation or discarded cumulative decisions',async()=>{
 const oldFetch=globalThis.fetch,server=await create();let view,saved;const requests=[];
 const intent={kind:'preview_all',request_uuid:'explicit-request',project_uuid:'project',protocol_uuid:'protocol'};
 const cumulative={drafts:{'older-union':{selected:['saved'],filters:{cell_uuid:'saved-cell'}}},scopes:{}};
 globalThis.fetch=async(path,options={})=>{
  requests.push({path,method:options.method||'GET'});
  if(path==='/api/protocols/protocol/workbench/prepare')return {ok:false,status:409,json:async()=>({code:'workbench_conflict',error:'An unmerged original proposal has stale authority or conflicting fingerprints; reconcile it before cumulative preparation'})};
  assert.equal(path,'/api/protocols/protocol/workbench/candidates/fresh/context');
  return {ok:true,status:200,json:async()=>({candidate_scope_revision:'fresh-scope',candidate_revision_uuid:'fresh',protocol:{definition:{protocol_uuid:'protocol'}},draft:{draft_version:0,selection_mode:'selected',decisions:[]},counts:{pending_epochs:136,pending_cells:4},publication_blocked:false})};
 };
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/components/IncomingWorkbench.jsx');
  await act(async()=>{view=TestRenderer.create(React.createElement(Workbench,{protocolId:'protocol',projectId:'project',authority:queue,initialMergeIntent:intent,onClaimMergeIntent:value=>value===intent,session:{cumulative},onSession:value=>{saved=value;}}));});
  const recovery=view.root.findByProps({'aria-label':'Cumulative review recovery'});
  assert.match(label(recovery),/own selections and exclusions apply/);
  assert.doesNotMatch(label(view.root),/Preparing your merge preview|Cancel merge request/,'the failed preview intent ends before independent review');
  assert.equal(recovery.findAllByType('button').filter(button=>label(button)==='Review saved proposals').length,1,'one history action in the refusal panel');
  const actions=recovery.findAllByType('button').filter(button=>label(button)==='Review eligible proposal');assert.equal(actions.length,1);
  await act(async()=>actions[0].props.onClick());
  assert.equal(view.root.findByProps({'data-root':'/protocols/protocol/workbench/candidates/fresh'}).type,'div');
  assert.ok(view.root.findAllByType('button').some(button=>label(button)==='Merge all'&&!button.props.disabled));
  assert.deepEqual(saved.cumulative.drafts,cumulative.drafts);assert.equal(saved.active,'fresh');
  assert.deepEqual(requests.map(r=>r.method),['POST','GET']);assert.ok(requests.every(r=>!r.path.endsWith('/preview')&&!r.path.endsWith('/accept')&&!r.path.endsWith('/draft')));
 }finally{if(view)await act(()=>view.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('unknown, stale or blocked proposals never appear as eligible recovery actions, and refresh fences the old queue',async()=>{
 const oldFetch=globalThis.fetch,server=await create();let view;globalThis.fetch=async()=>({ok:false,status:409,json:async()=>({error:'Preparation refused'})});
 try{
  const {default:Cumulative}=await server.ssrLoadModule('/src/components/CumulativeIncomingReview.jsx');
  const props={protocolId:'protocol',onReviewProposal:()=>{throw Error('No recovery while stale');},queue:{data:{...queue,candidates:[candidates[1],{...candidates[0],eligible_pending_epoch_count:null},{...candidates[0],status:'source_blocked'}]},loading:false}};
  await act(async()=>{view=TestRenderer.create(React.createElement(Cumulative,props));});
  assert.equal(view.root.findAllByType('button').filter(b=>label(b)==='Review eligible proposal').length,0);
  await act(async()=>view.update(React.createElement(Cumulative,{...props,queue:{data:queue,loading:true}})));
  const button=view.root.findAllByType('button').find(b=>label(b)==='Review eligible proposal');assert.ok(button?.props.disabled);
 }finally{if(view)await act(()=>view.unmount());globalThis.fetch=oldFetch;await server.close();}
});
