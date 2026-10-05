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


test('new navigation while loading wins over the saved view',async()=>{
  let release,route='initial',restores=0,stored;
  const session=createDesktopDraftSession({projectId:'project',navigationIdentity:()=>route,
    bridge:{loadDraft:()=>new Promise(resolve=>{release=resolve;}),saveDraft:async payload=>{stored=payload.value.value;}},
    snapshot:()=>({route}),restore:()=>restores++,isBusy:()=>false});
  await new Promise(resolve=>setImmediate(resolve));route='new-user-navigation';
  release({format:'rieke-renderer-draft',version:1,projectId:'project',value:{route:'old-saved-view'}});
  await session.flush();assert.equal(restores,0);assert.equal(stored.route,'new-user-navigation');session.close();
});
test('a superseded load cannot publish after retry or after project close',async()=>{
  const loads=[],restores=[];let state;
  const session=createDesktopDraftSession({projectId:'project',
    bridge:{loadDraft:()=>new Promise(resolve=>loads.push(resolve)),saveDraft:async()=>{}},
    snapshot:()=>({}),restore:value=>restores.push(value),isBusy:()=>false,onState:value=>{state=value;}});
  await new Promise(resolve=>setImmediate(resolve));const retried=session.retry();
  await new Promise(resolve=>setImmediate(resolve));
  loads[1]({format:'rieke-renderer-draft',version:1,projectId:'project',value:{route:'new'}});await retried;
  loads[0]({format:'rieke-draft-recovery'});await new Promise(resolve=>setImmediate(resolve));
  assert.equal(state.phase,'ready');assert.deepEqual(restores,[{route:'new'}]);
  const pending=session.retry();await new Promise(resolve=>setImmediate(resolve));session.close();
  loads[2]({format:'rieke-renderer-draft',version:1,projectId:'project',value:{route:'closed'}});await pending;
  assert.deepEqual(restores,[{route:'new'}]);
});

test('navigate away then back to the same route still supersedes a delayed restore',async()=>{
  let intent=0,release,restores=0;
  const session=createDesktopDraftSession({projectId:'project',navigationIdentity:()=>intent,
    bridge:{loadDraft:()=>new Promise(resolve=>{release=resolve;}),saveDraft:async()=>{}},snapshot:()=>({route:'same-key'}),restore:()=>restores++,isBusy:()=>false});
  await new Promise(resolve=>setImmediate(resolve));intent++;intent++;
  release({format:'rieke-renderer-draft',version:1,projectId:'project',value:{route:'same-key'}});
  await session.flush();assert.equal(restores,0);session.close();
});

test('public example saves the unchanged nested renderer envelope through an injected bridge',async()=>{
  const writes=[],view={route:{page:'files'},stores:{}};
  const bridge={loadDraft:async projectId=>{assert.equal(projectId,'example-project');return null;},
    saveDraft:async payload=>writes.push(payload)};
  const session=createDesktopDraftSession({bridge,projectId:'example-project',
    snapshot:()=>view,restore:()=>assert.fail('No saved view exists'),isBusy:()=>false});
  try{
    await session.flush();
    assert.deepEqual(writes,[{projectId:'example-project',value:{format:'rieke-renderer-draft',version:1,projectId:'example-project',value:view}}]);
  }finally{session.close();}
});
