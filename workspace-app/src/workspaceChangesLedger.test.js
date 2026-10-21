import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {applyWorkspaceChange,INITIAL_WORKSPACE_CHANGES,protocolClock} from './useWorkspaceChanges.js';
import {isMergeUndone,MERGE_UNDONE_MESSAGE} from './incoming-workbench/workbenchAuthority.js';

// Request ledgers through the mounted App, Protocol, Inspector, Workbench queue
// and product hooks; only HTTP is a fixture. Each step counts requests sent.
const visible=node=>{for(let current=node;current;current=current.parent)if(current.props?.hidden||current.props?.inert)return false;return true;};
function serve(h,state={queue:'q1',pending:12}){
 h.fixture.respond=async(url,options,fallback)=>{
  const path=url.pathname.replace(/^\/api/,'');
  if(path==='/workbench/summary')return {contract_version:1,workbench_counts:[{protocol_uuid:'protocol-A',pending_epoch_count:state.pending,pending_cell_count:1,eligible_pending_epoch_count:state.pending,eligible_pending_cell_count:1,pending_new_cell_count:0,pending_recordings:[],left_out_epoch_count:0,main_blocked_reason:null,queue_revision:state.queue,capabilities:{cumulative_pending_browse:true,additive_accept:true,merge_all:true}}]};
  if(/\/protocols\/protocol-[AB]\/workbench$/.test(path))return {contract_version:1,protocol_uuid:'protocol-A',queue_revision:state.queue,pending_epoch_count:0,pending_cell_count:0,candidates:[],next_cursor:null,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}};
  if(path==='/protocols/protocol-A/workbench/merge-all'){const body=JSON.parse(options.body);state.queue='q2';state.pending=0;return {operation_uuid:body.operation_uuid,mode:'all',accepted_epoch_count:12,candidate_scope_revision:'s',protocol_uuid:'protocol-A',candidate_revision_uuid:'u',actor:'author',binding:{version:3,revision_uuid:'m'},event_uuid:'e'};}
  if(path==='/protocols/protocol-A/workbench/undo')return {binding:{version:4,revision_uuid:'m2'},restored_revision_uuid:'r',removed_epoch_count:12};
  if(path==='/annotation-profiles')return {selected_profile_uuid:'author',profiles:[{profile_uuid:'author',display_name:'Scientist'}]};
  if(path==='/overview')return {project:{project_uuid:'project',name:'Fixture'},protocols:[{protocol_uuid:'protocol-A',name:'Test'},{protocol_uuid:'protocol-B',name:'Two'}],sources:[]};
  return fallback();
 };
}
async function step(h,action,ms=500){const before=h.fixture.requests.length;await h.act(action);await h.settle(ms);return h.fixture.requests.slice(before).map(request=>`${request.method} ${request.path}`);}
const tab=(h,name)=>h.root.findAllByProps({'aria-label':name}).find(node=>visible(node)&&node.props.role==='tab');
const protocolView=h=>h.root.findAll(node=>typeof node.props?.onMergeIncoming==='function'&&typeof node.props.onChange==='function'&&node.props.id).find(visible);

test('merge-all and its undo send one POST and at most two GETs, scoped to that protocol',async()=>{
 const h=await createWorkflowHarness();h.fixture.route={page:'protocol',protocol:'protocol-A',key:'route-1'};serve(h);
 try{
  await step(h,()=>h.mount(),800);
  const merged=await step(h,async()=>{await protocolView(h).props.onMergeIncoming('protocol-A',{kind:'merge_all',queue_revision:'q1',origin:'protocol-overview'});},800);
  assert.equal(merged.filter(line=>line.startsWith('POST')).length,1,merged.join('\n'));
  assert.ok(merged.filter(line=>line.startsWith('GET')).length<=2,merged.join('\n'));
  for(const unrelated of ['/projects','/jobs','/metadata/status','/protocol-suggestions','/overview'])assert.ok(!merged.includes(`GET ${unrelated}`),`${unrelated} is not re-read for a membership change`);
  const toast=h.root.findAll(node=>node.props?.controller&&Object.hasOwn(node.props,'projectId')&&node.props.controller.state!==undefined)[0];
  assert.equal(toast.props.controller.state.phase,'merged');
  const undone=await step(h,async()=>{await toast.props.controller.undo();},800);
  assert.equal(undone.filter(line=>line.startsWith('POST')).length,1,undone.join('\n'));
  assert.ok(undone.filter(line=>line.startsWith('GET')).length<=2,undone.join('\n'));
  assert.ok(undone.includes('GET /workbench/summary'),'pending counts refresh after undo');
 }finally{await h.close();}
});

test('returning to an unchanged Workbench or Inspect tab sends no reads',async()=>{
 const h=await createWorkflowHarness();h.fixture.route={page:'protocol',protocol:'protocol-A',key:'route-1'};serve(h);
 try{
  await step(h,()=>h.mount(),800);
  await step(h,()=>tab(h,'Workbench').props.onClick());
  await step(h,()=>tab(h,'Overview').props.onClick());
  assert.deepEqual(await step(h,()=>tab(h,'Workbench').props.onClick()),[],'Workbench queue is retained');
  await step(h,()=>tab(h,'Inspect').props.onClick(),800);
  await step(h,()=>tab(h,'Overview').props.onClick());
  assert.deepEqual(await step(h,()=>tab(h,'Inspect').props.onClick(),800),[],'Inspect browse descriptor and page are retained');
  // A real change for this protocol still refreshes its pages on return.
  await step(h,()=>tab(h,'Overview').props.onClick());
  await step(h,()=>protocolView(h).props.onChange({kind:'membership',protocolId:'protocol-A'}));
  const after=await step(h,()=>tab(h,'Inspect').props.onClick(),800);
  assert.ok(after.some(line=>line.includes('/protocols/protocol-A?projection=browse')),after.join('\n'));
 }finally{await h.close();}
});

test('an off-page epoch click reads its page once',async()=>{
 const h=await createWorkflowHarness({total:500,liveMetadata:false});
 try{
  const props={protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-0',expected_binding_version:2,cells:[{cell_uuid:'cell-0',date:'2026-09-29',label:'Cell 0',epochs:500}]},filters:{},revision:0,structureRevision:0,initialEpochUuid:'epoch-0'};
  const Inspector=await h.component('Inspector');
  await h.mount(Inspector,props);await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
  const date=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-date');
  await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
  const cell=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-cell');
  await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
  const row=ordinal=>h.root.findAllByType('button').find(node=>node.props['aria-label']?.startsWith('Inspect ')&&node.props['aria-label'].endsWith(` epoch ${ordinal}`));
  await h.waitFor(()=>!!row(1));await h.settle(300);
  await h.act(()=>h.root.findAllByType('button').find(node=>node.props.children==='Load more epochs').props.onClick());
  await h.waitFor(()=>!!row(61));await h.settle(300);
  const reads=(await step(h,()=>row(61).props.onClick({}),600)).filter(line=>line.includes('/protocols/protocol-A/epochs?'));
  assert.equal(reads.length,1,reads.join('\n'));
  assert.equal(h.viewer.epoch?.epoch_uuid,'epoch-60');
 }finally{await h.close();}
});

test('typed change kinds advance only the clocks their readers depend on',()=>{
 let state=INITIAL_WORKSPACE_CHANGES;
 const clocks=()=>({revision:state.revision,structure:state.structureRevision,review:state.reviewRevision,a:protocolClock(state.revision,state,'A'),b:protocolClock(state.revision,state,'B')});
 const start=clocks();
 state=applyWorkspaceChange(state,{kind:'membership',protocolId:'A'});
 assert.deepEqual({...clocks(),a:undefined},{...start,a:undefined},'membership leaves global, structure, review and other protocols');
 assert.notEqual(clocks().a,start.a);assert.equal(state.membershipRevision,1);assert.equal(state.contentRevision,1);
 assert.equal(state.last.kind,'membership');assert.equal(state.last.protocolId,'A');
 const beforeCuration=clocks();state=applyWorkspaceChange(state,{kind:'curation',protocolId:'B'});
 assert.equal(clocks().revision,beforeCuration.revision);assert.notEqual(clocks().b,beforeCuration.b);assert.equal(state.membershipRevision,1,'curation is not membership');
 const beforeStructure=clocks();state=applyWorkspaceChange(state,{kind:'structure'});
 for(const key of ['revision','structure','review'])assert.notEqual(clocks()[key],beforeStructure[key]);
 // Untyped events keep the original clocks: a bare change is structural.
 const beforeBare=clocks();state=applyWorkspaceChange(state);assert.notEqual(clocks().structure,beforeBare.structure);
 const beforeLegacy=clocks();state=applyWorkspaceChange(state,{kind:'curation'});
 assert.notEqual(clocks().revision,beforeLegacy.revision);assert.equal(clocks().structure,beforeLegacy.structure);
 const steady=state;assert.equal(applyWorkspaceChange(state,{kind:'annotations',tagChannel:true}),steady,'tag channel stays off these clocks');
});

test('undone merges are named instead of reported as accepted',()=>{
 assert.equal(isMergeUndone(Object.assign(Error('x'),{status:409,data:{code:'workbench_merge_undone'}})),true);
 assert.equal(isMergeUndone(Object.assign(Error('x'),{status:409,data:{code:'workbench_conflict'}})),false);
 assert.equal(isMergeUndone(Object.assign(Error('x'),{status:500,data:{code:'workbench_merge_undone'}})),false);
 assert.match(MERGE_UNDONE_MESSAGE,/undone/);
});

// PR #91 receipt shape: post-write curation for every requested epoch, the
// query revision the next write must send, and the echoed binding version.
function serveCurationReceipts(h,{receipts=true}={}){
 const state={generation:0,included:new Map(),stale:0};
 const base=h.fixture.respond;
 h.fixture.respond=async(url,options,fallback)=>{
  const path=url.pathname.replace(/^\/api/,''),body=options.body?JSON.parse(options.body):null;
  if(path==='/protocols/protocol-A/curation/read'){
   if(body.query_revision!==`query-${state.generation}`){state.stale++;throw Object.assign(Error('The inspected query or dataset binding changed. Refresh before saving.'),{status:409});}
   return {protocol_uuid:'protocol-A',query_revision:body.query_revision,expected_binding_version:body.expected_binding_version,epochs:body.epoch_uuids.map(id=>({epoch_uuid:id,cell_uuid:'cell-0',curation_revision:state.generation}))};
  }
  if(path==='/protocols/protocol-A/curation'){
   if(body.query_revision!==`query-${state.generation}`){state.stale++;throw Object.assign(Error('stale'),{status:409});}
   for(const id of body.epoch_uuids)if('included' in body.changes)state.included.set(id,body.changes.included);
   state.generation++;h.fixture.generation=state.generation;
   if(!receipts)return {curation:{},event_uuid:null};
   return {curation:Object.fromEntries(body.epoch_uuids.map(id=>[id,{included:state.included.get(id)??true,tags:[],review_state:'unreviewed',revision:state.generation,metadata_fingerprint:'f',approval_stale:false}])),
    event_uuid:null,query_revision:`query-${state.generation}`,expected_binding_version:body.expected_binding_version,curation_revisions:Object.fromEntries(body.epoch_uuids.map(id=>[id,state.generation]))};
  }
  return base?base(url,options,fallback):fallback();
 };
 return state;
}
async function openInspect(h){
 h.fixture.route={page:'protocol',protocol:'protocol-A',key:'route-1',inspection:{epoch_uuid:'epoch-0'}};serve(h);
 await step(h,()=>h.mount(),800);
 await step(h,()=>tab(h,'Inspect').props.onClick(),800);
 await h.waitFor(()=>!!h.viewer?.treePane?.listProps&&!h.viewer.treePane.listProps.disabled);
 const date=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-date');
 await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
 const cell=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-cell');
 await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
 await h.settle(500);
}
test('an inclusion toggle applies its curation receipt in place: 1 write, 0 page/tree reloads, chained revision',async()=>{
 const h=await createWorkflowHarness({total:40,liveMetadata:false});
 try{
  await openInspect(h);const state=serveCurationReceipts(h);
  const row={epoch_uuid:'epoch-3',cell_uuid:'cell-0'};
  for(const included of [false,true,false]){
   await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
   const sent=await step(h,()=>h.viewer.treePane.listProps.onToggleInclusion({...row,curation:{included:!included}},included),600);
   assert.deepEqual(sent.filter(line=>line.startsWith('POST')),['POST /protocols/protocol-A/curation/read','POST /protocols/protocol-A/curation'],sent.join('\n'));
   assert.deepEqual(sent.filter(line=>line.startsWith('GET')),[],'no page, tree, detail or summary reloads: '+sent.join('\n'));
   assert.equal(h.viewer.treePane.listProps.inclusionForEpoch({...row,curation:{included:true,tags:[]}}).curation.included,included,'row shows the receipt state');
  }
  assert.equal(state.stale,0,'each next write sent the chained query revision');
 }finally{await h.close();}
});
test('without a receipt the toggle keeps the reload path',async()=>{
 const h=await createWorkflowHarness({total:40,liveMetadata:false});
 try{
  await openInspect(h);serveCurationReceipts(h,{receipts:false});
  const sent=await step(h,()=>h.viewer.treePane.listProps.onToggleInclusion({epoch_uuid:'epoch-3',cell_uuid:'cell-0',curation:{included:true}},false),800);
  assert.ok(sent.some(line=>line.startsWith('GET /protocols/protocol-A/epochs?')),sent.join('\n'));
 }finally{await h.close();}
});


test('curation refreshes visible review queues on return before merge without reloading hidden browsing',async()=>{
 const h=await createWorkflowHarness({total:40,liveMetadata:false,realProtocolSuggestion:true});
 const state={queue:'q1',pending:12};serve(h,state);
 const props={id:'protocol-A',projectId:'project',revision:0,structureRevision:0,reviewRevision:0,curationRevision:0,onChange(){},
  onMergeIncoming:async(id,options)=>{assert.equal(options.queue_revision,state.queue);await (await h.module('api.js')).api('/protocols/protocol-A/workbench/merge-all',{method:'POST',body:{expected_queue_revision:options.queue_revision,operation_uuid:'merge-one'}});return true;}};
 const base=h.fixture.respond;
 h.fixture.respond=async(url,options,fallback)=>{
  const path=url.pathname.replace(/^\/api/,'');
  if(path==='/protocols/protocol-A/workbench')return {contract_version:1,protocol_uuid:'protocol-A',queue_revision:state.queue,
   pending_epoch_count:state.pending,pending_cell_count:1,eligible_pending_epoch_count:state.pending,eligible_pending_cell_count:1,
   candidates:[],next_cursor:null,capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true,merge_all:true}};
  if(path==='/protocols/protocol-A/workbench/merge-all')assert.equal(JSON.parse(options.body).expected_queue_revision,state.queue,'merge must use the new curation fence');
  return base(url,options,fallback);
 };
 const queueReads=lines=>lines.filter(line=>line.startsWith('GET /protocols/protocol-A/workbench?'));
 const hold=()=>h.root.findAllByType('button').find(node=>visible(node)&&node.props['aria-label']==='Hold to merge all');
 try{
  await step(h,()=>h.mount(h.Protocol,props),800);assert.ok(hold());
  await step(h,()=>tab(h,'Workbench').props.onClick());
  await step(h,()=>tab(h,'Inspect').props.onClick(),800);
  state.queue='q2';
  const changed=await step(h,()=>h.render(h.Protocol,{...props,curationRevision:1}));
  assert.deepEqual(changed,[],'applied receipt must not reload hidden queues or main browsing');
  const review=await step(h,()=>tab(h,'Workbench').props.onClick());
  assert.equal(queueReads(review).length,1,'Workbench renews its queue after receipt curation');
  const overview=await step(h,()=>tab(h,'Overview').props.onClick());
  assert.equal(queueReads(overview).length,1,'Overview merge card renews independently on reveal');
  assert.ok(hold());
  await h.act(()=>hold().props.onPointerDown({button:0,preventDefault(){}}));await h.settle(1200);
  const merged=h.fixture.requests.filter(call=>call.path==='/protocols/protocol-A/workbench/merge-all');
  assert.equal(merged.length,1);assert.equal(merged[0].body.expected_queue_revision,'q2');
 }finally{await h.close();}
});
