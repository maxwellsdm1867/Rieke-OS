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
