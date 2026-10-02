import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('');
const root=fileURLToPath(new URL('..',import.meta.url));
const create=()=>createServer({root,configFile:false,cacheDir:root+'/.review-vite-cache',optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});

test('actual Workbench renders authoritative queue and session worklist controls',async()=>{
 const server=await create();
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/components/IncomingWorkbench.jsx');
  const item={protocol_uuid:'history',protocol_name:'VariableHistoryNoiseCurInject',candidate_revision_uuid:'candidate-immutable',baseline_revision_uuid:'base-immutable',status:'pending',created_at:'2026-10-02T01:00:00Z',source_filename:'incoming.h5',diff_counts:{added:12,removed:0,changed:2},next_count:50};
  const props={protocolId:'history',suggestions:[item,{...item,protocol_uuid:'other',protocol_name:'Other'}],projectId:'project',authority:null};
  const html=renderToStaticMarkup(React.createElement(Workbench,props));
  for(const text of ['Needs review','candidate-immutable','base-immutable','incoming.h5','Earlier unmerged updates'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/>Other</);assert.match(html,/disabled=""[^>]*>Accept &amp; export/);
  const cumulative={contract_version:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},queue_revision:'union',pending_cell_count:2,pending_epoch_count:30,candidates:[{...item,pending_epoch_count:20},{...item,candidate_revision_uuid:'second-proposal',pending_epoch_count:20}]};
  const cumulativeHtml=renderToStaticMarkup(React.createElement(Workbench,{...props,authority:cumulative}));
  assert.match(cumulativeHtml,/2.*distinct cells/);assert.match(cumulativeHtml,/30.*incoming epochs/);assert.match(cumulativeHtml,/second-proposal/);assert.doesNotMatch(cumulativeHtml,/Earlier unmerged updates/);
  const blockedHtml=renderToStaticMarkup(React.createElement(Workbench,{...props,authority:{...cumulative,pending_cell_count:0,pending_epoch_count:0,candidates:[{...item,status:'conflict',pending_epoch_count:0},{...item,candidate_revision_uuid:'blocked-source',status:'source_blocked',pending_epoch_count:0}]}}));
  assert.match(blockedHtml,/Conflict requires review/);assert.match(blockedHtml,/Source unavailable/);assert.match(blockedHtml,/blocked-source/);assert.doesNotMatch(blockedHtml,/No current incoming proposals/);
  let renderer,saved;
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,{...props,onSession:value=>{saved=value;}}));});
  await act(async()=>renderer.root.findByType('input').props.onChange());
  assert.deepEqual(saved.selected,['history:candidate-immutable']);
  assert.ok(renderer.root.findAllByType('button').some(button=>label(button)==='Review selected'));
  assert.equal(saved.active,null);
  await act(async()=>renderer.unmount());
  const restored=renderToStaticMarkup(React.createElement(Workbench,{...props,session:saved}));
  assert.match(restored,/1 selected proposals/);
  const dir=fileURLToPath(new URL('../../review-evidence',import.meta.url));
  await mkdir(dir,{recursive:true});await writeFile(`${dir}/workbench-component.html`,html);
 }finally{await server.close();}
});
test('App and affected dialog/browser/sidebar JSX transform from isolated source',async()=>{
 const server=await create();
 try{
  for(const file of ['App.jsx','components/MetadataExplorer.jsx','components/IncomingExportDialog.jsx','components/ExportSelectionDialog.jsx','components/ProtocolSidebar.jsx','components/FrozenIncomingReview.jsx']){
   const result=await server.transformRequest(`/src/${file}`);assert.ok(result?.code.length>0,file);
  }
 }finally{await server.close();}
});

test('mounted additive review preserves an uncertain acceptance operation and recovers its receipt without rebinding',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;
 const calls=[];let renderer,saved,accepts=0,changed=0;
 const root='/protocols/history/workbench/candidates/proposal';
 const context={candidate_scope_revision:'exact-frozen-scope',draft:{draft_version:4,selection_mode:'all'},protocol:null};
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):undefined;
  calls.push({path:endpoint,method:options.method||'GET',body});
  let value=context,status=200;
  if(endpoint===`${root}/preview`)value={preview_sha256:'sealed-preview',expected_binding_version:2,expected_query_revision:'main-query',selected_epoch_count:7,accepted_epoch_count:7,already_present_epoch_count:0,retained_epoch_count:40,next_epoch_count:47,accepted_cell_count:2};
  else if(endpoint===`${root}/accept`){if(accepts++===0){status=503;value={error:'Reply lost after possible commit'};}else value={binding:{revision_uuid:'main-plus-additions',version:3},event_uuid:'one-event',operation_uuid:body.operation_uuid};}
  else assert.equal(endpoint,`${root}/context`,'frozen review makes no global browse or replacement request');
  return {ok:status===200,status,json:async()=>value};
 };
 try{
  const {default:Review}=await server.ssrLoadModule('/src/components/FrozenIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},protocolId:'history',item:{candidate_revision_uuid:'proposal'},onSession:value=>{saved=value;},onChange:()=>changed++}));});
  assert.ok(renderer.root.findAllByType('p').some(node=>label(node).includes('No global query is substituted')));
  const button=name=>renderer.root.findAllByType('button').find(node=>label(node)===name);
  await act(async()=>button('Preview accept all').props.onClick());
  assert.ok(renderer.root.findAllByType('dt').some(node=>label(node)==='Existing main epochs retained'));
  await act(async()=>button('Add these additions to main').props.onClick());
  assert.equal(saved.unconfirmed,true);assert.ok(saved.operation);assert.equal(saved.preview.mode,'all');
  assert.equal(button('Preview selected additions').props.disabled,true);
  assert.equal(button('Preview accept all').props.disabled,true);
  const operation=saved.operation;
  await act(async()=>renderer.unmount());
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},protocolId:'history',item:{candidate_revision_uuid:'proposal'},session:saved,onSession:value=>{saved=value;},onChange:()=>changed++}));});
  await act(async()=>button('Recover acceptance receipt').props.onClick());
  assert.equal(saved.receipt.binding.revision_uuid,'main-plus-additions');assert.equal(saved.unconfirmed,false);assert.equal(changed,1);
  const acceptanceCalls=calls.filter(call=>call.path.endsWith('/accept'));
  assert.equal(acceptanceCalls.length,2);assert.deepEqual(acceptanceCalls[0].body,acceptanceCalls[1].body);assert.equal(acceptanceCalls[1].body.operation_uuid,operation);
  assert.equal(calls.filter(call=>call.path.endsWith('/preview')).length,1);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('known cumulative authority survives a pending or failed refresh without switching to a live query',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;
 const queue={contract_version:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},queue_revision:'exact-union',pending_cell_count:2,pending_epoch_count:20,candidates:[]};
 let requests=0,release,renderer,state;
 globalThis.fetch=async()=>{if(requests++===0)return {ok:true,status:200,json:async()=>queue};await new Promise(resolve=>{release=resolve;});return {ok:false,status:503,json:async()=>({error:'unavailable'})};};
 try{
  const {default:useQueue}=await server.ssrLoadModule('/src/useWorkbenchQueue.js');
  function Probe(){state=useQueue('protocol',0);return React.createElement('span',null,state.data?.queue_revision||'unknown');}
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  assert.equal(state.data.queue_revision,'exact-union');
  await act(async()=>state.reload());
  assert.equal(state.loading,true);assert.equal(state.data.queue_revision,'exact-union');
  await act(async()=>release());
  assert.equal(state.loading,false);assert.equal(state.data.queue_revision,'exact-union');assert.match(state.error,/unavailable/);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
