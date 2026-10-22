import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';
for(const name of ['ColumnTree','HierarchyTree'])test(`${name} prepares only on click and cancels stale preparation`,async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://fixture/',pretendToBeVisual:true}),keys=['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const previous=Object.fromEntries(keys.map(k=>[k,globalThis[k]]));
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true,requestAnimationFrame:f=>setTimeout(f,0),cancelAnimationFrame:clearTimeout});
 const calls=[];let held;
 globalThis.fetch=async(url,options)=>{calls.push({url,options});if(url.endsWith('/prepare'))return new Promise(resolve=>held=resolve);return new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:'tree'}}),{status:202});};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:View}=await server.ssrLoadModule(`/src/tree-browser/ui/${name}.jsx`),root=createRoot(document.querySelector('main'));
 const render=protocolId=>act(async()=>root.render(React.createElement(View,{protocolId,projectId:'project',splits:'cell',browseOnly:true})));
 try{
  await render('a');assert.equal(calls.length,1);
  const button=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Show tree'));assert.ok(button);
  await act(()=>button.click());assert.equal(calls.length,2);assert.match(document.body.textContent,/Preparing view/);
  assert.deepEqual(JSON.parse(calls[1].options.body),{protocol_uuid:'a',filters:{},splits:'cell'});
  await render('b');assert.equal(calls[1].options.signal.aborted,true);assert.equal(calls.length,3);
  await act(()=>held(new Response(JSON.stringify({status:'ready'}))));assert.equal(calls.length,3);
  await act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Show tree')).click());
  await act(()=>held(new Response(JSON.stringify({status:'ready'}))));assert.equal(calls.length,5);
  assert.match(document.body.textContent,/Show tree/);
 }finally{await act(()=>root.unmount());await server.close();dom.window.close();for(const[k,v]of Object.entries(previous)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
});

async function preparationHarness(name){
 const dom=new JSDOM('<main></main>',{url:'http://fixture/',pretendToBeVisual:true}),keys=['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const previous=Object.fromEntries(keys.map(k=>[k,globalThis[k]]));
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true,requestAnimationFrame:f=>setTimeout(f,0),cancelAnimationFrame:clearTimeout});
 const calls=[];let ready=false,failPrepare=false,holdRead=null;
 const pending=()=>new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:'tree'}}),{status:202});
 globalThis.fetch=async(url,options)=>{
  calls.push({url,options});
  if(url.endsWith('/prepare')){if(failPrepare)return pending();ready=true;return new Response(JSON.stringify({status:'ready'}));}
  if(holdRead)return new Promise(resolve=>holdRead(resolve));
  if(!ready)return pending();
  const body=JSON.parse(options.body);
  return new Response(JSON.stringify({revision:'a'.repeat(64),kind:'branches',path:[],depth:0,offset:0,limit:body.limit,total:0,total_epochs:9,selection:{count:9},split_order:body.splits.split(','),levels:[],ancestors:[],branches:[],epochs:[],has_more:false}));
 };
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:View}=await server.ssrLoadModule(`/src/tree-browser/ui/${name}.jsx`),root=createRoot(document.querySelector('main'));
 return {calls,pending,set ready(value){ready=value;},set failPrepare(value){failPrepare=value;},set holdRead(value){holdRead=value;},
  render:props=>act(async()=>root.render(React.createElement(View,{protocolId:'p',projectId:'project',splits:'cell',browseOnly:true,...props}))),
  key:()=>act(()=>window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'t',metaKey:true,cancelable:true}))),
  async close(){await act(()=>root.unmount());await server.close();dom.window.close();for(const[k,v]of Object.entries(previous)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
 };
}

test('an edited layout prepares once; a failed preparation remains an explicit retry',async()=>{
 const h=await preparationHarness('ColumnTree');let intent=true;
 const takeLayoutPreparation=scope=>{assert.equal(scope.splits,'cell');const take=intent;intent=false;return take;};
 try{
  await h.render({takeLayoutPreparation});
  assert.deepEqual(h.calls.map(call=>call.url),['/api/tree-pages','/api/tree-pages/prepare','/api/tree-pages']);
  assert.equal(document.querySelector('[role="alert"]'),null);
  h.ready=false;h.failPrepare=true;intent=true;h.calls.length=0;
  await h.render({takeLayoutPreparation,revision:1});
  assert.equal(h.calls.length,2,'failed auto preparation never loops');
  assert.match(document.body.textContent,/Show tree/);
  h.failPrepare=false;await h.key();
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,2);
  assert.equal(h.calls.length,4);
 }finally{await h.close();}
});

test('a superseded layout read cannot consume an edit or start preparation',async()=>{
 const h=await preparationHarness('ColumnTree');let release,claims=0;
 try{
  h.holdRead=resolve=>{release=resolve;};
  await h.render({takeLayoutPreparation:()=>{claims++;return true;}});
  h.holdRead=null;h.ready=true;
  await h.render({splits:'date'});
  await act(()=>release(h.pending()));
  assert.equal(claims,0);assert.equal(h.calls.length,2);
 }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} Command-T retries once and ignores hidden or paused trees`,async()=>{
 const h=await preparationHarness(name);
 try{
  h.ready=true;await h.render({});h.ready=false;h.calls.length=0;
  await h.key();
  assert.deepEqual(h.calls.map(call=>call.url),['/api/tree-pages','/api/tree-pages/prepare','/api/tree-pages']);
  document.querySelector('main').setAttribute('inert','');h.calls.length=0;await h.key();assert.equal(h.calls.length,0);
  document.querySelector('main').removeAttribute('inert');
  await h.render({readPaused:true});h.calls.length=0;await h.key();assert.equal(h.calls.length,0);
 }finally{await h.close();}
});


test('an inactive hierarchy resumes its read when activated',async()=>{
 const h=await preparationHarness('HierarchyTree');
 try{
  h.ready=true;await h.render({active:false});assert.equal(h.calls.length,0);
  await h.render({active:true});assert.equal(h.calls.length,1);
  await h.render({active:false});h.calls.length=0;await h.key();assert.equal(h.calls.length,0);
 }finally{await h.close();}
});
