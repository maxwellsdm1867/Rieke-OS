import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const suggestion={protocol_uuid:'protocol-A',protocol_name:'Test',candidate_revision_uuid:'original',status:'pending',diff_counts:{added:2,removed:0,changed:0}};
for(const entry of ['Main match card','import page'])test(`actual App ${entry} wires a user request to the cumulative preview handoff`,async()=>{
 const h=await createWorkflowHarness();
 h.fixture.route=entry==='Main match card'?{page:'protocol',protocol:'protocol-A',key:'main'}:{page:'import',key:'import'};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/protocol-suggestions'?{suggestions:[suggestion]}:url.pathname==='/api/workbench/summary'?{workbench_counts:[]}:url.pathname.endsWith('/protocols/protocol-A/workbench')?{contract_version:1,queue_revision:'empty',pending_epoch_count:0,pending_cell_count:0,candidates:[],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}}:fallback();
 try{
  await h.mount();await h.waitFor(()=>h.root.findAll(node=>['workflow-child','import-suggestions'].includes(node.type)&&typeof node.props.onMerge==='function').length>0);
  const card=h.root.findAll(node=>['workflow-child','import-suggestions'].includes(node.type)&&typeof node.props.onMerge==='function')[0];
  await h.act(()=>assert.equal(card.props.onMerge('protocol-A'),true));
  await h.waitFor(()=>h.root.findAllByProps({className:'incoming-workbench'}).length>0);await h.settle(30);
  assert.equal(h.root.findAllByProps({'aria-label':'Workbench'})[0].props['aria-selected'],true);
  assert.ok(h.root.findAllByProps({role:'status'}).some(node=>node.children.join('').includes('No pending incoming recordings to merge')),'intent reached the real IncomingWorkbench hook');
  assert.ok(h.fixture.requests.every(r=>!r.path.includes('apply-to-protocol')&&!r.path.endsWith('/accept')));
 }finally{await h.close();}
});

test('held import source merges without entering Workbench and opens Overview only after receipt',async()=>{
 const h=await createWorkflowHarness();h.fixture.route={page:'import',key:'direct-source'};
 let release,started;const accepted=new Promise(resolve=>{started=resolve});
 h.fixture.respond=async(url,options,fallback)=>{
  const path=url.pathname;
  if(path.endsWith('/workbench/candidates/original/context'))return {candidate_revision_uuid:'original',actor:'author',source_additive_accept:true,candidate_scope_revision:'scope',draft:{draft_version:0,decisions_truncated:true},protocol:{definition:{protocol_uuid:'protocol-A'}}};
  if(path.endsWith('/workbench/candidates/original/preview'))return {mode:'source',source_sha256:'source',candidate_scope_revision:'scope',expected_draft_version:0,preview_sha256:'preview',expected_binding_version:1,expected_query_revision:'query',selected_epoch_count:1691,accepted_epoch_count:1691,already_present_epoch_count:0,retained_epoch_count:540,next_epoch_count:2231,accepted_cell_count:3};
  if(path.endsWith('/workbench/candidates/original/accept')){const body=JSON.parse(options.body);started();await new Promise(resolve=>{release=resolve});return {...body,candidate_scope_revision:'scope',protocol_uuid:'protocol-A',candidate_revision_uuid:'original',actor:'author',binding:{version:2,revision_uuid:'main'},event_uuid:'event'};}
  return fallback();
 };
 try{
  await h.mount();await h.waitFor(()=>h.root.findAllByType('import-suggestions').length>0);
  let pending;await h.act(()=>{pending=h.root.findByType('import-suggestions').props.onMerge('protocol-A',{kind:'merge_source',candidate_revision_uuid:'original',source_sha256:'source'});});
  await accepted;assert.equal(h.fixture.route.page,'import');assert.equal(h.root.findAllByProps({className:'incoming-workbench'}).length,0);
  await h.act(async()=>{release();await pending;});await h.settle(15);
  assert.equal(h.root.findAllByType('import-suggestions').length,0);assert.equal(h.root.findAllByProps({'aria-label':'Overview'})[0].props['aria-selected'],true);
  assert.equal(h.root.findAllByProps({className:'incoming-workbench'}).length,0);
  assert.ok(h.fixture.requests.every(r=>!r.path.endsWith('/draft')),'direct merge does not mutate a review draft');
 }finally{release?.();await h.close();}
});
