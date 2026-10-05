'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {recoverVerificationFailure}=require('../verification-recovery.cjs');
const {QuitCoordinator}=require('../close/quit-coordinator.cjs');
test('ordinary Quit retries only absent or unconfirmed verification cleanup',async()=>{
  const {cleanupAfterVerificationRecovery}=require('../verification-recovery.cjs');
  let retries=0;
  for(const result of [undefined,{services:{ready:false}},{services:{ready:'true'}}])
    assert.equal(await cleanupAfterVerificationRecovery(result,()=>{retries++;return 'retried';}),'retried');
  assert.equal(retries,3);
});
test('failure blocks new work immediately, preserves accepted work, and shows recovery only after cleanup',async()=>{
  const events=[];let acceptWrite;
  const acceptedWrite=new Promise(resolve=>{acceptWrite=resolve;});
  const pending=recoverVerificationFailure({
    blockNewWork:()=>events.push('blocked'),pause:async()=>events.push('paused'),
    saveDrafts:async()=>{events.push('drafts');return {ready:true};},
    closeServices:async drafts=>{assert.equal(drafts.ready,true);await acceptedWrite;events.push('closed');return{ready:true};},
    showRecovery:result=>{assert.equal(result.services.ready,true);events.push('recovery');}
  });
  assert.equal(events[0],'blocked');assert.equal(events.includes('recovery'),false);
  await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(events,['blocked','paused','drafts']);
  acceptWrite();await pending;assert.deepEqual(events,['blocked','paused','drafts','closed','recovery']);
});
test('failed pause/draft/cleanup retains uncertainty and still presents recovery',async()=>{
  let shown;
  const result=await recoverVerificationFailure({blockNewWork:()=>{},pause:async()=>{throw Error('unbound child');},saveDrafts:async()=>({ready:false,reason:'view unavailable'}),closeServices:async()=>{throw Error('cleanup pending');},showRecovery:value=>{shown=value;}});
  assert.equal(shown,result);assert.equal(result.services.ready,false);assert.equal(result.drafts.ready,false);assert.equal(result.pauseError,'unbound child');
});
test('Quit aborts audit and waits for audit closure before service cleanup and exit',async()=>{
  const events=[],controller=new AbortController();let closeAudit;
  const auditClosed=new Promise(resolve=>{closeAudit=resolve;});
  const quit=new QuitCoordinator({prepareDrafts:async()=>({ready:true}),cleanup:async()=>{controller.abort();events.push('abort');await auditClosed;events.push('services');return{ready:true};},exit:()=>events.push('exit')});
  const pending=quit.quit();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(controller.signal.aborted,true);assert.deepEqual(events,['abort']);
  closeAudit();const result=await pending;assert.equal(result.clean,true);assert.deepEqual(events,['abort','services','exit']);
});
