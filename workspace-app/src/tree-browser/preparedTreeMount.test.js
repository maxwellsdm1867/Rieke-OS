import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';
for(const name of ['ColumnTree','HierarchyTree'])test(`${name} prepares on first demand and cancels stale preparation`,async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://fixture/',pretendToBeVisual:true}),keys=['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const previous=Object.fromEntries(keys.map(k=>[k,globalThis[k]]));
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true,requestAnimationFrame:f=>setTimeout(f,0),cancelAnimationFrame:clearTimeout});
 const calls=[];let held;
 globalThis.fetch=async(url,options)=>{calls.push({url,options});if(url.endsWith('/prepare'))return new Promise(resolve=>held=resolve);return new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:'tree'}}),{status:202});};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:View}=await server.ssrLoadModule(`/src/tree-browser/ui/${name}.jsx`),root=createRoot(document.querySelector('main'));
 const render=protocolId=>act(async()=>root.render(React.createElement(View,{protocolId,projectId:'project',splits:'cell',browseOnly:true})));
 try{
  await render('a');assert.equal(calls.length,2);assert.match(document.body.textContent,/Preparing view/);
  assert.deepEqual(JSON.parse(calls[1].options.body),{protocol_uuid:'a',filters:{},splits:'cell'});
  const abandoned=held;await render('b');assert.equal(calls[1].options.signal.aborted,true);assert.equal(calls.length,4);
  await act(()=>abandoned(new Response(JSON.stringify({status:'ready'}))));assert.equal(calls.length,4);
  await act(()=>held(new Response(JSON.stringify({status:'ready'}))));assert.equal(calls.length,5);
  assert.match(document.body.textContent,/Show tree/);
 }finally{await act(()=>root.unmount());await server.close();dom.window.close();for(const[k,v]of Object.entries(previous)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
});

async function preparationHarness(name){
 const dom=new JSDOM('<main></main>',{url:'http://fixture/',pretendToBeVisual:true}),keys=['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const previous=Object.fromEntries(keys.map(k=>[k,globalThis[k]]));
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true,requestAnimationFrame:f=>setTimeout(f,0),cancelAnimationFrame:clearTimeout});
 const calls=[];let ready=false,failPrepare=false,holdRead=null,responseRevision='a'.repeat(64);
 const pending=()=>new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:'tree'}}),{status:202});
 globalThis.fetch=async(url,options)=>{
  calls.push({url,options});
  if(url.endsWith('/prepare')){if(failPrepare==='network')throw Error('preparation offline');if(failPrepare)return pending();ready=true;return new Response(JSON.stringify({status:'ready'}));}
  if(holdRead)return new Promise(resolve=>holdRead(resolve));
  if(!ready)return pending();
  const body=JSON.parse(options.body);
  return new Response(JSON.stringify({revision:responseRevision,kind:'branches',path:[],depth:0,offset:0,limit:body.limit,total:0,total_epochs:9,selection:{count:9},split_order:body.splits.split(','),levels:[],ancestors:[],branches:[],epochs:[],has_more:false}));
 };
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:View}=await server.ssrLoadModule(`/src/tree-browser/ui/${name}.jsx`),root=createRoot(document.querySelector('main'));
 return {calls,pending,set responseRevision(value){responseRevision=value;},set ready(value){ready=value;},set failPrepare(value){failPrepare=value;},set holdRead(value){holdRead=value;},
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


for(const name of ['ColumnTree','HierarchyTree'])test(`${name} failed preparation is not repeated on unchanged hide/show or pause`,async()=>{
 const h=await preparationHarness(name);
 try{
  h.failPrepare=true;await h.render({});assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);
  await h.render({active:false});await h.render({active:true});
  await h.render({active:true,readPaused:true});await h.render({active:true,readPaused:false});
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);
  h.failPrepare=false;await h.key();assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,2);
  assert.equal(document.querySelector('[role="alert"]'),null);
 }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} prepares a predicate tree without renewing its expected revision`,async()=>{
 const h=await preparationHarness(name),expectedRevision='a'.repeat(64),predicate={all:[{field:'EpochBlock.protocol_name',operator:'contains',value:'History'}]};let metadata=0,refreshes=0;
 const props={protocolId:undefined,predicate,expectedRevision,onMetadata(){metadata++;},onRefreshPreview(){refreshes++;}};
 try{
  await h.render(props);assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);assert.equal(metadata,1);assert.equal(refreshes,0);
  assert.deepEqual(JSON.parse(h.calls.find(call=>call.url.endsWith('/prepare')).options.body),{predicate,filters:{},splits:'cell'});
  for(const call of h.calls.filter(call=>!call.url.endsWith('/prepare')))assert.equal(JSON.parse(call.options.body).revision,expectedRevision);
  h.ready=false;h.responseRevision='b'.repeat(64);metadata=0;h.calls.length=0;
  await h.render({...props,revision:1});assert.equal(metadata,0);assert.equal(refreshes,0);
  assert.match(document.body.textContent,/Tree revision changed/);
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);
  for(const call of h.calls.filter(call=>!call.url.endsWith('/prepare')))assert.equal(JSON.parse(call.options.body).revision,expectedRevision);
 }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} never prepares a frozen review-owned context`,async()=>{
 const h=await preparationHarness(name);
 try{
  await h.render({readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'}});
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].url,'/api/protocols/p/workbench/candidates/c/tree/page');
  assert.match(document.body.textContent,/Show tree/);
 }finally{await h.close();}
});

test('hierarchy selected-anchor first read prepares once and keeps the expected revision',async()=>{
 const h=await preparationHarness('HierarchyTree'),expectedRevision='a'.repeat(64);
 try{
  await h.render({selected:'epoch',expectedRevision});
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);
  const reads=h.calls.filter(call=>!call.url.endsWith('/prepare'));
  assert.ok(reads.length>=2);for(const call of reads){const body=JSON.parse(call.options.body);assert.equal(body.revision,expectedRevision);assert.equal(body.anchor_uuid,'epoch');}
  assert.equal(document.querySelector('[role="alert"]'),null);
 }finally{await h.close();}
});


for(const name of ['ColumnTree','HierarchyTree'])for(const revisit of [false,true])test(`${name} explicit retry recovers a network-failed preparation with the same query revision (revisit=${revisit})`,async()=>{
 const h=await preparationHarness(name),expectedRevision='a'.repeat(64);let metadata=0,refreshes=0;
 const props={expectedRevision,onMetadata(){metadata++;},onRefreshPreview(){refreshes++;}};
 try{
  h.failPrepare='network';await h.render(props);assert.match(document.body.textContent,/preparation offline/);
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);
  if(revisit){await h.render({...props,active:false});await h.render({...props,active:true});}
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,1);
  h.failPrepare=false;await h.key();
  assert.equal(h.calls.filter(call=>call.url.endsWith('/prepare')).length,2);assert.equal(metadata,1);assert.equal(refreshes,0);
  for(const call of h.calls.filter(call=>!call.url.endsWith('/prepare')))assert.equal(JSON.parse(call.options.body).revision,expectedRevision);
 }finally{await h.close();}
});
