import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {act,create} from 'react-test-renderer';
import {useDesktopDraft} from './useDesktopDraft.js';
import {flushDesktopDrafts} from '../desktopLifecycle.js';

const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const saved=(projectId,value)=>({format:'rieke-renderer-draft',version:1,projectId,value});
const turn=()=>new Promise(resolve=>setImmediate(resolve));

// Only environment dependencies are controlled: the hook, factory and shared
// flush registrar are real. Every test restores its bridge and timer globals.
async function fixture(bridge){
 const previousWindow=Object.getOwnPropertyDescriptor(globalThis,'window');
 const previousSet=globalThis.setInterval,previousClear=globalThis.clearInterval;
 const timers=new Map(),renders=[];let nextTimer=0,root,visible;
 Object.defineProperty(globalThis,'window',{configurable:true,writable:true,value:{riekeDesktop:bridge}});
 globalThis.setInterval=(callback,delay)=>{const id=++nextTimer;timers.set(id,{callback,delay});return id;};
 globalThis.clearInterval=id=>timers.delete(id);
 function Probe(props){
  visible=useDesktopDraft(props);
  renders.push({requestedProject:props.projectId,...visible});
  return React.createElement('output',null,visible.phase);
 }
 const defaults={projectId:'a',snapshot:()=>({route:'overview'}),restore:()=>{},busy:false,navigationIdentity:()=>0};
 return {
  renders,timers,get state(){return visible;},
  async render(props={}){await act(async()=>{const element=React.createElement(Probe,{...defaults,...props});if(root)root.update(element);else root=create(element);});},
  async tick(){await act(async()=>{for(const {callback} of [...timers.values()])callback();await turn();});},
  async unmount(){if(root){await act(async()=>root.unmount());root=null;}},
  async close(){try{if(root)await act(async()=>root.unmount());}finally{root=null;globalThis.setInterval=previousSet;globalThis.clearInterval=previousClear;if(previousWindow)Object.defineProperty(globalThis,'window',previousWindow);else delete globalThis.window;}},
 };
}

test('draft hook project switch closes pending load and registers only the current saver',async()=>{
 const a=deferred(),b=deferred(),loads=[],writes=[],restores=[];
 const h=await fixture({loadDraft:project=>{loads.push(project);return project==='a'?a.promise:b.promise;},saveDraft:async value=>writes.push(value)});
 try{
  await h.render({restore:value=>restores.push(value)});
  assert.equal(h.state.phase,'loading');assert.deepEqual(loads,['a']);
  assert.deepEqual([...h.timers.values()].map(timer=>timer.delay),[3000]);
  await h.render({projectId:'b',snapshot:()=>({route:'files'}),restore:value=>restores.push(value)});
  assert.deepEqual(loads,['a','b']);assert.equal(h.timers.size,1);
  await act(async()=>{a.resolve(saved('a',{route:'old project'}));b.resolve(null);await turn();});
  assert.deepEqual(restores,[]);assert.equal(h.state.projectId,'b');assert.equal(h.state.phase,'ready');
  await flushDesktopDrafts();
  assert.deepEqual(writes,[{projectId:'b',value:saved('b',{route:'files'})}]);
  await h.unmount();assert.equal(h.timers.size,0);
  await flushDesktopDrafts();assert.equal(writes.length,1);
 }finally{a.resolve(null);b.resolve(null);await h.close();}
});

test('draft hook unmount fences a pending restore and removes autosave and flush registration',async()=>{
 const load=deferred(),restores=[],writes=[];
 const h=await fixture({loadDraft:()=>load.promise,saveDraft:async value=>writes.push(value)});
 try{
  await h.render({restore:value=>restores.push(value)});
  await h.unmount();assert.equal(h.timers.size,0);
  await act(async()=>{load.resolve(saved('a',{route:'late'}));await turn();});
  await flushDesktopDrafts();
  assert.deepEqual(restores,[]);assert.deepEqual(writes,[]);
 }finally{load.resolve(null);await h.close();}
});

test('draft hook uses latest restore snapshot and busy callbacks without reloading the project',async()=>{
 const load=deferred(),loads=[],restores=[],writes=[];
 const h=await fixture({loadDraft:project=>{loads.push(project);return load.promise;},saveDraft:async value=>writes.push(value)});
 const latest={restore:value=>restores.push(['latest',value]),snapshot:()=>({route:'latest snapshot'})};
 try{
  await h.render({restore:value=>restores.push(['old',value]),snapshot:()=>({route:'old snapshot'})});
  await h.render(latest);
  await act(async()=>{load.resolve(saved('a',{route:'stored'}));await turn();});
  assert.deepEqual(restores,[['latest',{route:'stored'}]]);assert.deepEqual(loads,['a']);
  await h.render({...latest,busy:true});await h.tick();assert.deepEqual(writes,[]);
  await assert.rejects(flushDesktopDrafts(),/latest view could not be saved/);
  await h.render(latest);await h.tick();
  assert.deepEqual(writes,[{projectId:'a',value:saved('a',{route:'latest snapshot'})}]);
  await h.render({...latest,snapshot:()=>({route:'newest snapshot'})});await flushDesktopDrafts();
  assert.deepEqual(writes.at(-1),{projectId:'a',value:saved('a',{route:'newest snapshot'})});
  assert.deepEqual(loads,['a']);assert.equal(h.timers.size,1);
 }finally{load.resolve(null);await h.close();}
});

test('draft hook latest navigation callback supersedes a pending saved view',async()=>{
 const load=deferred(),restores=[],writes=[];
 const h=await fixture({loadDraft:()=>load.promise,saveDraft:async value=>writes.push(value)});
 try{
  await h.render({navigationIdentity:()=>0,restore:value=>restores.push(value)});
  await h.render({navigationIdentity:()=>2,restore:value=>restores.push(value),snapshot:()=>({route:'user intent'})});
  await act(async()=>{load.resolve(saved('a',{route:'obsolete'}));await turn();});
  await flushDesktopDrafts();
  assert.deepEqual(restores,[]);assert.deepEqual(writes,[{projectId:'a',value:saved('a',{route:'user intent'})}]);
 }finally{load.resolve(null);await h.close();}
});

test('draft hook hides prior recovery immediately under another project identity',async()=>{
 const pending=deferred();let loads=0;
 const h=await fixture({loadDraft:project=>{loads++;return project==='a'?Promise.resolve({format:'rieke-draft-recovery'}):pending.promise;},saveDraft:async()=>{}});
 try{
  await h.render();assert.equal(h.state.phase,'recovery');assert.equal(h.state.resetAllowed,true);
  const before=h.renders.length;
  await h.render({projectId:'b'});
  const next=h.renders.slice(before);
  assert.equal(next[0].requestedProject,'b');assert.equal(next[0].phase,'inactive');
  assert.ok(next.every(state=>state.phase!=='recovery'&&state.projectId!=='a'));
  assert.equal(h.state.phase,'loading');assert.equal(loads,2);
  await act(async()=>{pending.resolve(null);await turn();});
  assert.equal(h.state.phase,'ready');assert.equal(h.state.projectId,'b');
  await h.render({projectId:null});assert.equal(h.state.phase,'inactive');assert.equal(h.timers.size,0);
  await flushDesktopDrafts();assert.equal(loads,2);
 }finally{pending.resolve(null);await h.close();}
});
