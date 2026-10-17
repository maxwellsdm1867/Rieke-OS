import test from 'node:test';
import assert from 'node:assert/strict';
import {registerDraftSaver,trackWrite,flushDesktopDrafts,installDesktopLifecycle} from './desktopLifecycle.js';
test('closure acknowledgment follows pending writes and durable draft saves',async()=>{
  let handler,release,saved=false,ack=null;
  const pending=trackWrite(new Promise(resolve=>release=resolve));
  const stop=registerDraftSaver(async()=>{saved=true;});
  const uninstall=installDesktopLifecycle({onPrepareClose:fn=>{handler=fn;return()=>{};},acknowledgeDrafts:async(id,result)=>{ack={id,...result};}});
  const closing=handler({requestId:'request'});
  await Promise.resolve();assert.equal(saved,false);assert.equal(ack,null);
  release();await pending;await closing;
  assert.equal(saved,true);assert.deepEqual(ack,{id:'request',ok:true});stop();uninstall();
});
test('a failed draft never acknowledges safe closure',async()=>{
  let handler,ack;
  const stop=registerDraftSaver(async()=>{throw new Error('disk full');});
  const uninstall=installDesktopLifecycle({onPrepareClose:fn=>{handler=fn;return()=>{};},acknowledgeDrafts:async(id,result)=>{ack=result;}});
  await handler({requestId:'failed'});assert.equal(ack.ok,false);assert.match(ack.reason,/last saved view/i);stop();uninstall();
});

test('failed accepted writes do not prevent a view snapshot and committed backup failures are reported accurately',async()=>{
 let handler,release,ack,snapshots=0;
 const uninstall=installDesktopLifecycle({onPrepareClose:fn=>{handler=fn;return()=>{};},acknowledgeDrafts:async(_id,result)=>{ack=result;}});
 const stop=registerDraftSaver(async()=>{snapshots++;});
 const accepted=trackWrite(new Promise((_resolve,reject)=>release=reject));
 const closing=handler({requestId:'backup-failure'});
 const failure=Object.assign(new Error('backup unavailable'),{saved:true});release(failure);
 await accepted.catch(()=>{});await closing;
 assert.equal(snapshots,1);assert.equal(ack.ok,false);assert.match(ack.reason,/committed to the database/);assert.match(ack.reason,/backup coverage/);
 stop();uninstall();
});
test('shutdown pauses new mutation requests before network admission and a late missing acknowledgement is tolerated',async()=>{
 const {api}=await import('./api.js');const old=globalThis.fetch;let requests=0,handler;
 globalThis.fetch=async()=>{requests++;return{ok:true,json:async()=>({})};};
 const uninstall=installDesktopLifecycle({onPrepareClose:fn=>{handler=fn;return()=>{};},acknowledgeDrafts:async()=>{throw new Error('quit deadline elapsed');}});
 try{
  await handler({requestId:'late'});
  await assert.rejects(api('/edit',{method:'POST',body:{}}),/closing/);
  assert.equal(requests,0);
 }finally{uninstall();globalThis.fetch=old;}
});

test('project checkpoint runs hidden dirty guards, permits close request, and resumes on cancellation',async()=>{
 const {assertDesktopWritable,registerUnmountGuard}=await import('./desktopLifecycle.js');
 let prepare,resume,ack;
 const uninstall=installDesktopLifecycle({onPrepareClose:fn=>{prepare=fn;},onProjectResume:fn=>{resume=fn;},acknowledgeDrafts:async(_id,value)=>{ack=value;}});
 const stop=registerUnmountGuard(()=> 'Unfinished hidden draft');
 try{
  await prepare({requestId:'blocked',purpose:'project-checkpoint'});assert.equal(ack.ok,false);assert.match(ack.reason,/hidden draft/);assert.doesNotThrow(()=>assertDesktopWritable('/edit'));
  stop();await prepare({requestId:'saved',purpose:'project-checkpoint'});assert.equal(ack.ok,true);
  assert.throws(()=>assertDesktopWritable('/edit'),/unmounting/);assert.doesNotThrow(()=>assertDesktopWritable('/projects/unmount'));
  resume();assert.doesNotThrow(()=>assertDesktopWritable('/edit'));
 }finally{stop();uninstall();}
});

test('renderer recovery pauses new mutations without destroying registered draft savers',async()=>{
 const {assertDesktopWritable}=await import('./desktopLifecycle.js');let status,saves=0;
 const stop=registerDraftSaver(async()=>saves++),uninstall=installDesktopLifecycle({onStatus:fn=>{status=fn;},onPrepareClose:()=>{}});
 try{
  status({state:'Recovery'});assert.throws(()=>assertDesktopWritable('/edit'),/closing/);await flushDesktopDrafts();assert.equal(saves,1);
  status({state:'IntegrityRecovery'});assert.throws(()=>assertDesktopWritable('/edit'),/closing/);
  status({state:'Running'});assert.doesNotThrow(()=>assertDesktopWritable('/edit'));
 }finally{stop();uninstall();}
});

test('submission flush: a views-only failure does not reject; an unconfirmed accepted write does; close stays strict',async()=>{
 const {flushBeforeSubmission}=await import('./desktopLifecycle.js');
 const stop=registerDraftSaver(async()=>{throw new Error('disk full');});
 try{
  const result=await flushBeforeSubmission();
  assert.equal(result.viewSaved,false);assert.match(result.notice,/view could not be saved/);
  await assert.rejects(flushDesktopDrafts(),/latest view could not be saved/,'close/unmount keep the strict contract');
  let reject;const pending=trackWrite(new Promise((_resolve,fail)=>{reject=fail;}));
  const flushing=flushBeforeSubmission();reject(new Error('lost'));await pending.catch(()=>{});
  await assert.rejects(flushing,/not confirmed/);
 }finally{stop();}
 const ok=registerDraftSaver(async()=>{});try{assert.deepEqual(await flushBeforeSubmission(),{viewSaved:true,notice:''});}finally{ok();}
});
