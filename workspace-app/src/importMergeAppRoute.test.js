import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const visible=node=>{for(let current=node;current;current=current.parent)if(current.props?.hidden||current.props?.inert||current.props?.style?.display==='none')return false;return true;};
const suggestion={protocol_uuid:'protocol-A',protocol_name:'Test',candidate_revision_uuid:'original',status:'pending',diff_counts:{added:2,removed:0,changed:0}};
// The Overview card no longer issues this intent (it holds a source merge); the
// App capability stays covered from both mounted callers.
for(const entry of ['Main match card','import page'])test(`actual App ${entry} wires an explicit cumulative intent to the preview handoff`,async()=>{
 const h=await createWorkflowHarness();
 h.fixture.route=entry==='Main match card'?{page:'protocol',protocol:'protocol-A',key:'main'}:{page:'import',key:'import'};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/protocol-suggestions'?{suggestions:[suggestion]}:url.pathname==='/api/workbench/summary'?{workbench_counts:[]}:url.pathname.endsWith('/protocols/protocol-A/workbench')?{contract_version:1,queue_revision:'empty',pending_epoch_count:0,pending_cell_count:0,candidates:[],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}}:fallback();
 try{
  await h.mount();await h.waitFor(()=>h.root.findAll(node=>['workflow-child','import-suggestions'].includes(node.type)&&typeof node.props.onMerge==='function').length>0);
  const card=h.root.findAll(node=>['workflow-child','import-suggestions'].includes(node.type)&&typeof node.props.onMerge==='function')[0];
  await h.act(()=>assert.equal(card.props.onMerge('protocol-A'),true));
  await h.waitFor(()=>h.root.findAllByProps({className:'incoming-workbench'}).filter(visible).length>0);await h.settle(30);
  assert.equal(h.root.findAllByProps({'aria-label':'Workbench'}).find(visible).props['aria-selected'],true);
  assert.ok(h.root.findAllByProps({role:'status'}).some(node=>node.children.join('').includes('No pending incoming recordings to merge')),'intent reached the real IncomingWorkbench hook');
  assert.ok(h.fixture.requests.every(r=>!r.path.includes('apply-to-protocol')&&!r.path.endsWith('/accept')));
 }finally{await h.close();}
});

// Import review cards are the Overview card from /workbench/summary rows: the
// hold sends the same merge_all request (one POST merge-all with the row's queue
// revision) and the verified receipt shows the corner Undo toast.
test('held import review card merges all pending epochs with one request and shows Undo',async()=>{
 const {importReviewCards,mergeAllRequest}=await import('./protocol-overview/protocolSuggestions.js');
 const h=await createWorkflowHarness();h.fixture.route={page:'import',key:'direct-source'};
 const state={receipt:null};let release,started;const accepted=new Promise(resolve=>{started=resolve});
 h.fixture.respond=async(url,options,fallback)=>{
  const path=url.pathname.replace(/^\/api/,'');
  if(path==='/workbench/summary')return {contract_version:1,workbench_counts:[{protocol_uuid:'protocol-A',pending_epoch_count:state.receipt?0:12,pending_cell_count:state.receipt?0:2,eligible_pending_epoch_count:state.receipt?0:12,eligible_pending_cell_count:state.receipt?0:2,pending_new_cell_count:1,pending_recordings:[],left_out_epoch_count:0,main_blocked_reason:null,queue_revision:state.receipt?'q2':'q1',capabilities:{cumulative_pending_browse:true,additive_accept:true,merge_all:true}}]};
  if(path==='/protocols/protocol-A/workbench/merge-all'){const body=JSON.parse(options.body);started();await new Promise(resolve=>{release=resolve});state.receipt={operation_uuid:body.operation_uuid,mode:'all',accepted_epoch_count:12,candidate_scope_revision:'scope',protocol_uuid:'protocol-A',candidate_revision_uuid:'union',actor:'author',binding:{version:2,revision_uuid:'main'},event_uuid:'event'};return state.receipt;}
  if(path==='/annotation-profiles')return {selected_profile_uuid:'author',profiles:[{profile_uuid:'author',display_name:'Scientist'}]};
  return fallback();
 };
 try{
  await h.mount();await h.waitFor(()=>h.root.findAll(node=>node.type==='import-suggestions'&&node.props.workbenchSummary?.data?.contract_version===1).length>0);
  const props=h.root.findByType('import-suggestions').props;
  const model=importReviewCards({summary:props.workbenchSummary.data,protocols:props.protocols});
  assert.equal(model.ready,1);const request=mergeAllRequest(model.other[0].card);
  let pending;await h.act(()=>{pending=props.onMerge('protocol-A',request);});
  await accepted;assert.equal(h.fixture.route.page,'import');assert.equal(h.root.findAllByProps({className:'incoming-workbench'}).filter(visible).length,0);
  await h.act(async()=>{release();assert.equal(await pending,true);});await h.settle(15);
  const writes=h.fixture.requests.filter(r=>r.method!=='GET');
  assert.deepEqual(writes.map(r=>r.path),['/protocols/protocol-A/workbench/merge-all'],'one merge-all request, no per-recording merge');
  assert.deepEqual({...writes[0].body,operation_uuid:'op'},{expected_queue_revision:'q1',operation_uuid:'op'});
  const toast=h.root.findAll(node=>node.props?.controller&&Object.hasOwn(node.props,'projectId')&&node.props.controller.state!==undefined)[0];
  assert.equal(toast.props.controller.state?.phase,'merged','the corner Undo toast is shown for the verified receipt');assert.equal(toast.props.controller.state?.count,12);
  assert.equal(h.fixture.route.page,'import','Merge all updates import review in place; only Inspect changes workspace');
  assert.equal(h.root.findAllByProps({className:'incoming-workbench'}).filter(visible).length,0);
 }finally{release?.();await h.close();}
});

// The Overview "New data matches your saved query" card now follows the
// cumulative queue; its hold sends merge_all for the queue revision it showed
// (see protocolSuggestionHold.test.js). Through the actual App that runs
// prepare -> draft all -> preview all -> accept, in place on the Overview.
const overviewHold={kind:'merge_all',queue_revision:'q1',origin:'protocol-overview'};
const unionRoot='/protocols/protocol-A/workbench/candidates/union';
const unionContext=(version,mode)=>({candidate_revision_uuid:'union',candidate_scope_revision:'scope',actor:'author',protocol:{definition:{protocol_uuid:'protocol-A'}},draft:{draft_version:version,selection_mode:mode}});
async function overviewMergeHarness({lost=false}={}){
 const h=await createWorkflowHarness(),state={accepts:0,summaryReads:0,receipt:null,navigations:0};
 let navigate;Object.defineProperty(h.fixture,'navigate',{configurable:true,get:()=>navigate,set:value=>{navigate=(...args)=>{state.navigations++;return value(...args);};}});
 h.fixture.route={page:'protocol',protocol:'protocol-A',key:'main'};
 h.fixture.respond=async(url,options,fallback)=>{
  const path=url.pathname.replace(/^\/api/,'');
  if(path==='/protocol-suggestions')return {suggestions:[]};
  if(path==='/workbench/summary'){state.summaryReads++;return {workbench_counts:[{protocol_uuid:'protocol-A',pending_cell_count:state.receipt?0:4,pending_epoch_count:state.receipt?0:755,queue_revision:state.receipt?'q2':'q1'}]};}
  if(path==='/annotation-profiles')return {selected_profile_uuid:'author',profiles:[{profile_uuid:'author',display_name:'Scientist'}]};
  if(path.endsWith('/protocols/protocol-A/workbench'))return {contract_version:1,queue_revision:'empty',pending_epoch_count:0,pending_cell_count:0,candidates:[],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}};
  if(path==='/protocols/protocol-A/workbench/prepare')return {contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prepare-op',candidate_revision_uuid:'union',root:unionRoot,candidate_scope_revision:'scope',queue_revision:'q1',actor:'author',context:unionContext(3,'selected')};
  if(path===`${unionRoot}/draft`)return unionContext(4,'all');
  if(path===`${unionRoot}/preview`)return {mode:'all',candidate_scope_revision:'scope',expected_draft_version:4,preview_sha256:'preview',expected_binding_version:1,expected_query_revision:'query',selected_epoch_count:755,accepted_epoch_count:755,already_present_epoch_count:0,retained_epoch_count:36,next_epoch_count:791,accepted_cell_count:4};
  if(path==='/protocols/protocol-A/workbench/merge-all'){
   const body=JSON.parse(options.body);if(!state.receipt){state.accepts++;state.receipt={operation_uuid:body.operation_uuid,mode:'all',accepted_epoch_count:755,candidate_scope_revision:'scope',protocol_uuid:'protocol-A',candidate_revision_uuid:'union',actor:'author',binding:{version:2,revision_uuid:'main-two'},event_uuid:'event'};}
   if(lost){lost=false;return {failure:503,error:'Reply lost after commit'};}
   return state.receipt;
  }
  if(path.startsWith('/protocols/protocol-A/workbench/receipts/'))return state.receipt&&path.endsWith(state.receipt.operation_uuid)?state.receipt:{failure:404,error:'No receipt'};
  return fallback();
 };
 await h.mount();
 const cards=()=>h.root.findAll(node=>node.type==='workflow-child'&&node.props.pendingProtocol==='protocol-A'&&typeof node.props.onMerge==='function');
 await h.waitFor(()=>cards().length>0);
 return {h,state,cards};
}

test('Overview card hold merges all pending mergeable epochs in place with one request',async()=>{
 const {h,state,cards}=await overviewMergeHarness();
 try{
  const tile=()=>h.root.findAll(node=>!!node.props&&typeof node.type==='function'&&Object.hasOwn(node.props,'pendingReviewCells')).map(node=>node.props.pendingReviewCells);
  const summaryBefore=state.summaryReads;let result;
  await h.act(async()=>{result=await cards()[0].props.onMerge('protocol-A',overviewHold);});
  assert.equal(result,true);assert.equal(state.accepts,1);
  const writes=h.fixture.requests.filter(r=>r.method!=='GET');
  assert.deepEqual(writes.map(r=>r.path),['/protocols/protocol-A/workbench/merge-all']);
  const merge=writes[0].body;assert.match(merge.operation_uuid,/^[0-9a-f-]{36}$/);
  assert.deepEqual({...merge,operation_uuid:'op'},{expected_queue_revision:'q1',operation_uuid:'op'});
  assert.equal(state.navigations,0,'merging from this Overview neither opens Workbench nor pushes a route');
  assert.equal(h.root.findAllByProps({className:'incoming-workbench'}).filter(visible).length,0);
  await h.waitFor(()=>state.summaryReads>summaryBefore);
  await h.settle(15);assert.ok(tile().includes(0),'the Needs review tile reads the refreshed mergeable count');
  assert.equal(h.root.findAllByProps({'aria-label':'Overview'}).find(visible).props['aria-selected'],true);
 }finally{await h.close();}
});

test('Overview card lost merge-all reply keeps recovery identity; consent is single-use until the receipt is recovered',async()=>{
 const {h,state,cards}=await overviewMergeHarness({lost:true});
 try{
  await h.act(async()=>{await assert.rejects(cards()[0].props.onMerge('protocol-A',overviewHold),/may have completed/);});
  assert.equal(state.accepts,1);
  await h.act(async()=>{await assert.rejects(cards()[0].props.onMerge('protocol-A',overviewHold),/recover/i);});
  assert.equal(h.fixture.requests.filter(r=>r.path.endsWith('/merge-all')).length,1,'a second hold submits nothing while recovery is pending');
  const recovery=h.root.findAll(node=>node.type==='workflow-child'&&node.props.mergeLabel==='Hold to retry merge');
  assert.equal(recovery.length,1);assert.equal(recovery[0].props.identity,state.receipt.operation_uuid,'recovery keeps the original operation UUID');
  await h.act(async()=>{await recovery[0].props.onInspect();});await h.settle(15);
  assert.equal(h.fixture.requests.filter(r=>r.path.endsWith('/merge-all')).length,1,'receipt recovery is a GET, not a resubmission');
  assert.equal(h.root.findAll(node=>node.type==='workflow-child'&&node.props.mergeLabel==='Hold to retry merge').length,0);assert.equal(state.navigations,0);
 }finally{await h.close();}
});
