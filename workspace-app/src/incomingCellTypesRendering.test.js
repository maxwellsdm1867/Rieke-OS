import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {createServer} from './test-support/isolatedVite.js';

test('inline type counts expose distinct frozen cells without a popup or hover-only content',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 try{
  const {default:Types}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingCellTypes.jsx');
  const a={cell_uuid:'a',cell_type:'ON-midget',epochs:999};
  const html=renderToStaticMarkup(React.createElement(Types,{cells:[a,a,{cell_uuid:'b',cell_type:'ON-midget'},{cell_uuid:'c',cell_type:'Unknown'}],count:3}));
  assert.match(html,/aria-label="Frozen proposal cell types"/);
  assert.match(html,/<strong>2<\/strong> ON-midget/);
  assert.match(html,/<strong>1<\/strong> Unclassified/);
  assert.match(html,/role="listitem" tabindex="0"/,'individual pills remain keyboard reachable without an outer frame');
  assert.doesNotMatch(html,/role="list" tabindex=/);
  assert.doesNotMatch(html,/<details|<summary|title=|role="dialog"|incoming-type-disclosure|999/);
  const filtered=renderToStaticMarkup(React.createElement(Types,{cells:[a],count:1,scope:'Filtered incoming view',compact:true}));
  assert.match(filtered,/Filtered incoming view · 1 cell/);
  assert.match(filtered,/<strong>1<\/strong> ON-midget/);
  for(const props of [{cells:null,count:0},{cells:[],count:2}]){
   const unavailable=renderToStaticMarkup(React.createElement(Types,props));
   assert.match(unavailable,/Types unavailable/);assert.doesNotMatch(unavailable,/>0 cells</);
  }
  assert.match(renderToStaticMarkup(React.createElement(Types,{cells:[],count:0})),/>0 cells</);
 }finally{await server.close();}
});

async function disclosureHarness(){
 const dom=new JSDOM('<!doctype html><div id="root"></div><button id="outside">Outside</button>',{url:'http://localhost/'});
 const globals={window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true,fetch:()=>{throw Error('Type overview must not request data');}};
 const previous=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const {default:Types}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingCellTypes.jsx');
 const container=document.getElementById('root'),root=createRoot(container),outside=document.getElementById('outside');
 return {container,outside,get trigger(){return container.querySelector('.incoming-cell-type-trigger');},
  get card(){return container.querySelector('.incoming-cell-type-card');},
  async render(props={}){await act(()=>root.render(React.createElement(React.StrictMode,null,React.createElement(Types,{cells:[{cell_uuid:'a',cell_type:'ON-midget'},{cell_uuid:'b',cell_type:'Unknown'}],count:2,trigger:React.createElement('span',null,'+2 cells'),...props}))));},
  async pointer(node,type,relatedTarget=null,pointerType='mouse'){const event=new dom.window.MouseEvent(type,{bubbles:true,relatedTarget});Object.defineProperty(event,'pointerType',{value:pointerType});await act(()=>node.dispatchEvent(event));},
  async close(){await act(()=>root.unmount());await server.close();dom.window.close();for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}
 };
}

test('cell-count overview supports hover, keyboard, Escape, touch and outside dismissal',async()=>{
 const h=await disclosureHarness();
 try{
  await h.render();assert.equal(h.card,null);assert.equal(h.trigger.getAttribute('aria-expanded'),'false');
  await h.pointer(h.trigger,'pointerover');assert.ok(h.card);assert.equal(h.card.id,h.trigger.getAttribute('aria-controls'));
  assert.match(h.card.textContent,/ON-midget/);assert.match(h.card.textContent,/Unclassified/);
  const item=h.card.querySelector('[role=listitem]');await h.pointer(h.trigger,'pointerout',item);assert.ok(h.card,'pointer can enter the card');
  await h.pointer(item,'pointerout',h.outside);assert.equal(h.card,null);
  await act(()=>h.trigger.focus());assert.ok(h.card,'keyboard focus opens overview');
  await act(()=>h.card.querySelector('[role=listitem]').focus());assert.ok(h.card,'card receives keyboard focus');
  await act(()=>document.activeElement.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})));
  assert.equal(h.card,null);assert.equal(document.activeElement,h.trigger);assert.equal(h.trigger.getAttribute('aria-expanded'),'false','Escape focus return must not reopen');
  await act(()=>h.outside.focus());await h.pointer(h.trigger,'pointerover',null,'touch');assert.equal(h.card,null,'touch hover is not an opening gesture');
  await act(()=>h.trigger.click());assert.ok(h.card,'touch click opens');
  await h.pointer(h.trigger,'pointerout',h.outside);assert.ok(h.card,'clicked overview stays open while pointer leaves');
  await act(()=>h.trigger.click());assert.equal(h.card,null,'second click dismisses');
  await act(()=>h.trigger.focus());await act(()=>h.trigger.click());assert.ok(h.card);
  await act(()=>h.outside.focus());assert.equal(h.card,null,'Tab away dismisses even a click-pinned card');
  await act(()=>h.trigger.click());await h.pointer(h.outside,'pointerdown');assert.equal(h.card,null,'outside pointer dismisses');
 }finally{await h.close();}
});

test('open cell-count overview preserves unavailable and known-zero authority',async()=>{
 const h=await disclosureHarness();
 try{
  await h.render();await act(()=>h.trigger.focus());assert.ok(h.card);
  await h.render({cells:null,count:0});assert.match(h.card.textContent,/Types unavailable/);assert.doesNotMatch(h.card.textContent,/0 cells/);
  await h.render({cells:[],count:0});assert.match(h.card.textContent,/0 cells/);assert.doesNotMatch(h.card.textContent,/unavailable/);
  await h.render({cells:[],count:2});assert.match(h.card.textContent,/Types unavailable/);assert.doesNotMatch(h.card.textContent,/0 cells/);
 }finally{await h.close();}
});
