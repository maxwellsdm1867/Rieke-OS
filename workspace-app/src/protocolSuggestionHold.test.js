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
