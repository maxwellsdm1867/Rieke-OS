import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useLayoutEffect} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {usePreparedTraceGeometry} from './usePreparedTraceGeometry.js';
import {RetainedWorkspaceViews,RetainedWorkspacePanel,useRetainedViewProtection} from '../retainedWorkspaceViews.js';
import {traceDisplaySegments} from './ui/traceGeometry.js';
import {traceSampleStatistics} from './traceStatistics.js';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const context={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
async function harness(){
 const names=['window','ResizeObserver'],old=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
 const requests=[],events=[],observers=[],resolutions=[],presentation={remember(){}};
 let width=603,renderer,current,input={},suspended=false,release;
 const blocked=new Promise(resolve=>{release=resolve;});
 globalThis.window={devicePixelRatio:1,addEventListener(){},removeEventListener(){},matchMedia(query){const item={query,callback:null,addEventListener(_,fn){this.callback=fn;},removeEventListener(){this.callback=null;}};resolutions.push(item);return item;}};
 globalThis.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.closed=true;}};
 const canvas={current:{getBoundingClientRect(){events.push('measure');return {width};}}};
 const values=Float64Array.from({length:10000},(_,i)=>Math.sin(i/13));
 const stream={kind:'responses',uuid:uid(7),sample_count:values.length,sample_rate:10000,units:'pA'};
 const makeOwner=name=>({name,request(path,{signal}){events.push('request');return new Promise((resolve,reject)=>requests.push({path,signal,resolve,reject,context:input.readContext??context,source:input.sourceSha256??'b'.repeat(64),stream:input.stream??stream}));}});
 const owner=makeOwner('A');
 function Probe(props){
  useRetainedViewProtection({busy:true});
  current=usePreparedTraceGeometry({canvas,enabled:true,identity:'A',owner,request:owner.request,epochUuid:uid(6),sourceSha256:'b'.repeat(64),stream,readContext:context,...props});
  useLayoutEffect(()=>{events.push('following-layout');});
  if(suspended)throw blocked;
  return null;
 }
 const h={requests,events,owner,makeOwner,canvas,get current(){return current;},
  async render(props={}){input=props;await act(async()=>{
   const node=React.createElement(RetainedWorkspaceViews,{route:{page:'protocol',protocol:'p',key:'a'},projectId:'p',projectPath:'/p',presentation,
    render:()=>React.createElement(RetainedWorkspacePanel,{name:'trace',visible:props.visible!==false},React.createElement(React.Suspense,{fallback:null},React.createElement(Probe,props)))});
   if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);
  });},
  async finish(index,extra={}){const item=requests[index],url=new URL(item.path,'http://fixture'),physicalWidth=Number(url.searchParams.get('physical_width')),indices=Uint32Array.from(traceDisplaySegments(values,physicalWidth)[0]);
   const result={representation:'m4_geometry',algorithm:'first-last-extrema-v1',epoch_uuid:url.pathname.split('/').at(-2),stream_uuid:item.stream.uuid,source_sha256:item.source,sample_rate:item.stream.sample_rate,units:item.stream.units,read_context:item.context,raw_start:0,raw_count:values.length,total_samples:values.length,physical_width:physicalWidth,point_count:indices.length,indices,point_values:Float64Array.from(indices,i=>values[i]),statistics:traceSampleStatistics(values),...extra};
   await act(async()=>item.resolve(result));
  },
  async resize(next){width=next;await act(async()=>{for(const observer of [...observers])if(!observer.closed)observer.callback();});},
  async dpr(next){window.devicePixelRatio=next;await act(async()=>{for(const resolution of [...resolutions])resolution.callback?.();});},
  suspend(){suspended=true;},async resume(){suspended=false;await act(async()=>release());},
  async close(){await act(async()=>renderer?.unmount());for(const name of names){if(old[name]===undefined)delete globalThis[name];else globalThis[name]=old[name];}}
 };
 return h;
}

test('first committed canvas measurement dispatches before any following layout effect or width rerender',async()=>{
 const h=await harness();try{
  await h.render();assert.deepEqual(h.events.slice(0,3),['measure','request','following-layout']);assert.equal(h.requests.length,1);
  assert.equal(new URL(h.requests[0].path,'http://fixture').searchParams.get('physical_width'),'500');
  assert.equal(h.current.physicalWidth,500);assert.equal(h.current.loading,true);
  await h.finish(0);assert.equal(h.current.data.raw_count,10000);assert.equal(h.current.loading,false);
  await h.render({readContext:Object.fromEntries(Object.entries(context).reverse())});assert.equal(h.requests.length,1,'equal canonical capability fields do not refetch because JSON key order changed');
  await h.resize(603);assert.equal(h.requests.length,1,'initial/same-width observer callback cannot duplicate the read');
 }finally{await h.close();}
});

test('zero width waits, fractional resize and DPR changes replace exact current requests',async()=>{
 const h=await harness();try{
  await h.resize(0);await h.render();assert.equal(h.requests.length,0);assert.equal(h.current.physicalWidth,null);
  await h.resize(603.25);assert.equal(h.requests.length,1);assert.equal(h.current.physicalWidth,500.25);
  await h.resize(703.25);assert(h.requests[0].signal.aborted);assert.equal(h.current.physicalWidth,600.25);
  await h.finish(0);assert.equal(h.current.data,null);
  await h.dpr(2);assert(h.requests[1].signal.aborted);assert.equal(h.current.physicalWidth,1200.5);
  await h.finish(1);assert.equal(h.current.data,null);await h.finish(2);assert.equal(h.current.data.physical_width,1200.5);
 }finally{await h.close();}
});

test('completed A cannot revive after pending B, current owner replacement or reload',async()=>{
 const h=await harness();try{
  await h.render();await h.finish(0);await h.render({identity:'B',epochUuid:uid(8)});await h.render();
  assert(h.requests[0].signal.aborted);assert(h.requests[1].signal.aborted);assert.equal(h.current.data,null);
  await h.finish(1);assert.equal(h.current.data,null);await h.finish(2);assert.equal(h.current.data.epoch_uuid,uid(6));
  const next=h.makeOwner('new');await h.render({owner:next,request:next.request});assert(h.requests[2].signal.aborted);assert.equal(h.current.data,null);
  await h.finish(3);await act(async()=>h.current.reload());assert(h.requests[3].signal.aborted);assert.equal(h.current.data,null);assert.equal(h.requests.length,5);
 }finally{await h.close();}
});

test('hidden retained geometry does not read while unrelated busy protection keeps effects mounted',async()=>{
 const h=await harness();try{
  await h.render();await h.render({visible:false});assert(h.requests[0].signal.aborted);
  await h.resize(703);await h.dpr(2);await act(async()=>h.current.reload());assert.equal(h.requests.length,1);
  await h.finish(0);assert.equal(h.current.data,null);
  await h.render();assert.equal(h.requests.length,2);assert.equal(h.current.physicalWidth,1200);await h.finish(1);assert.equal(h.current.data.physical_width,1200);
 }finally{await h.close();}
});

test('a suspended uncommitted owner starts no geometry read',async()=>{
 const h=await harness();try{
  await h.render();await h.finish(0);h.suspend();await h.render({identity:'B',epochUuid:uid(8)});
  assert.equal(h.requests.length,1,'rendering another owner without commit never starts transport');
  await h.resume();assert.equal(h.requests.length,2);assert(h.requests[0].signal.aborted);await h.finish(1);assert.equal(h.current.data.epoch_uuid,uid(8));
 }finally{await h.close();}
});

test('geometry disable and unsupported-width decisions expose no display request',async()=>{
 const h=await harness();try{
  await h.render({requestEnabled:false});assert.equal(h.current.physicalWidth,500);assert.equal(h.current.useGeometry,false);assert.equal(h.requests.length,0);
  await h.render();assert.equal(h.requests.length,1);await h.render({enabled:false});assert(h.requests[0].signal.aborted);assert.equal(h.current.physicalWidth,null);
  await h.resize(20000);await h.render();assert.equal(h.current.useGeometry,false);assert.equal(h.current.physicalWidth,19897);assert.equal(h.requests.length,1);
 }finally{await h.close();}
});
