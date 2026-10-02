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
