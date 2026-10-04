import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {fileURLToPath} from 'node:url';
import {JSDOM} from 'jsdom';
import {createServer} from './test-support/isolatedVite.js';

// jsdom verifies ReactDOM attributes; native input suppression is exercised by
// the opt-in desktop/e2e/stable-content-inert.e2e.cjs Chrome regression.
test('retained content publishes inert through loading, error and blocked, then recovers',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 const globals={window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true};
 const previous=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error'});
 const view=createRoot(document.getElementById('root'));
 try{
  const {default:StableContent}=await server.ssrLoadModule('/src/components/StableContent.jsx');
  const render=async(props,label)=>act(async()=>view.render(React.createElement(StableContent,{scope:'same',data:{},...props},React.createElement('button',null,label))));
  await render({},'Committed');
  const retained=document.querySelector('button'),body=document.querySelector('.stable-content-body');
  assert.equal(body.hasAttribute('inert'),false);
  for(const state of [{loading:true},{error:'Failed'},{blocked:true}]){
   await render(state,'Uncommitted');
   assert.equal(document.querySelector('button'),retained,'old control stays mounted');
   assert.equal(retained.textContent,'Committed');
   assert.equal(body.hasAttribute('inert'),true,'ReactDOM must publish native inert while waiting');
   assert.equal(body.getAttribute('aria-hidden'),'true');
  }
  await render({},'Fresh');
  assert.equal(document.querySelector('button'),retained);
  assert.equal(retained.textContent,'Fresh');
  assert.equal(body.hasAttribute('inert'),false);
  assert.equal(body.hasAttribute('aria-hidden'),false);
 }finally{await act(async()=>view.unmount());await server.close();dom.window.close();for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}
});
