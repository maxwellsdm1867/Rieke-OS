import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

const card={suggestion_uuid:'suggestion',protocol_uuid:'protocol-A',protocol_name:'Test',candidate_revision_uuid:'candidate',source_sha256:'source',source_filename:'2026-10-12_F.h5',created_at:'2026-10-14T09:17:00Z',status:'pending',diff_counts:{added:16,removed:0,changed:0}};

// The Overview card uses the same hold-only consent as import review: a plain
// click never merges or navigates, one completed hold submits one exact
// source-scoped request, and a failed merge leaves the card for recovery.
test('Overview match card holds to merge its recording directly and never opens a cumulative preview',async t=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Suggestion}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx');
 let renderer,merges=[],inspected=[],outcome=()=>true;
 let props={suggestion:card,onMerge:async(...args)=>{merges.push(args);return outcome();},onProtocol:(...args)=>inspected.push(args)};
 const render=async()=>act(()=>{const node=React.createElement(Suggestion,props);if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);});
 const buttons=()=>renderer.root.findAllByType('button'),hold=()=>buttons().find(node=>node.props['aria-label']==='Hold to merge');
 const text=()=>JSON.stringify(renderer.toJSON());
 const event={button:0,preventDefault(){}},tick=ms=>act(async()=>{t.mock.timers.tick(ms);await Promise.resolve();});
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();});
 await render();t.mock.timers.enable({apis:['setTimeout']});
 try{
  assert.doesNotMatch(text(),/Merge matched data/,'the click-to-navigate merge button is gone');assert.equal(buttons().length,2);
  assert.ok(hold(),'Overview offers the same hold control as import review');
  assert.match(text(),/2026-10-12_F\.h5/);assert.doesNotMatch(text(),/Merge opens a fresh preview/);
  await act(()=>hold().props.onClick(event));assert.deepEqual(merges,[],'plain click grants no consent');
  const inspect=buttons().find(node=>node.props.className==='primary');await act(()=>inspect.props.onClick());
  assert.deepEqual(inspected,[['protocol-A']],'Inspect remains the review path');assert.deepEqual(merges,[]);
  await act(()=>hold().props.onPointerDown(event));await tick(999);await act(()=>hold().props.onPointerUp());await tick(1000);assert.deepEqual(merges,[],'early release cancels');
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await tick(1000);await act(()=>hold().props.onPointerUp());
  assert.deepEqual(merges,[['protocol-A',{kind:'merge_source',candidate_revision_uuid:'candidate',source_sha256:'source',origin:'protocol-overview'}]],'one hold submits one exact source merge');
  outcome=()=>{throw Error('Merge may have completed. Recover this same receipt before trying another merge.');};
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await act(()=>hold().props.onPointerUp());
  assert.equal(merges.length,2);assert.match(text(),/Recover this same receipt/,'failure stays visible on the retained card');
  for(const change of [{status:'stale'},{source_sha256:undefined},{diff_counts:{added:0}}]){
   props={...props,suggestion:{...card,...change}};await render();assert.equal(hold(),undefined,JSON.stringify(change));
  }
  props={...props,suggestion:{...card,status:'stale'}};await render();assert.match(text(),/Refresh the saved proposal/);
 }finally{t.mock.timers.reset();}
});

// The same Overview card, driven by the cumulative queue: one card summing every
// pending import, a hold that merges all of it, and retirement after a receipt.
test('Overview card follows the cumulative queue, holds to merge all, and disappears after a verified receipt',async t=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Suggestion}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx');
 const queue={contract_version:1,queue_revision:'q1',pending_epoch_count:755,pending_cell_count:4,eligible_pending_epoch_count:755,eligible_pending_cell_count:4,
  capabilities:{cumulative_pending_browse:true,additive_accept:true,frozen_browse:true,drafts:true,incoming_export:true},
  candidates:[{candidate_revision_uuid:'a',source_filename:'2026-10-12_F.h5',source_sha256:'sa',eligible_pending_epoch_count:500},{candidate_revision_uuid:'b',source_filename:'2026-10-13_A.h5',source_sha256:'sb',eligible_pending_epoch_count:255}]};
 const main={counts:{epochs:36},cells:[{cell_uuid:'x'},{cell_uuid:'y'}]};
 let renderer,merges=[],inspected=[],outcome=()=>true;
 let props={projectId:'undo-banner-project',pendingProtocol:'protocol-A',main,queue,onMerge:async(...args)=>{merges.push(args);return outcome();},onProtocol:(...args)=>inspected.push(args)};
 const render=async()=>act(()=>{const node=React.createElement(Suggestion,props);if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);});
 const buttons=()=>renderer.root.findAllByType('button'),hold=()=>buttons().find(node=>node.props['aria-label']==='Hold to merge all');
 const text=()=>JSON.stringify(renderer.toJSON());
 const event={button:0,preventDefault(){}},tick=ms=>act(async()=>{t.mock.timers.tick(ms);await Promise.resolve();});
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();});
 await render();t.mock.timers.enable({apis:['setTimeout']});
 try{
  assert.match(text(),/New data matches your saved query/,'the existing card is reused');
  assert.match(text(),/2026-10-12_F\.h5, 2026-10-13_A\.h5/,'subtitle lists every pending recording');
  assert.match(text(),/755/);assert.match(text(),/791/,'Proposed epochs are Main plus mergeable pending');
  await act(()=>buttons().find(node=>node.props.className==='primary').props.onClick());assert.deepEqual(inspected,[['protocol-A']]);
  await act(()=>hold().props.onPointerDown(event));await tick(999);await act(()=>hold().props.onPointerUp());await tick(1000);assert.deepEqual(merges,[],'early release cancels');
  outcome=()=>{throw Error('Merge may have completed. Recover this same receipt before trying another merge.');};
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await act(()=>hold().props.onPointerUp());
  assert.deepEqual(merges,[['protocol-A',{kind:'merge_all',queue_revision:'q1',origin:'protocol-overview'}]]);
  assert.match(text(),/Recover this same receipt/,'an uncertain outcome keeps the card');
  outcome=()=>true;
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await act(async()=>{});
  assert.equal(merges.length,2);assert.equal(renderer.toJSON(),null,'a verified receipt retires the card for the queue revision it showed');
  props={...props,queue:{...queue,queue_revision:'q2',eligible_pending_epoch_count:0,eligible_pending_cell_count:0,pending_epoch_count:0,pending_cell_count:0,candidates:[]}};await render();
  assert.equal(renderer.toJSON(),null,'nothing pending: no card');
  const {createMergeUndo}=await server.ssrLoadModule('/src/incoming-workbench/mergeUndo.js');
  const undo=createMergeUndo({request:async()=>({binding:{revision_uuid:'restored',version:4},restored_revision_uuid:'restored',removed_epoch_count:755})});
  undo.show({protocol_uuid:'protocol-A',operation_uuid:'banner-merge',event_uuid:'merged',binding:{revision_uuid:'main',version:3},accepted_epoch_count:755},{projectId:'undo-banner-project'});
  await act(async()=>undo.undo());
  assert.equal(renderer.toJSON(),null,'undo alone never invents pending membership from an empty queue');
  props={...props,queue};await render();
  assert.ok(hold(),'the restored original queue revision shows the banner after Undo');
  assert.match(text(),/755/);assert.match(text(),/2026-10-12_F\.h5/);
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await act(async()=>{});
  assert.equal(renderer.toJSON(),null,'merging the restored queue retires it again');
  undo.show({protocol_uuid:'other-protocol',operation_uuid:'other-banner-merge',event_uuid:'other',binding:{revision_uuid:'other-main',version:3},accepted_epoch_count:1},{projectId:'undo-banner-project'});
  await act(async()=>undo.undo());
  assert.equal(renderer.toJSON(),null,'another protocol undo cannot resurrect this banner');
  props={...props,queue:{...queue,queue_revision:'q3'}};await render();assert.ok(hold(),'new pending data shows the card again');
  props={...props,queue:{...queue,queue_revision:'q4',eligible_pending_epoch_count:0,main_blocked_reason:'Main contains epochs whose recorded metadata changed; save the query again to update main.'}};await render();
  assert.equal(hold(),undefined);assert.match(text(),/save the query again/,'a blocked Main shows one quiet sentence instead of the card');
 }finally{t.mock.timers.reset();}
});
