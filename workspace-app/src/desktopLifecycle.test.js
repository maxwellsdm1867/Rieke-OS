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
  installDesktopLifecycle({onPrepareClose:fn=>{handler=fn;return()=>{};},acknowledgeDrafts:async(id,result)=>{ack=result;}});
  await handler({requestId:'failed'});assert.deepEqual(ack,{ok:false});stop();
});
