import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {createOverviewCache} from './overviewCache.js';
import {useOverviewResource} from './useOverviewResource.js';
import useWorkbenchQueue from '../incoming-workbench/useWorkbenchQueue.js';

for(const kind of ['overview','workbench'])test(`${kind}: real StrictMode prepares once; Activity return reuses ready state`,async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 const previous=new Map(['window','document','navigator','fetch'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 Object.defineProperty(globalThis,'window',{configurable:true,writable:true,value:dom.window});
 Object.defineProperty(globalThis,'document',{configurable:true,writable:true,value:dom.window.document});
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:dom.window.navigator});
 const cache=createOverviewCache();let current,ready=false,release,posts=0,reads=0,setups=0,cleanups=0;
 globalThis.fetch=async path=>{
  if(path.endsWith('/prepare')){posts++;await new Promise(resolve=>release=resolve);ready=true;return new Response('{}');}
  reads++;
  if(!ready)return new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:kind}}),{status:202});
  return new Response(JSON.stringify(kind==='overview'?{counts:{epochs:12}}:{contract_version:1,queue_revision:'fresh',candidates:[],pending_epoch_count:0,pending_cell_count:0,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}}));
 };
 function Overview(){current=useOverviewResource('/overview',0,{cache,scope:'project'});return null;}
 function Workbench(){current=useWorkbenchQueue('p',0,undefined,'project');return null;}
 function Proof(){useEffect(()=>{setups++;return()=>{cleanups++;};},[]);return React.createElement(kind==='overview'?Overview:Workbench);}
 const root=createRoot(dom.window.document.getElementById('root'));
 const render=mode=>React.createElement(React.StrictMode,null,React.createElement(React.Activity,{mode},React.createElement(Proof)));
 try{
  await act(()=>root.render(render('visible')));assert.equal(setups,2);assert.equal(cleanups,1);assert.equal(posts,1);
  await act(()=>release());assert.ok(current.data);assert.equal(current.preparing,false);
  const count=reads;
  await act(()=>root.render(render('hidden')));await act(()=>root.render(render('visible')));
  assert.equal(posts,1);assert.equal(reads,count);assert.ok(current.data);
 }finally{
  await act(()=>root.unmount());cache.clear();dom.window.close();
  for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];
 }
});
