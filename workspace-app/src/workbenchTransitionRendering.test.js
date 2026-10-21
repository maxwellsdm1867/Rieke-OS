import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
const response=value=>({ok:true,status:200,headers:new Headers({'X-Disco-Workbench-Context':'fresh-v1'}),json:async()=>value});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
async function harness(){
 const name=`__workbenchFlow${Math.random().toString(36).slice(2)}`;
 const profile={profileUuid:'author-a',loading:false,error:null};globalThis[name]=profile;
 const probe={name:'workflow-inspector',enforce:'pre',resolveId(source,importer){
  if(source.endsWith('/annotations/annotationProfile.js')||source.endsWith('../../annotations/annotationProfile.js'))return '\0flow-profile';
  if(importer?.endsWith('/FrozenIncomingReview.jsx')&&source==='../../epoch-browser/ui/Inspector.jsx')return '\0flow-inspector';
 },load(id){if(id==='\0flow-profile')return `export const useAnnotationProfile=()=>globalThis[${JSON.stringify(name)}];`;
  if(id==='\0flow-inspector')return `import React from 'react';export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=true;export default function Inspector(props){return React.createElement('div',{'data-scope':props.readContext.candidate_scope_revision});}`;
 }};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,plugins:[probe],server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',esbuild:{jsx:'automatic'}});
 const [{default:Review},{default:Suggestion},{default:useQueue},{createMergeUndo},{createSourceMerge},{api}]=await Promise.all([
  server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx'),server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx'),
  server.ssrLoadModule('/src/incoming-workbench/useWorkbenchQueue.js'),server.ssrLoadModule('/src/incoming-workbench/mergeUndo.js'),
  server.ssrLoadModule('/src/incoming-workbench/sourceMerge.js'),server.ssrLoadModule('/src/api.js')]);
 let membership=0,binding=1,version=1,excluded=false,blocked=null,selected=[],renderer,saved,queueState,held=null,epoch=0;
 const calls=[],receipts=new Map(),oldFetch=globalThis.fetch;
 const queue=()=>({contract_version:1,queue_revision:`q-${membership}-${excluded}-${profile.profileUuid}`,pending_epoch_count:membership||excluded?0:2,pending_cell_count:membership||excluded?0:1,eligible_pending_epoch_count:membership||excluded?0:2,eligible_pending_cell_count:membership||excluded?0:1,left_out_epoch_count:excluded?2:0,main_blocked_reason:blocked,pending_recordings:[{filename:'fixture.h5',source_sha256:'source'}],total_candidate_count:1,candidates:[{candidate_revision_uuid:'original',status:membership?'accepted':'pending',source_filename:'fixture.h5',eligible_pending_epoch_count:membership||excluded?0:2}],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}});
 const context=()=>({actor:profile.profileUuid,candidate_revision_uuid:'same-candidate',candidate_scope_revision:`scope-${binding}-${version}-${profile.profileUuid}`,expected_binding_version:binding,protocol:{definition:{protocol_uuid:'p',project_uuid:'project'},counts:{epochs:membership?0:2},cells:[]},counts:{pending_epochs:membership?0:2,pending_cells:membership?0:1,excluded_epochs:excluded?2:0},draft:{draft_version:version,selection_mode:'selected',decisions:selected.map(epoch_uuid=>({epoch_uuid,selected:true,reviewed:true,excluded})),decisions_total:selected.length,decisions_truncated:false}});
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):null;calls.push({endpoint,body});
  if(endpoint==='/protocols/p/workbench?limit=20'){const value=queue();if(held){const wait=held;held=null;await wait.promise;}return response(value);}
  if(endpoint==='/protocols/p/workbench/prepare'){const c=context();return response({contract_version:1,kind:'workbench_pending_union',actor:profile.profileUuid,prepare_operation_uuid:`prepare-${binding}`,candidate_revision_uuid:c.candidate_revision_uuid,root:'/protocols/p/workbench/candidates/same-candidate',candidate_scope_revision:c.candidate_scope_revision,queue_revision:body.expected_queue_revision,context:c});}
  if(endpoint.endsWith('/context'))return response(context());
  if(endpoint.endsWith('/draft')){selected=body.decisions.filter(x=>x.selected).map(x=>x.epoch_uuid);version++;return response(context());}
  if(endpoint.endsWith('/preview'))return response({preview_sha256:`preview-${binding}`,expected_binding_version:binding,expected_query_revision:`main-${binding}`,selected_epoch_count:selected.length,accepted_epoch_count:selected.length,already_present_epoch_count:0,retained_epoch_count:10,next_epoch_count:10+selected.length,accepted_cell_count:1});
  if(endpoint.endsWith('/accept')||endpoint.endsWith('/merge-all')){
   membership=2;binding++;const receipt={operation_uuid:body.operation_uuid,protocol_uuid:'p',candidate_revision_uuid:'same-candidate',event_uuid:`event-${binding}`,binding:{revision_uuid:`main-${binding}`,version:binding},accepted_epoch_count:2,mode:endpoint.endsWith('/merge-all')?'all':'selected',undone:false};receipts.set(body.operation_uuid,receipt);return response(receipt);
  }
  if(endpoint.endsWith('/undo')){membership=0;binding++;receipts.get(body.operation_uuid).undone=true;return response({binding:{revision_uuid:'main-original',version:binding},restored_revision_uuid:'main-original',removed_epoch_count:2});}
  if(endpoint.includes('/receipts/'))return response(receipts.get(endpoint.split('/').at(-1)));
  throw Error(`Unexpected request: ${endpoint}`);
 };
 const undo=createMergeUndo({request:api}),source=createSourceMerge({projectId:'project',request:api});
 const announce=receipt=>undo.show(receipt,{projectId:'project',protocolName:'Fixture'});
 async function mergeAll(_protocol,options){const result=await source.startAll('p',options);announce(result.receipt);return true;}
 function App({revision=0,provided,session,show=true}){
  const q=useQueue('p',revision,provided,'project');queueState=q;
  return React.createElement(React.Fragment,null,
   React.createElement(Suggestion,{projectId:'project',pendingProtocol:'p',main:{counts:{epochs:10}},queue:q.data,onMerge:mergeAll}),
   show&&React.createElement(Review,{projectId:'project',protocolId:'p',revision,queue:q,session,onSession:value=>{saved=value;},onMerged:announce,onRefresh:q.reload,onChange:q.reload}));
 }
 const render=async props=>act(async()=>{const next=React.createElement(App,props);renderer?renderer.update(next):renderer=TestRenderer.create(next);});
 return {render,profile,calls,queue,context,undo,get root(){return renderer.root;},get saved(){return saved;},get state(){return queueState;},get text(){return label(renderer.root);},get membership(){return membership;},
  set excluded(value){excluded=value;},set blocked(value){blocked=value;},hold(){held=deferred();return held;},
  async refresh(){await act(async()=>queueState.reload());},
  async overviewMerge(){await act(async()=>renderer.root.findByType(Suggestion).props.onMerge('p',{queue_revision:queue().queue_revision}));},
  async unmount(){await act(async()=>renderer.unmount());renderer=null;},
  async close(){if(renderer)await act(async()=>renderer.unmount());source.close();globalThis.fetch=oldFetch;delete globalThis[name];await server.close();}
 };
}

test('Overview merge and Undo reconcile a retained Workbench even when queue and candidate identities repeat',async()=>{
 const h=await harness();try{
  await h.render({});assert.match(h.text,/New data matches your saved query/);
  await act(async()=>assert.equal(h.root.find(node=>node.type?.name==='Inspector').props.onRefreshEpochs(),true));
  await h.overviewMerge();assert.equal(h.membership,2);assert.doesNotMatch(h.text,/New data matches your saved query/);assert.match(h.text,/No pending cells/);
  const wait=h.hold();await h.refresh();
  await act(async()=>h.undo.undo());
  assert.match(h.text,/New data matches your saved query/);
  await act(async()=>wait.resolve());
  const inspector=h.root.find(node=>node.type?.name==='Inspector');assert.equal(inspector.props.draftSelection.disabled,false);
  assert.equal(h.root.findAllByProps({role:'alert'}).length,0);
  await act(async()=>inspector.props.draftSelection.onMerge(['a','b']));
  assert.equal(h.membership,0);assert.match(h.text,/Selected incoming additions/);
  const confirm=()=>h.root.findAllByType('button').find(n=>label(n)==='Add these additions to main');
  await act(async()=>confirm().props.onClick());assert.equal(h.membership,2);assert.match(h.text,/Merge complete, no pending cells/);
  await h.refresh();assert.match(h.text,/Merge complete, no pending cells/);
  await act(async()=>h.undo.undo());assert.equal(h.membership,0);
  assert.equal(h.root.find(node=>node.type?.name==='Inspector').props.draftSelection.disabled,false,'undone receipt never locks the restored candidate');
  assert.equal(h.root.findAllByProps({role:'alert'}).length,0);
  const session=h.saved;await h.unmount();await h.render({session});
  assert.equal(h.root.find(node=>node.type?.name==='Inspector').props.draftSelection.disabled,false,'reopening checks durable undone status');
 }finally{await h.close();}
});

test('provided queues and same-author reload retire correctly; late old-author data cannot publish',async()=>{
 const h=await harness();try{
  const provided=h.queue();await h.render({provided});
  await h.overviewMerge();assert.equal(h.state.data.pending_epoch_count,0,'shared merge invalidates the unchanged provided snapshot');
  await act(async()=>h.undo.undo());assert.equal(h.state.data.pending_epoch_count,2);
  h.profile.loading=true;await h.render({provided});assert.equal(h.state.loading,true);
  h.profile.loading=false;await h.render({provided});assert.equal(h.state.loading,false);assert.equal(h.state.data.pending_epoch_count,2);
  const wait=h.hold();await h.refresh();
  h.profile.profileUuid='author-b';h.excluded=true;await h.render({provided});
  await act(async()=>wait.resolve());assert.equal(h.state.data.pending_epoch_count,0);assert.match(h.state.data.queue_revision,/author-b/);
 }finally{await h.close();}
});

test('blocked discovery is distinct from empty completion and left-out epochs have an explicit review path',async()=>{
 const h=await harness();try{
  h.excluded=true;await h.render({});assert.match(h.text,/2 epochs left out/);
  assert.equal(h.root.findAll(node=>node.type?.name==='Inspector').length,0);
  await act(async()=>h.root.findAllByType('button').find(n=>label(n)==='Review left-out epochs').props.onClick());
  assert.equal(h.root.find(node=>node.type?.name==='Inspector').props.draftSelection.disabled,false);
  h.blocked='Main metadata changed. Refresh the saved query.';await h.refresh();
  assert.match(h.text,/Main metadata changed/);assert.doesNotMatch(h.text,/Merge complete|No pending cells/);
  assert.equal(h.root.findAll(node=>node.type?.name==='Inspector').length,0);
 }finally{await h.close();}
});

test('proposal history isolates author recovery and restores it after switching back',async()=>{
 const name=`__actorHistory${Math.random().toString(36).slice(2)}`;globalThis[name]={profileUuid:'a',loading:false};
 const plugin={name:'actor-history',enforce:'pre',resolveId(source,importer){
  if(source.endsWith('/annotations/annotationProfile.js'))return '\0history-profile';
  if(importer?.endsWith('/IncomingWorkbench.jsx')&&source==='./FrozenIncomingReview.jsx')return '\0history-review';
 },load(id){if(id==='\0history-profile')return `export const useAnnotationProfile=()=>globalThis[${JSON.stringify(name)}];`;
  if(id==='\0history-review')return `import React from 'react';export default function HistoryReview(props){return React.createElement('div');}`;
 }};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,plugins:[plugin],server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',esbuild:{jsx:'automatic'}});
 const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
 const oldFetch=globalThis.fetch;const queue={contract_version:1,queue_revision:'q',pending_epoch_count:2,pending_cell_count:1,candidates:[{candidate_revision_uuid:'same'}],capabilities:{frozen_browse:true,cumulative_pending_browse:true,drafts:true,additive_accept:true,incoming_export:true}};
 let release=null,reads=0;globalThis.fetch=async()=>{reads++;if(release)await release.promise;return response(queue);};
 let renderer,saved;const original={unconfirmed:true,operation:'a-operation',preview:{preview_sha256:'a-preview'}};
 const props={projectId:'p',protocolId:'history',authority:queue,initialCandidateId:'same',session:{sessionActor:'a',history:true,active:'same',drafts:{same:original}},onSession:value=>{saved=value;}};
 const render=()=>act(async()=>{const view=React.createElement(Workbench,props);renderer?renderer.update(view):renderer=TestRenderer.create(view);});
 const review=()=>renderer.root.find(node=>node.type?.name==='HistoryReview');
 try{
  await render();assert.deepEqual(review().props.session,original);
  release=deferred();globalThis[name]={profileUuid:'b',loading:false};await render();
  assert.equal(reads,1,'switching author retires the supplied summary even across the keyed remount');
  assert.equal(renderer.root.findAll(node=>node.type?.name==='HistoryReview').length,0,'old author summary stays inert while fresh read is held');
  await act(async()=>release.resolve());release=null;assert.equal(review().props.session,undefined,'B never receives A recovery');
  await act(async()=>review().props.onSession({selected:['b-epoch']}));
  globalThis[name]={profileUuid:'a',loading:false};await render();assert.deepEqual(review().props.session,original);
  assert.equal(saved.sessionsByActor.a.drafts.same.operation,'a-operation');assert.deepEqual(saved.sessionsByActor.b.drafts.same.selected,['b-epoch']);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;delete globalThis[name];await server.close();}
});
