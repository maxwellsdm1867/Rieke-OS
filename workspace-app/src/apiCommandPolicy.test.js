import test from 'node:test';
import assert from 'node:assert/strict';
import {api} from './api.js';
import {beginProjectUnmount,installDesktopLifecycle,registerDraftSaver} from './desktopLifecycle.js';
import {mutationUndo} from "./undo/mutationUndo.js";

// Real api() and lifecycle owners, with no network or desktop/native operations.
const deferred=()=>{let resolve;const promise=new Promise(yes=>{resolve=yes;});return {promise,resolve};};
const response=(data={},status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const assertPendingUnmount=()=>assert.throws(()=>{
  // Clean up admission even if a regression incorrectly allows it.
  const release=beginProjectUnmount();release();
},/pending changes/);
function harness(t){
  const previous=globalThis.fetch,network=deferred(),calls=[];
  globalThis.fetch=(...args)=>{calls.push(args);return network.promise;};
  let prepare,ack;
  const uninstall=installDesktopLifecycle({
    onPrepareClose:handler=>{prepare=handler;return()=>{};},
    acknowledgeDrafts:async(id,value)=>{ack={id,...value};},
  });
  t.after(()=>{network.resolve(response());uninstall();globalThis.fetch=previous;mutationUndo.project(null);});
  return {network,calls,close:()=>prepare({requestId:'policy-close'}),ack:()=>ack};
}

// These POST reads deliberately retain client write-barrier participation while
// the server exempts them from synchronous backup. Never share the classifiers.
const trackedRequests=[
  ['/tree-pages','POST'],
  ['/annotations/read','POST'],
  ['/explore/summaries/job/cancel','POST'],
  ['/annotations/group-preview-release','POST'],
  ['/annotations','POST'],
  ['/annotations/group','POST'],
  ['/projects/unmount','POST'],
  ['/project/close','POST'],
  ['/project-preferences','PUT'],
  ['/protocols/p/workbench/candidates/r/draft','PATCH'],
  ['/future-command','DELETE'],
  ['/tree-pages','post'],
];
for(const [path,method] of trackedRequests){
  test(`api ${method} ${path} blocks unmount and delays close until settled`,async t=>{
    const h=harness(t);
    const operation=api(path,{method,body:{}});
    assert.equal(h.calls.length,1);
    assert.equal(h.calls[0][0],`/api${path}`);
    assertPendingUnmount();
    let snapshots=0;
    const stop=registerDraftSaver(async()=>{snapshots++;});t.after(stop);
    const closing=h.close();
    await Promise.resolve();
    assert.equal(h.ack(),undefined);assert.equal(snapshots,0);
    h.network.resolve(response({receipt:'retained'}));
    assert.deepEqual(await operation,{receipt:'retained'});
    await closing;
    assert.equal(snapshots,1);
    assert.deepEqual(h.ack(),{id:'policy-close',ok:true});
  });
}

test('omitted method GET is not tracked by the write barrier',async t=>{
  const h=harness(t);
  const operation=api('/annotations/read');
  const release=beginProjectUnmount();release();
  await h.close();
  assert.deepEqual(h.ack(),{id:'policy-close',ok:true});
  h.network.resolve(response({read:true}));
  assert.deepEqual(await operation,{read:true});
});

test('annotation stays pending through JSON decoding and undo receipt completion, not backup completion',async t=>{
  const h=harness(t),decoded=deferred(),entered=deferred();
  mutationUndo.project('policy-project');
  const operation=api('/annotations',{method:'POST',body:{}});
  assert.equal(h.calls[0][1].headers['X-Rieke-Undo-Receipt'],'1');
  h.network.resolve({ok:true,status:200,json:()=>{entered.resolve();return decoded.promise;}});
  await entered.promise;
  assertPendingUnmount();
  assert.equal(mutationUndo.view().pending,1);
  const closing=h.close();
  await Promise.resolve();assert.equal(h.ack(),undefined);
  const payload={persistence:{database:'committed',backup:{status:'pending'}},undo:{
    kind:'annotations',target_kind:'epoch',profile_uuid:'author',
    targets:[['epoch',1,0,0]],patterns:[{tags_add:['verified']}],
  }};
  decoded.resolve(payload);
  assert.deepEqual(await operation,payload);
  await closing;
  assert.equal(mutationUndo.view().pending,0);
  assert.equal(mutationUndo.view().count,1);
  assert.deepEqual(h.ack(),{id:'policy-close',ok:true});
});

test('actual 507 error envelope reaches close as committed backup failure without retry',async t=>{
  const h=harness(t);
  const operation=api('/annotations/group',{method:'POST',body:{operation_uuid:'inverse-operation'}});
  let snapshots=0;const stop=registerDraftSaver(async()=>{snapshots++;});t.after(stop);
  const closing=h.close();
  const payload={error:'Backup unavailable',saved:true,code:'recovery_unconfirmed',
    operation_uuid:'inverse-operation',persistence:{database:'committed',backup:{status:'degraded'}}};
  const rejected=assert.rejects(operation,error=>{
    assert.equal(error.status,507);assert.equal(error.saved,true);
    assert.deepEqual(error.persistence,payload.persistence);assert.deepEqual(error.data,payload);
    return true;
  });
  h.network.resolve(response(payload,507));
  await rejected;await closing;
  assert.equal(h.calls.length,1);assert.equal(snapshots,1);
  assert.equal(h.ack().ok,false);assert.match(h.ack().reason,/committed to the database/);
  assert.match(h.ack().reason,/backup coverage is incomplete/);
});

test('closing blocks even read POST before fetch but still permits GET',async t=>{
  const h=harness(t);await h.close();
  await assert.rejects(api('/tree-pages',{method:'POST',body:{}}),/closing/);
  await assert.rejects(api('/project/close',{method:'POST',body:{}}),/closing/);
  assert.equal(h.calls.length,0);
  const read=api('/backup/status');h.network.resolve(response());await read;
  assert.equal(h.calls.length,1);
});

test('unmount fence admits only the exact unmount write path and tracks it',async t=>{
  const h=harness(t),release=beginProjectUnmount();t.after(release);
  for(const path of ['/tree-pages','/projects/unmount/extra','/projects/unmount?retry=1']){
    await assert.rejects(api(path,{method:'POST',body:{}}),/unmounting/);
  }
  assert.equal(h.calls.length,0);
  const operation=api('/projects/unmount',{method:'POST',body:{}});
  assert.equal(h.calls.length,1);
  assert.throws(()=>beginProjectUnmount(true),/pending changes/);
  h.network.resolve(response());await operation;
  release();const finish=beginProjectUnmount();finish();
});
