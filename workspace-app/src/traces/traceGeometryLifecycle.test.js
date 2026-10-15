import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useLayoutEffect} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {traceDisplaySegments} from './ui/traceGeometry.js';
import {traceSampleStatistics} from './traceStatistics.js';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const captured={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
async function harness({holdDisplay=false,displayError=null}={}){
 const names=['window','document','getComputedStyle','ResizeObserver','requestAnimationFrame','cancelAnimationFrame'],previous=Object.fromEntries(names.map(n=>[n,globalThis[n]]));
 const observers=[],resolutions=[],frames=new Map(),strokes=[],requests=[],followingLayoutRequests=[];let frameId=0,renderer;
 let rect={left:0,top:0,width:603,height:300};
 globalThis.window={devicePixelRatio:1,addEventListener(){},removeEventListener(){},matchMedia(query){const value={query,callback:null,addEventListener(_,cb){this.callback=cb;},removeEventListener(){this.callback=null;}};resolutions.push(value);return value;}};
 globalThis.document={activeElement:null};globalThis.getComputedStyle=()=>({getPropertyValue:name=>name==='--plot-trace'?'trace':name});
 globalThis.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.closed=true;}};
 globalThis.requestAnimationFrame=cb=>{frames.set(++frameId,cb);return frameId;};globalThis.cancelAnimationFrame=id=>frames.delete(id);
 const makeCanvas=base=>{const node={getBoundingClientRect:()=>rect};let points=[];const ctx=new Proxy({canvas:node,beginPath(){points=[];},moveTo(x,y){points.push([x,y]);},lineTo(x,y){points.push([x,y]);},stroke(){if(base&&this.strokeStyle==='trace')strokes.push(points.slice());}},{get:(o,k)=>k in o?o[k]:()=>{}});node.getContext=()=>ctx;return node;};
 const canvas=makeCanvas(true),overlay=makeCanvas(false),response={textContent:''},generic={textContent:'',focus(){}};
 const count=100000,values=Float64Array.from({length:count},(_,i)=>Math.sin(i/13));values[123]=3;values[456]=-4;
 const stream={kind:'responses',uuid:uid(7),sample_count:count,sample_rate:10000,units:'pA'};
 const epoch={epoch_uuid:uid(6),source_sha256:'b'.repeat(64),streams:[stream]};let activeEpoch=epoch,activeContext=captured;
 const request=(path,{signal})=>new Promise((resolve,reject)=>{
  const url=new URL(path,'http://fixture'),isDisplay=url.pathname.endsWith('/display'),start=Number(url.searchParams.get('start')),size=Number(url.searchParams.get('count')),width=Number(url.searchParams.get('physical_width'));
  const header={epoch_uuid:activeEpoch.epoch_uuid,stream_uuid:activeEpoch.streams[0].uuid,source_sha256:activeEpoch.source_sha256,sample_rate:10000,units:'pA',read_context:activeContext,total_samples:count};
  const item={path,signal,isDisplay,start,count:size,width,reject,finish(change={}){if(isDisplay){const indices=Uint32Array.from(traceDisplaySegments(values,width)[0]),point_values=Float64Array.from(indices,index=>values[index]);resolve({...header,representation:'m4_geometry',algorithm:'first-last-extrema-v1',raw_start:0,raw_count:count,physical_width:width,point_count:indices.length,indices,point_values,statistics:traceSampleStatistics(values),...change});}else resolve({...header,start,count:size,decimated:false,values:values.slice(start,start+size),...change});}};requests.push(item);
  if(isDisplay){if(displayError)reject(displayError);else if(!holdDisplay)item.finish();}
 });
 const port={identity:'geometry-session',request};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx'),{WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 function FollowingLayout(){useLayoutEffect(()=>{followingLayoutRequests.push(requests.length);});return null;}
 const render=async({record=epoch,context=captured,owner=port}={})=>act(async()=>{activeEpoch=record;activeContext=context;const node=React.createElement(WorkspaceRequestProvider,{port:owner},React.createElement(React.Fragment,null,React.createElement(Trace,{epoch:record,readContext:context}),React.createElement(FollowingLayout)));if(renderer)renderer.update(node);else renderer=TestRenderer.create(node,{createNodeMock:n=>n.type==='canvas'?(n.props.className==='tv-base'?canvas:overlay):n.props['aria-label']==='Recorded response and scientific units'?response:generic});});
 return {requests,strokes,values,epoch,port,response,resolutions,followingLayoutRequests,get root(){return renderer.root;},render,
  async frame(){await act(async()=>{const callbacks=[...frames.values()];frames.clear();callbacks.forEach(cb=>cb());});},
  async resize(width){await act(async()=>{rect={...rect,width};for(const observer of [...observers].reverse())if(!observer.closed)observer.callback();});},
  async dpr(value){await act(async()=>{window.devicePixelRatio=value;for(const resolution of [...resolutions])resolution.callback?.();});},
  async close(){await act(async()=>renderer?.unmount());await server.close();for(const n of names){if(previous[n]===undefined)delete globalThis[n];else globalThis[n]=previous[n];}}
 };
}
test('prepared whole geometry paints without raw prefetch; exact cursor and sample view demand bounded raw data',async()=>{
 const h=await harness();try{
  await h.render();assert.equal(h.requests.length,1);assert(h.requests[0].isDisplay);assert.equal(h.requests[0].width,500);assert(h.strokes.length);assert.equal(h.root.findByProps({'aria-label':'Exact sample index for cursor'}).props.disabled,false);
  await act(async()=>h.root.findByProps({'aria-label':'Exact sample index for cursor'}).props.onChange({target:{value:'12345'}}));await h.frame();
  assert.equal(h.requests.length,2);assert.equal(h.requests[1].isDisplay,false);assert.equal(h.requests[1].count,20000);assert.equal(h.response.textContent,'Loading sample…');
  await act(async()=>h.requests[1].finish());await h.frame();assert.equal(h.response.textContent,String(h.values[12345])+' pA');
  await act(async()=>h.root.findAllByType('button').find(n=>n.props.children==='Sample').props.onClick());assert.equal(h.requests.length,3);assert.equal(h.requests[2].count,200,'geometry never pretends to retain whole raw values');
  await act(async()=>h.requests[2].finish());assert.equal(h.root.findByProps({'aria-label':'Exact sample index for cursor'}).props.disabled,false);
 }finally{await h.close();}
});
test('resize clears incompatible geometry, rejects late width responses, and DPR-only change requests exact new bins',async()=>{
 const h=await harness({holdDisplay:true});try{
  await h.render();await act(async()=>h.requests[0].finish());const painted=h.strokes.length;
  await h.resize(703.25);assert.equal(h.strokes.length,painted,'old geometry is never painted at the new width');assert.equal(h.requests[1].width,600.25);
  await h.resize(803.25);assert(h.requests[1].signal.aborted);assert.equal(h.requests[2].width,700.25);
  await act(async()=>h.requests[1].finish());assert.equal(h.strokes.length,painted);
  await act(async()=>h.requests[2].finish());assert.equal(h.strokes.length,painted+1);
  await h.dpr(2);assert.equal(h.requests[3].width,1400.5,'resolution change works without CSS resize');assert(h.resolutions.some(item=>item.query==='(resolution: 2dppx)'));
  await act(async()=>h.requests[3].finish());assert.equal(h.strokes.length,painted+2);assert.equal(h.requests.filter(r=>!r.isDisplay).length,0);
 }finally{await h.close();}
});
test('old epoch geometry cannot publish after focus replacement',async()=>{
 const h=await harness({holdDisplay:true});try{
  await h.render();await h.render({record:{...h.epoch,epoch_uuid:uid(9)}});assert(h.requests[0].signal.aborted);
  await act(async()=>h.requests[0].finish());assert.equal(h.strokes.length,0);
  await act(async()=>h.requests[1].finish());assert(h.strokes.length);
  assert.equal(h.requests.filter(r=>!r.isDisplay).length,0);
 }finally{await h.close();}
});
test('typed geometry unavailable alone triggers same-prepared raw fallback',async()=>{
 const unavailable=Object.assign(Error('unsupported layout'),{status:409,data:{code:'trace_geometry_unavailable'}}),h=await harness({displayError:unavailable});try{
  await h.render();assert.equal(h.requests.length,2);assert(h.requests[0].isDisplay);assert.equal(h.requests[1].isDisplay,false);assert(h.requests[1].path.startsWith(`/trace-views/${captured.token}/`));
  await act(async()=>h.requests[1].finish());assert(h.strokes.length);
  await h.resize(703.25);assert.equal(h.requests.length,2,'unsupported geometry retains its one raw interval across resize');
 }finally{await h.close();}
 const failed=await harness({displayError:Object.assign(Error('source changed'),{status:409,data:{code:'source_changed'}})});try{
  await failed.render();assert.equal(failed.requests.length,1);assert.equal(failed.strokes.length,0);assert(failed.root.findAllByProps({role:'alert'}).some(n=>n.children.includes('source changed')));
 }finally{await failed.close();}
});

test('current geometry error retries the same prepared display owner without a raw fallback',async()=>{
 const h=await harness({holdDisplay:true});try{
  await h.render();await act(async()=>h.requests[0].reject(Error('Current geometry read failed')));
  assert(h.root.findAllByProps({role:'alert'}).some(n=>n.children.includes('Current geometry read failed')));
  const retry=h.root.findAllByType('button').find(n=>n.props.children==='Retry trace');
  await act(async()=>retry.props.onClick());
  assert.equal(h.requests.length,2);assert(h.requests[0].signal.aborted);assert(h.requests[1].isDisplay);assert.equal(h.requests[1].path,h.requests[0].path);
  await act(async()=>h.requests[1].finish());assert(h.strokes.length);assert.equal(h.requests.filter(r=>!r.isDisplay).length,0);
 }finally{await h.close();}
});


test('actual Trace dispatches geometry during its first committed layout before its following sibling',async()=>{
 const h=await harness({holdDisplay:true});try{
  await h.render();
  assert.equal(h.followingLayoutRequests[0],1,'actual consumer must request before width publication can cause a second commit');
  assert.equal(h.requests.length,1);assert(h.requests[0].isDisplay);assert.equal(h.requests[0].width,500);
  assert.equal(h.strokes.length,0);
  await act(async()=>h.requests[0].finish());assert(h.strokes.length);
 }finally{await h.close();}
});
