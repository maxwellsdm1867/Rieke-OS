import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useEffect,useState} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {RetainedWorkspaceViews,RetainedWorkspacePanel,useRetainedViewProtection} from '../retainedWorkspaceViews.js';
import {api,useResource,useEpochPrefetch,useEpochResource} from '../api.js';
import {epochResourceCache} from '../resourceCache.js';
import {hasPendingDesktopWrites,flushDesktopDrafts} from '../desktopLifecycle.js';
import {useEpochBrowserPage} from '../epoch-browser/useEpochBrowserPage.js';
import {usePreparedTraceRead} from './usePreparedTraceRead.js';
import {useExactTraceCursor} from './useExactTraceCursor.js';
import {useFieldRegistry} from '../summary-jobs/useFieldRegistry.js';
import {useOverviewResource} from '../protocol-overview/useOverviewResource.js';
import {createOverviewCache} from '../protocol-overview/overviewCache.js';

const tick=async(t,ms)=>act(async()=>{t.mock.timers.tick(ms);for(let i=0;i<15;i++)await Promise.resolve();});
async function harness(t,{held=false,offer=null}={}){
 const oldFetch=globalThis.fetch,requests=[],pending=[],cache=createOverviewCache();let renderer,current,setText,cleanups=0,starts=0,finishScan;
 const presentation={remember(){}},requestPort={identity:'exact-owner',request:api};
 epochResourceCache.invalidate();
 const body=path=>path.includes('/epochs/warm')?{epoch_uuid:'warm',streams:[]}:{fields:[],epochs:[],query_revision:'q',total:0,path};
 const response=path=>new Response(JSON.stringify(body(path)),{status:200,headers:{'Content-Type':'application/json'}});
 globalThis.fetch=(url,options={})=>{
  const path=url.slice(4),entry={path,...options};requests.push(entry);
  if(path==='/annotations/scan')return new Promise(resolve=>{finishScan=()=>resolve(response(path));});
  if(held&&options.method!=='POST')return new Promise(resolve=>pending.push({entry,resolve:()=>resolve(response(path))}));
  return Promise.resolve(response(path));
 };
 function Page({revision}){
  const [text,update]=useState(''),[busy,setBusy]=useState(false);setText=update;
  useRetainedViewProtection({dirty:!!text,busy});
  useEffect(()=>{starts++;return()=>cleanups++;},[]);
  const plain=useResource('/storage',revision),cached=useEpochResource('/epochs/warm',revision);
  const custom=useResource('/custom/page',revision,0,{requestPort});
  const initial=useResource(offer?'/initial-page':null,revision,0,{initialRead:offer});
  const page=useEpochBrowserPage({kind:'protocol',protocolId:'p'},{cellUuid:'cell'},revision);
  const prepared=usePreparedTraceRead('/captured/trace',revision,requestPort);
  const registry=useFieldRegistry(revision),overview=useOverviewResource('/overview',revision,{cache,scope:'p'});
  useEpochPrefetch(['/epochs/neighbor/trace?stream_uuid=s&start=0&count=3'],revision,80,{traceOnly:true});
  current={plain,cached,custom,initial,page,prepared,registry,overview,text,
   save:async()=>{setBusy(true);try{await api('/annotations/scan',{method:'POST',body:{}});}finally{setBusy(false);}}};
  return React.createElement('input',{value:text});
 }
 const h={requests,pending,get current(){return current;},get starts(){return starts;},get cleanups(){return cleanups;},
  async render({visible=true,revision=0,route='a'}={}){await act(async()=>{
   const node=React.createElement(RetainedWorkspaceViews,{route:{page:'protocol',protocol:'p',key:route},projectId:'p',projectPath:'/p',presentation,
    render:destination=>destination.key==='a'?React.createElement(RetainedWorkspacePanel,{name:'inspect',visible},React.createElement(Page,{revision})):null});
   if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);
  });},
  async text(value){await act(async()=>setText(value));},
  scan(){return api('/annotations/scan',{method:'POST',body:{}});},
  async finish(){await act(async()=>{finishScan?.();for(let i=0;i<15;i++)await Promise.resolve();});},
  async close(){await h.finish();await act(async()=>renderer?.unmount());for(const item of pending)item.resolve();cache.clear();epochResourceCache.invalidate();globalThis.fetch=oldFetch;t.mock.timers.reset();}
 };
 t.mock.timers.enable({apis:['setTimeout']});return h;
}

test('unrelated scan reconnects hidden Activity without any hidden read, prefetch, or lost presentation',async t=>{
 const h=await harness(t);let write;
 try{
  await h.render();await h.text('unfinished tag');assert.equal(h.current.plain.loading,false);
  await h.render({visible:false});assert.equal(h.cleanups,1,'ordinary hidden Activity disconnects effects');
  h.requests.length=0;write=h.scan();assert(hasPendingDesktopWrites());
  await h.render({visible:false,revision:1});await tick(t,200);
  assert.equal(h.starts,2,'pending global write really reconnects the hidden Activity');
  assert.deepEqual(h.requests.map(r=>r.path),['/annotations/scan'],'no resource/page/registry/overview/prepared/prefetch read follows hidden reconnect');
  await act(async()=>{for(const name of ['plain','cached','custom','page','prepared','registry','overview'])h.current[name].reload();});
  await tick(t,200);assert.equal(h.requests.length,1,'imperative reload remains queued while hidden');
  assert.equal(h.current.plain.loading,true);assert.equal(h.current.overview.loading,true,'deferred overview retry cannot look fresh');
  await h.finish();await write;await flushDesktopDrafts();assert.equal(hasPendingDesktopWrites(),false);
  await h.render({revision:1});await tick(t,80);
  for(const path of ['/storage','/epochs/warm','/custom/page','/captured/trace','/explore/field-registry','/overview'])assert.equal(h.requests.filter(r=>r.path===path).length,1,path);
  assert.equal(h.requests.filter(r=>r.path.startsWith('/protocols/p/epochs?')).length,1);
  assert.equal(h.requests.filter(r=>r.path.startsWith('/epochs/neighbor/trace?')).length,1);
  assert.equal(h.current.text,'unfinished tag');assert.equal(h.current.plain.loading,false);
 }finally{await h.close();await write;}
});

test('a hidden accepted write finishes while read lifetimes abort and reject late publication',async t=>{
 const h=await harness(t,{held:true});let write;
 try{
  await h.render();const reads=[...h.requests];assert(reads.length>3);
  await act(async()=>{write=h.current.save();});assert(hasPendingDesktopWrites());
  await h.render({visible:false});assert.equal(h.cleanups,0,'accepted write owner stays mounted');
  for(const read of reads.filter(r=>r.path!=='/overview'&&r.path!=='/epochs/warm'))assert.equal(read.signal.aborted,true,read.path);
  await tick(t,0);assert.equal(reads.find(r=>r.path==='/epochs/warm').signal.aborted,true,'shared cached demand retires after the existing handoff turn');
  await act(async()=>{for(const item of h.pending)item.resolve();});
  assert.equal(h.current.plain.data,null);assert.equal(h.current.prepared.data,null);
  await tick(t,200);assert.equal(h.requests.filter(r=>r.path.includes('neighbor')).length,0);
  await h.finish();await write;assert.equal(hasPendingDesktopWrites(),false);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1,'write is neither cancelled nor repeated');
 }finally{await h.close();await write;}
});

test('inactive route defers same-revision reload and retires an initial scientific page offer',async t=>{
 let claims=0;const offer={claim(){claims++;return {receipt:'initial'};}};
 const h=await harness(t,{offer});let write;
 try{
  await h.render();assert.equal(claims,1);assert.equal(h.current.initial.data.receipt,'initial');const oldOverviewReload=h.current.overview.reload;
  write=h.scan();await h.render({route:'b'});const before=h.requests.length;
  await act(async()=>{h.current.plain.reload();h.current.initial.reload();oldOverviewReload();});
  await tick(t,100);assert.equal(h.requests.length,before);
  await h.render();assert.equal(h.requests.filter(r=>r.path==='/storage').length,2);
  assert.equal(h.requests.filter(r=>r.path==='/overview').length,2,'same-revision hidden overview reload forces one read on return');
  assert.equal(h.requests.filter(r=>r.path==='/initial-page').length,1);assert.equal(claims,1,'hidden offer cannot be reclaimed as a fresh page');
 }finally{await h.close();await write;}
});

test('hidden cursor cancels deferred hover and in-flight tile while a global write keeps Activity mounted',async t=>{
 const oldFetch=globalThis.fetch,requests=[];let renderer,current,finishScan,write;
 const owner={},request=(path,{signal})=>new Promise(resolve=>requests.push({path,signal,resolve}));
 const stream={uuid:'s',sample_count:40000,sample_rate:10000,units:'pA'},presentation={remember(){}};
 globalThis.fetch=()=>new Promise(resolve=>{finishScan=()=>resolve(new Response('{}',{status:200}));});
 function Cursor(){current=useExactTraceCursor({enabled:true,identity:'fixed',owner,request,epochUuid:'e',sourceSha256:'a',stream,readContext:null});return null;}
 const render=visible=>act(async()=>{const node=React.createElement(RetainedWorkspaceViews,{route:{page:'protocol',protocol:'p',key:'a'},projectId:'p',projectPath:'/p',presentation,
  render:()=>React.createElement(RetainedWorkspacePanel,{name:'inspect',visible},React.createElement(Cursor))});if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);});
 t.mock.timers.enable({apis:['setTimeout']});
 try{
  await render(true);await act(async()=>current.read(1));write=api('/annotations/scan',{method:'POST',body:{}});
  await render(false);await tick(t,100);assert.equal(requests.length,0,'queued hover intent is cancelled on hide');
  await act(async()=>current.read(2,{immediate:true}));assert.equal(requests.length,0,'hidden callbacks cannot issue raw tile reads');
  await render(true);await act(async()=>current.read(1,{immediate:true}));assert.equal(requests.length,1);
  await render(false);assert.equal(requests[0].signal.aborted,true);
  await act(async()=>requests[0].resolve({}));assert.equal(current.sample(1).state,'pending');
 }finally{await act(async()=>{finishScan?.();await write;renderer?.unmount();});globalThis.fetch=oldFetch;t.mock.timers.reset();}
});


test('an uncommitted overview reveal cannot activate a retained reload callback',async()=>{
 const oldFetch=globalThis.fetch,requests=[],cache=createOverviewCache(),presentation={remember(){}};
 let renderer,current,reveal,finishScan,write,suspend=false;
 const blocked=new Promise(resolve=>{reveal=resolve;});
 globalThis.fetch=(url,options={})=>{
  requests.push({url,...options});
  if(url==='/api/annotations/scan')return new Promise(resolve=>{finishScan=()=>resolve(new Response('{}',{status:200}));});
  return Promise.resolve(new Response('{"value":"saved overview"}',{status:200}));
 };
 function Overview(){current=useOverviewResource('/overview',0,{cache,scope:'p'});if(suspend)throw blocked;return null;}
 const render=visible=>act(async()=>{
  const node=React.createElement(RetainedWorkspaceViews,{route:{page:'protocol',protocol:'p',key:'a'},projectId:'p',projectPath:'/p',presentation,
   render:()=>React.createElement(RetainedWorkspacePanel,{name:'overview',visible},React.createElement(React.Suspense,{fallback:null},React.createElement(Overview)))});
  if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);
 });
 try{
  await render(true);assert.equal(requests.length,1);const oldReload=current.reload;
  write=api('/annotations/scan',{method:'POST',body:{}});await render(false);
  suspend=true;await render(true);const before=requests.length;
  await act(async()=>oldReload());assert.equal(requests.length,before,'attempted reveal cannot publish visibility before its layout effect commits');
  suspend=false;await act(async()=>reveal());
  assert.equal(requests.filter(value=>value.url==='/api/overview').length,2,'queued explicit refresh runs exactly once after reveal commits');
 }finally{await act(async()=>{finishScan?.();await write;renderer?.unmount();});cache.clear();globalThis.fetch=oldFetch;}
});
