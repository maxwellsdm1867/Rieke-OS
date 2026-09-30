import test from 'node:test';
import assert from 'node:assert/strict';
import {createDesktopDraftSession} from './desktopDraftSession.js';
test('corrupt view requires explicit choice and never overwrites preserved bytes',async()=>{
  let state,stored=0,resets=0;
  const session=createDesktopDraftSession({projectId:'launcher',bridge:{loadDraft:async()=>({format:'rieke-draft-recovery'}),saveDraft:async()=>stored++,resetDraft:async()=>resets++},snapshot:()=>({route:{page:'overview'}}),restore:()=>assert.fail('Corrupt view must not restore'),isBusy:()=>false,onState:next=>state=next});
  await assert.rejects(session.flush(),/explicit choice/);assert.equal(state.phase,'recovery');assert.equal(stored,0);
  session.preserveForQuit();await session.flush();assert.equal(stored,0);assert.equal(resets,0);
  await session.fresh();await session.flush();assert.equal(stored,1);assert.equal(resets,1);assert.equal(state.phase,'ready');session.close();
});
test('failed load is observed immediately and retry retains a valid saved view',async()=>{
  let fail=true,state,restored=false;
  const session=createDesktopDraftSession({projectId:'launcher',bridge:{loadDraft:async()=>{if(fail)throw new Error('Read failed');return {format:'rieke-renderer-draft',version:1,projectId:'launcher',value:{route:{page:'files'}}};},saveDraft:async()=>{}},snapshot:()=>({}),restore:()=>{restored=true;},isBusy:()=>false,onState:next=>state=next});
  await assert.rejects(session.flush());assert.equal(state.phase,'recovery');assert.equal(state.resetAllowed,false);
  await assert.rejects(session.fresh());fail=false;await session.retry();await session.flush();assert.equal(restored,true);session.close();
});


test('navigation flush waits behind an in-flight autosave and commits the current view last',async()=>{
  let current={page:'overview'},release;
  const gate=new Promise(resolve=>{release=resolve;});
  const saves=[];
  const session=createDesktopDraftSession({projectId:'launcher',snapshot:()=>current,restore:()=>{},isBusy:()=>false,
    bridge:{loadDraft:async()=>null,saveDraft:async payload=>{saves.push(payload.value.value.page);if(saves.length===1)await gate;}}});
  const periodic=session.flush();
  await new Promise(resolve=>setImmediate(resolve));
  current={page:'files'};
  const navigation=session.flush();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(saves,['overview']);
  release();await Promise.all([periodic,navigation]);
  assert.deepEqual(saves,['overview','files']);
  session.close();
});
