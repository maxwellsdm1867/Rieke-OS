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
