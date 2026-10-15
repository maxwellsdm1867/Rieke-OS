import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('actual million-sample canvas retains spikes and exact cursor while resize, DPR and zoom adapt display work',async()=>{
 const names=['window','document','getComputedStyle','ResizeObserver','requestAnimationFrame','cancelAnimationFrame'];
 const previous=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
 const frames=new Map(),observers=[],listeners=new Map(),strokes=[];let frameId=0,renderer,reads=0;
 let rect={left:0,top:0,width:603,height:300};
 globalThis.window={devicePixelRatio:1,addEventListener:(type,fn)=>listeners.set(type,fn),removeEventListener:(type,fn)=>{if(listeners.get(type)===fn)listeners.delete(type);}};
 globalThis.document={activeElement:null};globalThis.getComputedStyle=()=>({getPropertyValue:name=>name==='--plot-trace'?'trace':name});
 globalThis.requestAnimationFrame=fn=>{frames.set(++frameId,fn);return frameId;};globalThis.cancelAnimationFrame=id=>frames.delete(id);
 globalThis.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.closed=true;}};
 const canvas=isBase=>{
  const element={getBoundingClientRect:()=>rect};let path=[];
  const context=new Proxy({canvas:element,beginPath(){path=[];},moveTo(x,y){path.push({move:true,x,y});},lineTo(x,y){path.push({move:false,x,y});},stroke(){if(isBase&&this.strokeStyle==='trace')strokes.push(path.slice());}},{get:(object,key)=>key in object?object[key]:()=>{}});
  element.getContext=()=>context;return element;
 };
 const base=canvas(true),overlay=canvas(false),responseReadout={textContent:''},otherRef={textContent:''};
 const values=new Float64Array(1000000),positive=123456,negative=123457;values[positive]=100.00000000000001;values[negative]=-100.00000000000001;
 const before=Buffer.from(values.buffer).toString('base64');
 const port={identity:'display-test',request:async path=>{
  reads++;const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count'),chunks=+(q.get('chunks')||1);
  const header={epoch_uuid:'e',stream_uuid:'s',total_samples:values.length,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false};
  const windows=Array.from({length:chunks},(_,i)=>{const at=start+i*count,n=Math.min(count,values.length-at);return {...header,start:at,count:n,values:values.subarray(at,at+n)};});
  return chunks>1?{...header,start,count:windows.reduce((sum,w)=>sum+w.count,0),windows}:windows[0];
 }};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx'),{WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const epoch={epoch_uuid:'e',streams:[{kind:'responses',uuid:'s',sample_count:values.length,sample_rate:10000,units:'pA'}]};
 const frame=async()=>act(async()=>{const work=[...frames.values()];frames.clear();for(const fn of work)fn();});
 const notify=()=>observers.findLast(observer=>!observer.closed).callback();
 const latest=()=>strokes.at(-1),indices=()=>latest().map(p=>Math.round((p.x-82)/(rect.width-103)*(values.length-1)));
 try{
  await act(async()=>{renderer=TestRenderer.create(React.createElement(WorkspaceRequestProvider,{port},React.createElement(Trace,{epoch})),{createNodeMock:node=>node.type==='canvas'?(node.props.className==='tv-base'?base:overlay):node.props['aria-label']==='Recorded response and scientific units'?responseReadout:otherRef});});
  assert.equal(reads,2);assert(latest().length<=2000);assert.deepEqual([indices()[0],indices().at(-1)],[0,999999]);assert(indices().includes(positive));assert(indices().includes(negative));
  const firstCount=latest().length;
  window.devicePixelRatio=2;listeners.get('resize')();await frame();assert(latest().length<=4000);assert(latest().length>firstCount);assert.equal(base.width,1206);
  rect={...rect,width:403};notify();assert(latest().length<=2400);assert(indices().includes(positive));assert(indices().includes(negative));
  await act(async()=>renderer.root.findByProps({'aria-label':'Exact sample index for cursor'}).props.onChange({target:{value:String(positive)}}));await frame();
  assert.equal(responseReadout.textContent,`${String(values[positive])} pA`,'exact cursor retains the full-precision original sample');
  await act(async()=>renderer.root.findAllByType('button').find(b=>b.props.children==='Sample').props.onClick());
  assert.equal(latest().length,200,'a zoomed sample window draws every sample');
  assert.equal(reads,2,'display changes never fetch or alter scientific data');
  assert.equal(Buffer.from(values.buffer).toString('base64'),before);
 }finally{await act(async()=>renderer?.unmount());await server.close();for(const name of names){if(previous[name]===undefined)delete globalThis[name];else globalThis[name]=previous[name];}}
});
