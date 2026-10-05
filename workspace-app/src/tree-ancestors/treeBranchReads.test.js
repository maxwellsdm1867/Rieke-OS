import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';

const turn=()=>new Promise(resolve=>setImmediate(resolve));
const hex=n=>String(n).repeat(64);
const body={protocol_uuid:'protocol',filters:{},splits:'date,cell',path:[],offset:0,limit:60,revision:hex(1)};
const witness=(project='a',path='/owned/a')=>({kind:'branches',revision:hex(1),split_order:['date','cell'],read_identity:{version:1,project_uuid:project,project_path:path,protocol_uuid:'protocol',tree_revision:hex(1),generation:{metadata:'m',typed:null,source:'s',annotation:'a',binding:'b',publication:'p'}}});
const profile={profiles:[{profile_uuid:'actor',display_name:'Fixture'}],selected_profile_uuid:'actor'};

// Actual provider/profile/cache modules; only HTTP, browser events and desktop
// status are controlled. Listener accounting observes public add/remove calls.
async function fixture(){
 const browser=new JSDOM('<div id="root"></div>',{url:'http://fixture/'});
 const previous=new Map(),requests=[],listeners=new Map(),statuses=new Set(),restores=[];
 let server,root,cache,visible,Profile,Owner,useReads;
 for(const [key,value] of Object.entries({window:browser.window,document:browser.window.document,localStorage:browser.window.localStorage})){
  previous.set(key,Object.getOwnPropertyDescriptor(globalThis,key));Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 }
 const events=['focus','online','pageshow','pagehide'];
 for(const [target,names] of [[window,events],[document,['visibilitychange']]]){
  const add=target.addEventListener,remove=target.removeEventListener;
  target.addEventListener=function(name,callback,...args){if(names.includes(name)){if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(callback);}return add.call(this,name,callback,...args);};
  target.removeEventListener=function(name,callback,...args){if(names.includes(name))listeners.get(name)?.delete(callback);return remove.call(this,name,callback,...args);};
  restores.push(()=>{target.addEventListener=add;target.removeEventListener=remove;});
 }
 window.riekeDesktop={onStatus:callback=>{statuses.add(callback);return()=>statuses.delete(callback);}};
 previous.set('fetch',Object.getOwnPropertyDescriptor(globalThis,'fetch'));
 globalThis.fetch=(url,options)=>new Promise(resolve=>{assert.equal(url,'/api/annotation-profiles');requests.push({options,done:false,reply(data,ok=true){assert.equal(this.done,false);this.done=true;resolve({ok,status:ok?200:503,json:async()=>data});}});});
 function Probe(){visible=useReads();return null;}
 async function close(){try{
  if(root){await act(async()=>root.unmount());root=null;}
  cache?.retire();for(const request of requests)if(!request.done)request.reply(profile);
  await turn();await server?.close();
 }finally{for(const restore of restores)restore();browser.window.close();for(const [key,descriptor]of previous){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}}
 try{
  server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
  ({AnnotationProfileProvider:Profile}=await server.ssrLoadModule("/src/annotations/annotationProfile.js"));
  ({TreeBranchReadOwner:Owner,useTreeBranchReads:useReads}=await server.ssrLoadModule('/src/tree-ancestors/treeBranchReads.jsx'));
  const {createTreeBranchReadCache}=await server.ssrLoadModule('/src/tree-ancestors/treeBranchReadCache.js');cache=createTreeBranchReadCache({now:()=>0});
  root=createRoot(document.getElementById('root'));
  return {requests,listeners,statuses,cache,get reads(){return visible;},
   async render({projectId='a',projectPath='/owned/a',revision=1}={}){await act(async()=>{root.render(React.createElement(Profile,{projectId},React.createElement(Owner,{projectId,projectPath,revision,cache},React.createElement(Probe))));await turn();});},
   async reply(index,data=profile,ok=true){await act(async()=>{requests[index].reply(data,ok);await turn();});},
   async event(name){await act(async()=>{(name==='visibilitychange'?document:window).dispatchEvent(new browser.window.Event(name));await turn();});},
   async status(state){await act(async()=>{for(const callback of statuses)callback({state});await turn();});},
   async unmount(){await act(async()=>root.unmount());root=null;},close};
 }catch(error){await close();throw error;}
}
const leaseFor=(h,project='a',path='/owned/a')=>{const lease=h.reads.attest(body,witness(project,path));assert.ok(lease,'fresh public witness attests');assert.equal(h.reads.current(lease),true);return lease;};
const retired=(h,lease)=>assert.throws(()=>h.reads.current(lease),{name:'AbortError'});

test('real tree provider preserves unavailable scope semantics through profile loading, failure and browse-only readiness',async()=>{
 const h=await fixture();try{
  await h.render();assert.equal(h.reads.available,false);assert.equal(h.reads.active(),true);assert.equal(h.reads.attest(body,witness()),null);
  await h.reply(0,{error:'profile offline'},false);assert.equal(h.reads.available,false);assert.equal(h.reads.active(),true);assert.equal(h.reads.attest(body,witness()),null);
  await h.render({projectId:'b',projectPath:'/owned/b'});await h.reply(1,{profiles:[]});
  assert.equal(h.reads.available,true);assert.equal(h.reads.active(),true);leaseFor(h,'b','/owned/b');
  await h.render({projectId:'b',projectPath:null});assert.equal(h.reads.available,false);assert.equal(h.reads.active(),true);assert.equal(h.reads.attest(body,witness('b','/owned/b')),null);
 }finally{await h.close();}
});

test('real tree provider browser lifecycle events revoke leases and require fresh attestation',async()=>{
 const h=await fixture();try{
  await h.render();await h.reply(0);
  for(const name of ['focus','online','pageshow','pagehide','visibilitychange']){
   const lease=leaseFor(h),identity=h.reads.identity;
   await h.event(name);retired(h,lease);assert.notEqual(h.reads.identity,identity);assert.equal(h.reads.available,true);leaseFor(h);
  }
  const lease=leaseFor(h);await h.event('visibilitychange');retired(h,lease);
 }finally{await h.close();}
});

test('real tree provider initial and changed desktop status revoke but repeated identical status preserves leases',async()=>{
 const h=await fixture();try{
  await h.render();await h.reply(0);assert.equal(h.statuses.size,1);
  const initial=leaseFor(h);await h.status('Ready');retired(h,initial);
  const same=leaseFor(h),identity=h.reads.identity;await h.status('Ready');assert.equal(h.reads.current(same),true);assert.equal(h.reads.identity,identity);
  await h.status('Closing');retired(h,same);const changed=leaseFor(h);
  await h.status('Closing');assert.equal(h.reads.current(changed),true);
 }finally{await h.close();}
});

test('real tree provider project revision and unmount retire leases and remove event and status subscriptions',async()=>{
 const h=await fixture();try{
  await h.render();await h.reply(0);const first=leaseFor(h);
  await h.render({revision:2});retired(h,first);const next=leaseFor(h);
  await h.render({projectId:'b',projectPath:'/owned/b',revision:2});retired(h,next);assert.equal(h.reads.available,false);
  await h.reply(1);const last=leaseFor(h,'b','/owned/b');
  for(const name of ['focus','online','pageshow','pagehide','visibilitychange'])assert.ok(h.listeners.get(name)?.size>=1,`${name} has active public subscriptions`);
  await h.unmount();assert.equal(h.cache.isCurrent(last),false);assert.equal(h.statuses.size,0);
  for(const name of ['focus','online','pageshow','pagehide','visibilitychange'])assert.equal(h.listeners.get(name)?.size,0);
  const generation=h.cache.stats().generation;await h.event('focus');await h.status('Ready');assert.equal(h.cache.stats().generation,generation);
 }finally{await h.close();}
});
