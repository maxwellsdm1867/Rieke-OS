import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
const proposal={contract_version:1,review_kind:'replacement',candidate_revision_uuid:'frozen-proposal',protocol_uuid:'protocol-A'};
const comparison={contract_version:1,review_kind:'replacement',candidate_revision_uuid:'frozen-proposal',expected_candidate_scope_revision:'scope',expected_binding_version:2,expected_query_revision:'query',preview_sha256:'hash',previous_count:2,next_count:1,diff_counts:{added:0,removed:1,changed:0},compatibility:{compatible:true,epoch_count:1,expected_protocol_id:'Test'}};
test('actual App routes a submitted predicate receipt to its frozen Workbench review',async()=>{
 const h=await createWorkflowHarness();h.fixture.route={page:'explore',key:'explore'};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/workbench/summary'?{workbench_counts:[]}:url.pathname.endsWith('/protocols/protocol-A/workbench')?{contract_version:1,queue_revision:'queue',pending_epoch_count:0,pending_cell_count:0,candidates:[],replacement_reviews:[proposal],capabilities:{replacement_review:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true,cumulative_pending_browse:true}}:url.pathname.endsWith('/replacement-preview')?comparison:fallback();
 try{
  await h.mount();await h.waitFor(()=>h.root.findAll(node=>typeof node.props.onProtocolApplied==='function').length>0);
  const explorer=h.root.findAll(node=>typeof node.props.onProtocolApplied==='function')[0];
  await h.act(()=>explorer.props.onProtocolApplied('protocol-A',proposal));
  await h.waitFor(()=>h.root.findAllByProps({'aria-label':'Frozen protocol change review'}).length>0);
  assert.equal(h.root.findAllByProps({'aria-label':'Workbench'})[0].props['aria-selected'],true);
  assert.equal(h.root.findAllByType('button').find(node=>label(node)==='Accept protocol changes').props.disabled,true);
  assert.ok(h.fixture.requests.every(item=>!item.path.endsWith('/replacement-accept')&&!item.path.endsWith('/apply-to-protocol')));
 }finally{await h.close();}
});
test('real export destination preserves proposal receipt through sidebar pinning',async()=>{
 const h=await createWorkflowHarness(),applied=[];
 const preference={format:'rieke-project-preferences',version:1,project_uuid:'project-route',state:{protocol_shortcuts:{},recent_searches:[]},revisions:{protocol_shortcuts:1,recent_searches:1}};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/project-preferences'?preference:url.pathname.endsWith('/compare-to-protocol')?comparison:url.pathname.endsWith('/propose-to-protocol')?{...proposal,operation_uuid:JSON.parse(options.body).operation_uuid}:fallback();
 try{
  const Dialog=await h.component('ExportSelectionDialog');
  await h.mount(Dialog,{projectId:'project-route',candidate:{revision_uuid:'saved-search',summary:{matched_count:0}},protocols:[{protocol_uuid:'protocol-A',name:'Test'}],initialProtocolId:'protocol-A',onApplied:(...args)=>applied.push(args)});
  assert.equal(h.root.findAllByType('button').find(node=>label(node).startsWith('Export directly')).props.disabled,true);
  assert.equal(h.root.findAllByType('button').find(node=>label(node).startsWith('Create pinned protocol')).props.disabled,true);
  await h.act(()=>h.root.findAllByType('button').find(node=>label(node).startsWith('Update pinned protocol')).props.onClick());
  await h.act(()=>h.root.findAllByType('button').find(node=>label(node)==='Review in Workbench').props.onClick());
  assert.equal(applied[0][0],'protocol-A');assert.equal(applied[0][1].candidate_revision_uuid,'frozen-proposal');
  assert.ok(h.fixture.requests.some(item=>item.path==='/project-preferences'&&item.method==='PUT'));
  assert.ok(h.fixture.requests.every(item=>!item.path.endsWith('/apply-to-protocol')));
 }finally{await h.close();}
});
