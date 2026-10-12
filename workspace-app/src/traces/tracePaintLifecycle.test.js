import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('trace paints once per data change and redraws only for actual size, DPR or appearance changes',async()=>{
  const names=['window','document','fetch','getComputedStyle','ResizeObserver','requestAnimationFrame','cancelAnimationFrame'];
  const previous=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
  const frames=new Map(),observers=[],listeners=new Map();let frameId=0,paints=0,renderer;
  let rect={width:600,height:300};
  globalThis.window={devicePixelRatio:1,addEventListener:(type,fn)=>listeners.set(type,fn),removeEventListener:(type,fn)=>{if(listeners.get(type)===fn)listeners.delete(type);}};
  globalThis.document={activeElement:null};
  globalThis.getComputedStyle=()=>({getPropertyValue:()=> '#555'});
  globalThis.requestAnimationFrame=fn=>{frames.set(++frameId,fn);return frameId;};
  globalThis.cancelAnimationFrame=id=>frames.delete(id);
  globalThis.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.closed=true;}};
  const canvas=base=>{
    const element={getBoundingClientRect:()=>rect};
    const context=new Proxy({canvas:element,fill(){if(base)paints++;}},{get:(object,key)=>key in object?object[key]:()=>{}});
    element.getContext=()=>context;return element;
  };
  const base=canvas(true),overlay=canvas(false);
  const epoch=uuid=>({epoch_uuid:uuid,streams:[{kind:'responses',uuid:`stream-${uuid}`,sample_count:3}]});
  globalThis.fetch=async path=>{const uuid=path.split('/')[3];return new Response(JSON.stringify({epoch_uuid:uuid,stream_uuid:`stream-${uuid}`,start:0,count:3,sample_rate:10000,units:'mV',values:[-1,0,2]}),{status:200});};
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
  const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
  const {epochResourceCache}=await server.ssrLoadModule('/src/resourceCache.js');epochResourceCache.invalidate();
  const render=async uuid=>act(async()=>{
    const element=React.createElement(Trace,{epoch:epoch(uuid)});
    if(renderer)renderer.update(element);else renderer=TestRenderer.create(element,{createNodeMock:node=>node.type==='canvas'?(node.props.className==='tv-base'?base:overlay):null});
  });
  const frame=async()=>act(async()=>{const work=[...frames.values()];frames.clear();for(const fn of work)fn();});
  const notify=()=>observers.findLast(observer=>!observer.closed).callback();
  try{
    await render('a');assert.equal(paints,1);
    notify();await frame();assert.equal(paints,1,'initial ResizeObserver delivery must not repaint the same data');
    await render('b');assert.equal(paints,2);notify();await frame();assert.equal(paints,2);
    rect={...rect,width:600.25};notify();assert.equal(paints,3,'observer redraw happens before another animation frame');notify();await frame();assert.equal(paints,3,'subpixel CSS resize must repaint even with equal rounded backing width');
    globalThis.window.devicePixelRatio=2;listeners.get('resize')();await frame();assert.equal(paints,4);assert.equal(base.width,1201);
    listeners.get('disco:appearance')();notify();await frame();assert.equal(paints,5,'unchanged size must not cancel an appearance redraw');
    listeners.get('disco:appearance')();rect={...rect,height:320};notify();assert.equal(paints,6);await frame();assert.equal(paints,6,'observer draw replaces pending appearance draw');
    assert.equal(renderer.root.findByProps({className:'tv-plot tv-zoom'}).props['data-epoch-arrows'],'ignore');
    listeners.get('disco:appearance')();await act(async()=>renderer.unmount());await frame();assert.equal(paints,6);
    assert.equal(listeners.size,0);assert(observers.every(observer=>observer.closed));
  }finally{
    await act(async()=>renderer?.unmount());await server.close();
    for(const name of names){if(previous[name]===undefined)delete globalThis[name];else globalThis[name]=previous[name];}
  }
});

test('box zoom commits only on release; pan preserves width and reuses whole samples',async()=>{
 const names=['window','document','getComputedStyle','ResizeObserver','requestAnimationFrame','cancelAnimationFrame'];
 const previous=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
 globalThis.window={devicePixelRatio:1,addEventListener(){},removeEventListener(){}};
 globalThis.document={activeElement:null};globalThis.getComputedStyle=()=>({getPropertyValue:()=> '#555'});
 const frames=new Map();let nextFrame=0,markerPaints=0;
 const flush=()=>{const work=[...frames.values()];frames.clear();for(const fn of work)fn();};
 globalThis.requestAnimationFrame=fn=>{frames.set(++nextFrame,fn);return nextFrame;};globalThis.cancelAnimationFrame=id=>frames.delete(id);globalThis.ResizeObserver=class{observe(){}disconnect(){}};
 const canvas=isBase=>{const element={getBoundingClientRect:()=>({left:0,top:0,width:603,height:300}),setPointerCapture(){},hasPointerCapture(){return true;},releasePointerCapture(){}};element.getContext=()=>new Proxy({canvas:element},{get:(o,k)=>k in o?o[k]:()=>{if(!isBase&&['fillRect','strokeRect','arc','stroke'].includes(k))markerPaints++;}});return element;};
 const base=canvas(true),overlay=canvas(false),surface={focus(){}};let renderer;const calls=[];
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const port={identity:'pointer-zoom',request:async path=>{const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count');calls.push({start,count});return {epoch_uuid:'e',stream_uuid:'s',start,count,total_samples:67500,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array.from({length:count},(_,i)=>start+i)};}};
 const epoch={epoch_uuid:'e',streams:[{kind:'responses',uuid:'s',sample_count:67500,sample_rate:10000,units:'pA'}]};
 const button=label=>renderer.root.findAllByType('button').find(n=>n.props.children===label||Array.isArray(n.props.children)&&n.props.children.includes(' '+label));
 const input=label=>renderer.root.findByProps({'aria-label':label}).props.value;
 const pointer=()=>renderer.root.findByProps({className:'tv-overlay'}).props;
 const event=(x,y=100)=>({button:0,pointerId:1,clientX:82+x,clientY:y,currentTarget:overlay});
 try{
  await act(async()=>{renderer=TestRenderer.create(React.createElement(WorkspaceRequestProvider,{port},React.createElement(Trace,{epoch})),{createNodeMock:node=>node.type==='canvas'?(node.props.className==='tv-base'?base:overlay):node.props.role==='group'?surface:{}});});
  assert.equal(calls.length,4);
  await act(async()=>renderer.root.findByProps({'aria-label':'Zoom in'}).props.onClick());assert.equal(button('Whole epoch').props['aria-pressed'],true);
  await act(async()=>{pointer().onPointerDown(event(100,65));pointer().onPointerMove(event(400,195));});
  assert.equal(button('Whole epoch').props['aria-pressed'],true,'dragging does not switch mode before release');
  await act(async()=>pointer().onPointerUp(event(400,195)));
  assert.equal(button('Sample').props['aria-pressed'],true);assert.equal(input('Start sample'),'13500');assert.equal(input('Sample count'),'40500');
  const boundsText=()=>renderer.root.findByProps({'aria-label':'Selected response bounds'}).children.join('');
  const beforePan=boundsText();assert.match(beforePan,/pA/);
  assert.match(renderer.root.findByProps({'aria-label':'Selected sample bounds'}).children.join(''),/Start 13,500 · Stop 53,999/);
  await act(async()=>button('Pan').props.onClick());flush();markerPaints=0;
  await act(async()=>pointer().onPointerMove(event(200)));flush();
  assert.equal(markerPaints,0,'Pan hover has no crosshair or sample marker');
  await act(async()=>{pointer().onPointerDown(event(200));pointer().onPointerMove(event(250,115));});
  flush();assert.equal(markerPaints,0,'Pan drag has no selection box or interactive markers');
  assert.equal(input('Start sample'),'9450','pan moves while the pointer is held');
  assert.equal(input('Sample count'),'40500','live pan keeps zoom width');
  await act(async()=>pointer().onPointerMove(event(300,130)));
  assert.equal(input('Start sample'),'5400','successive moves are anchored to drag start, without accumulating drift');
  await act(async()=>pointer().onPointerUp(event(300,130)));
  assert.equal(input('Start sample'),'5400','release does not apply the delta twice');
  assert.notEqual(boundsText(),beforePan,'vertical panning moves response bounds');
  assert.equal(input('Start sample'),'5400');assert.equal(input('Sample count'),'40500');
  assert.equal(calls.length,4,'box zoom and pan do not reload any samples');
  await act(async()=>button('Whole epoch').props.onClick());assert.equal(calls.length,4);assert.equal(renderer.root.findAllByProps({'aria-label':'Selected response bounds'}).length,0);
  await act(async()=>{pointer().onPointerDown(event(200,65));pointer().onPointerMove(event(200,195));pointer().onPointerUp(event(200,195));});
  assert.equal(input('Sample count'),'67500','vertical-only zoom preserves the whole time range');
  assert.equal(renderer.root.findByProps({'aria-label':'Zoom out'}).props.disabled,false);
  await act(async()=>renderer.root.findByProps({'aria-label':'Zoom out'}).props.onClick());
  assert.equal(renderer.root.findAllByProps({'aria-label':'Selected response bounds'}).length,0,'zoom out recovers the whole response range');
  assert.equal(calls.length,4,'vertical zoom and zoom out require no reads');
  await act(async()=>button('Sample').props.onClick());assert.equal(input('Start sample'),'0');assert.equal(input('Sample count'),'200');assert.equal(calls.length,4);
 }finally{await act(async()=>renderer?.unmount());await server.close();for(const name of names){if(previous[name]===undefined)delete globalThis[name];else globalThis[name]=previous[name];}}
});
