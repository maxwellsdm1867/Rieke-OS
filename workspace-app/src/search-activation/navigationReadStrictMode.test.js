import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';
const {JSDOM}=await import(process.env.RIEKE_TEST_DOM_MODULE||'jsdom');

test('ReactDOM StrictMode replay, owner remount and visible wake cannot resurrect retired search',async()=>{
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost/'});
 const requests=[];
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,fetch:async(url,options)=>{requests.push({url,signal:options.signal});return {ok:true,json:async()=>({results:[{kind:'cell',id:'same-uuid',label:'Synthetic cell'}],total:1})};}};
 const previous=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error'});
 let mounted=createRoot(document.getElementById('root')),setups=0,cleanups=0,snapshot;
 try{
   const {NavigationReadProvider,useSearchSnapshot}=await server.ssrLoadModule('/src/search-activation/navigationReadCache.jsx');
   const {createPageReadCache}=await server.ssrLoadModule('/src/search-activation/pageReadCache.js');const cache=createPageReadCache();
   function Probe(){snapshot=useSearchSnapshot({open:true,query:'CellA',revision:0});useEffect(()=>{setups++;return()=>{cleanups++;};},[]);return React.createElement('span',null,snapshot.data?.results[0]?.label||'Loading');}
   const element=()=>React.createElement(React.StrictMode,null,React.createElement(NavigationReadProvider,{projectId:'same-project-uuid',projectOpenIdentity:'first-open',actorId:'browse-only',cache},React.createElement(Probe)));
   const wait=async predicate=>{const until=Date.now()+1500;while(!predicate()){if(Date.now()>until)throw Error('Strict search did not settle');await act(()=>new Promise(resolve=>setTimeout(resolve,10)));}};
   await act(async()=>mounted.render(element()));assert.equal(setups,2);assert.equal(cleanups,1);
   await wait(()=>snapshot.fresh);assert.equal(requests.length,1);assert.equal(cache.stats().entries,1);
   await act(async()=>{window.dispatchEvent(new window.Event('online'));});assert.equal(snapshot.data,null);await wait(()=>snapshot.fresh);assert.equal(requests.length,2);
   await act(async()=>mounted.unmount());mounted=null;assert.equal(cache.stats().entries,0);assert.equal(cleanups,2);
   const generation=cache.stats().generation;window.dispatchEvent(new window.Event('online'));assert.equal(cache.stats().generation,generation,'disposed owner removed listeners');
   mounted=createRoot(document.getElementById('root'));await act(async()=>mounted.render(element()));await wait(()=>snapshot.fresh);assert.equal(requests.length,3,'new owner cannot reuse identical UUID from first open');
   Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));
   assert.equal(snapshot.data,null);await wait(()=>snapshot.fresh);assert.equal(requests.length,4);
 }finally{if(mounted)await act(async()=>mounted.unmount());await server.close();dom.window.close();for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}
});
