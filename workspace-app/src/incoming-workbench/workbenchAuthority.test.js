import test from 'node:test';
import assert from 'node:assert/strict';
import {requireWorkbenchQueue,saveWorkbenchDecisions,previewWorkbench,acceptWorkbench,workbenchCandidateRoot,acceptanceFailureKind,workbenchPreviewCounts} from './workbenchAuthority.js';
const context={candidate_scope_revision:'frozen-scope',draft:{draft_version:4,selection_mode:'all'}};
test('cumulative queue count comes from authority even when overlapping paged candidates differ',()=>{
 const queue={contract_version:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},queue_revision:'union',pending_cell_count:2,pending_epoch_count:30,candidates:[{candidate_revision_uuid:'a',pending_epoch_count:20},{candidate_revision_uuid:'b',pending_epoch_count:20}]};
 assert.equal(requireWorkbenchQueue(queue).pending_cell_count,2);
 assert.equal(requireWorkbenchQueue(queue).pending_epoch_count,30);
 assert.equal(requireWorkbenchQueue({...queue,pending_cell_count:null}).pending_cell_count,null);
 assert.throws(()=>requireWorkbenchQueue({...queue,pending_cell_count:undefined}),/authoritative/);
 assert.throws(()=>requireWorkbenchQueue({...queue,contract_version:2}),/unsupported/);
});
test('bounded draft updates fence each committed batch and stop at conflict without claiming rollback',async()=>{
 const committed=[],bodies=[];
 const decisions=Array.from({length:501},(_,i)=>({epoch_uuid:`e${i}`,selected:true}));
 let writes=0;
 await assert.rejects(()=>saveWorkbenchDecisions({root:'/candidate',context,decisions},async(path,{body})=>{
  bodies.push(body);writes++;if(writes===2)throw Error('revision conflict');
  return {...context,draft:{draft_version:5}};
 },value=>committed.push(value)),/revision conflict/);
 assert.equal(writes,2);assert.equal(committed.length,1);assert.equal(bodies[0].decisions.length,250);assert.equal(bodies[1].decisions.length,250);
 assert.equal(bodies[0].expected_version,4);assert.equal(bodies[1].expected_version,5);
 assert.equal(bodies[1].expected_candidate_scope_revision,'frozen-scope');
});
test('durable defer changes no scientific inclusion or shared annotations',async()=>{
 let body;
 await saveWorkbenchDecisions({root:'/candidate',context,deferred:true},async(path,options)=>{assert.equal(path,'/candidate/draft');body=options.body;return {...context,draft:{draft_version:5}};});
 assert.deepEqual(body,{expected_version:4,expected_candidate_scope_revision:'frozen-scope',decisions:[],deferred:true});
});
test('additive acceptance uses explicit preview fences and stable operation retry identity',async()=>{
 const calls=[];
 const root=workbenchCandidateRoot('protocol','candidate');
 const preview=await previewWorkbench(root,context,'all',async(path,{body})=>{calls.push({path,body});return {preview_sha256:'reviewed-preview',expected_binding_version:9,expected_query_revision:'main-query',counts:{added:6,retained:40}};});
 let attempts=0;
 const request=async(path,{body})=>{calls.push({path,body});if(attempts++===0)throw Error('reply lost');return {binding:{version:10,revision_uuid:'main-combined'},event_uuid:'accept-event',operation_uuid:body.operation_uuid};};
 await assert.rejects(()=>acceptWorkbench(root,preview,'same-operation',request),/reply lost/);
 const receipt=await acceptWorkbench(root,preview,'same-operation',request);
 assert.equal(receipt.binding.revision_uuid,'main-combined');
 assert.deepEqual(calls[1],calls[2]);assert.equal(calls[2].path,`${root}/accept`);assert.equal(calls[2].body.expected_candidate_scope_revision,'frozen-scope');assert.equal(calls[2].body.expected_draft_version,4);assert.equal(calls[2].body.mode,'all');
 assert.equal(calls[2].body.operation_uuid,'same-operation');assert.equal(calls[2].body.expected_binding_version,9);assert.equal(calls[2].body.preview_sha256,'reviewed-preview');
 await assert.rejects(()=>acceptWorkbench(root,preview,'same-operation',async()=>({})),/receipt is incomplete/);
});

test('definitive stale rejection can refresh while uncertain commit preserves its operation',()=>{
 assert.equal(acceptanceFailureKind({status:409}),'rejected');
 assert.equal(acceptanceFailureKind({status:409,saved:true}),'unconfirmed');
 assert.equal(acceptanceFailureKind({status:503}),'unconfirmed');
 assert.equal(acceptanceFailureKind(Error('reply lost')),'unconfirmed');
});

test('preview saves mode with fresh draft fences before comparing; failed compare retains the saved draft',async()=>{
 const calls=[],committed=[];
 const initial={candidate_scope_revision:'before',draft:{draft_version:4,selection_mode:'selected'}};
 await assert.rejects(()=>previewWorkbench('/candidate',initial,'all',async(path,{body})=>{
  calls.push({path,body});
  if(path.endsWith('/draft'))return {candidate_scope_revision:'after',draft:{draft_version:5,selection_mode:'all'}};
  throw Error('Source changed');
 },value=>committed.push(value)),/Source changed/);
 assert.equal(committed.length,1);assert.equal(calls[0].body.selection_mode,'all');
 assert.equal(calls[1].body.expected_candidate_scope_revision,'after');assert.equal(calls[1].body.expected_draft_version,5);
});
test('preview count display uses flat authority fields and rejects unavailable counts',()=>{
 const preview={selected_epoch_count:7,accepted_epoch_count:6,already_present_epoch_count:1,retained_epoch_count:40,next_epoch_count:46,accepted_cell_count:2};
 assert.deepEqual(workbenchPreviewCounts(preview).map(row=>row.count),[7,6,1,40,46,2]);
 assert.throws(()=>workbenchPreviewCounts({...preview,accepted_epoch_count:undefined}),/authoritative/);
});
