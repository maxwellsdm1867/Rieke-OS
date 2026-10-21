import test from 'node:test';
import assert from 'node:assert/strict';
import {createMergeUndo,mergeUndoTarget} from './mergeUndo.js';

const receipt=(overrides={})=>({protocol_uuid:'protocol-A',operation_uuid:'op-1',event_uuid:'event',binding:{revision_uuid:'main-2',version:7},accepted_epoch_count:755,mode:'all',...overrides});
const details={projectId:'project',protocolName:'Expanding Spots'};
function harness(respond){
  const calls=[],refreshes=[],states=[];let release;
  const request=(path,options)=>{calls.push([path,structuredClone(options)]);return respond?respond(path,options):new Promise((resolve,reject)=>{release={resolve,reject};});};
  const controller=createMergeUndo({request,refresh:id=>refreshes.push(id),onState:value=>states.push(value)});
  return {controller,calls,refreshes,states,get release(){return release;}};
}

test('a verified receipt shows the toast; undo posts the exact payload once and refreshes after success',async()=>{
  const h=harness();
  assert.equal(h.controller.show(receipt(),details),true);
  assert.deepEqual({...h.controller.state},{projectId:'project',protocolId:'protocol-A',protocolName:'Expanding Spots',count:755,operationUuid:'op-1',bindingVersion:7,phase:'merged',message:'',canUndo:true});
  const first=h.controller.undo(),second=h.controller.undo();
  assert.equal(await second,false,'a second click while pending submits nothing');
  assert.deepEqual(h.calls,[['/protocols/protocol-A/workbench/undo',{method:'POST',body:{operation_uuid:'op-1',expected_binding_version:7}}]]);
  assert.equal(h.controller.state.phase,'undoing');
  h.release.resolve({binding:{revision_uuid:'main-1',version:8},restored_revision_uuid:'main-1',removed_epoch_count:755});
  assert.equal(await first,true);
  assert.deepEqual(h.refreshes,['protocol-A'],'data refreshes like a merge completion');
  assert.equal(h.controller.state.phase,'undone');assert.equal(h.controller.state.message,'Merge undone');assert.equal(h.controller.state.canUndo,false);
  assert.equal(await h.controller.undo(),false);assert.equal(h.calls.length,1);
});

test('409 shows the server reason, removes Undo and does not claim a change',async()=>{
  const h=harness(async()=>{throw Object.assign(Error('Main changed since this merge; it cannot be undone safely.'),{status:409});});
  h.controller.show(receipt(),details);
  assert.equal(await h.controller.undo(),false);
  assert.equal(h.controller.state.phase,'error');assert.equal(h.controller.state.message,'Main changed since this merge; it cannot be undone safely.');
  assert.equal(h.controller.state.canUndo,false);assert.deepEqual(h.refreshes,[]);
  assert.equal(await h.controller.undo(),false);assert.equal(h.calls.length,1);
});

test('an uncertain undo failure refreshes, never retries, and an incomplete reply is not success',async()=>{
  const lost=harness(async()=>{throw Object.assign(Error('Reply lost'),{status:503});});
  lost.controller.show(receipt(),details);await lost.controller.undo();
  assert.match(lost.controller.state.message,/may not have completed/);assert.equal(lost.controller.state.canUndo,false);assert.deepEqual(lost.refreshes,['protocol-A']);
  const partial=harness(async()=>({binding:{}}));partial.controller.show(receipt(),details);await partial.controller.undo();
  assert.equal(partial.controller.state.phase,'error');
});

test('a newer merge replaces the toast and a late reply to the older undo cannot overwrite it',async()=>{
  const h=harness();h.controller.show(receipt(),details);const pending=h.controller.undo();
  h.controller.show(receipt({operation_uuid:'op-2',accepted_epoch_count:3,binding:{revision_uuid:'main-3',version:9}}),details);
  h.release.resolve({binding:{revision_uuid:'main-1',version:10},restored_revision_uuid:'main-1',removed_epoch_count:755});await pending;
  assert.equal(h.controller.state.operationUuid,'op-2');assert.equal(h.controller.state.phase,'merged');
  h.controller.dismiss();assert.equal(h.controller.state,null);
});

test('receipts that cannot identify a merge show nothing; dismiss waits for a pending undo',async()=>{
  for(const bad of [receipt({operation_uuid:''}),receipt({binding:null}),receipt({accepted_epoch_count:-1}),null])assert.equal(mergeUndoTarget(bad,details),null);
  assert.equal(mergeUndoTarget(receipt(),{}),null,'project identity is required');
  const h=harness();h.controller.show(receipt(),details);void h.controller.undo();h.controller.dismiss();
  assert.equal(h.controller.state.phase,'undoing');h.release.resolve({binding:{revision_uuid:'r',version:8},restored_revision_uuid:'r'});
  await new Promise(resolve=>setTimeout(resolve,0));assert.equal(h.controller.state.phase,'undone');
});


test('the same Undo controller reverses Finish reviewing without undoing an earlier merge',async()=>{
 const h=harness();h.controller.show(receipt({operation_uuid:'earlier-merge'}),details);
 const completion={kind:'workbench_review_completion',protocol_uuid:'protocol-A',candidate_revision_uuid:'union',actor:'author',operation_uuid:'finished-review',expected_draft_version:5,left_out_epoch_count:332};
 assert.equal(h.controller.show(completion,details),true);assert.equal(h.controller.state.kind,'review');
 const undo=h.controller.undo();assert.equal(await h.controller.undo(),false);
 assert.deepEqual(h.calls,[['/protocols/protocol-A/workbench/undo-review',{method:'POST',body:{operation_uuid:'finished-review',expected_draft_version:5}}]]);
 h.release.resolve({kind:'workbench_review_undo',protocol_uuid:'protocol-A',operation_uuid:'undo-finished-review',undone_operation_uuid:'finished-review',restored_epoch_count:332});assert.equal(await undo,true);
 assert.equal(h.controller.state.message,'Review reopened');assert.deepEqual(h.refreshes,['protocol-A']);
});

test('a stale review completion refusal does not claim restored pending epochs',async()=>{
 const h=harness(async()=>{throw Object.assign(Error('Review changed after completion'),{status:409});});
 h.controller.show({kind:'workbench_review_completion',protocol_uuid:'protocol-A',candidate_revision_uuid:'union',actor:'author',operation_uuid:'stale-review',expected_draft_version:5,left_out_epoch_count:332},details);
 assert.equal(await h.controller.undo(),false);assert.equal(h.controller.state.phase,'error');assert.match(h.controller.state.message,/Review changed/);assert.deepEqual(h.refreshes,[]);
});
