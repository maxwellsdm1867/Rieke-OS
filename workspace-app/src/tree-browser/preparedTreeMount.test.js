import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';
for(const name of ['ColumnTree','HierarchyTree'])test(`${name} prepares only on click and cancels stale preparation`,async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://fixture/'}),keys=['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const previous=Object.fromEntries(keys.map(k=>[k,globalThis[k]]));
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true,requestAnimationFrame:f=>setTimeout(f,0),cancelAnimationFrame:clearTimeout});
 const calls=[];let held;
 globalThis.fetch=async(url,options)=>{calls.push({url,options});if(url.endsWith('/prepare'))return new Promise(resolve=>held=resolve);return new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:'tree'}}),{status:202});};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:View}=await server.ssrLoadModule(`/src/tree-browser/ui/${name}.jsx`),root=createRoot(document.querySelector('main'));
 const render=protocolId=>act(async()=>root.render(React.createElement(View,{protocolId,projectId:'project',splits:'cell',browseOnly:true})));
 try{
  await render('a');assert.equal(calls.length,1);
  const button=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Prepare view'));assert.ok(button);
  await act(()=>button.click());assert.equal(calls.length,2);assert.match(document.body.textContent,/Preparing view/);
  assert.deepEqual(JSON.parse(calls[1].options.body),{protocol_uuid:'a',filters:{},splits:'cell'});
  await render('b');assert.equal(calls[1].options.signal.aborted,true);assert.equal(calls.length,3);
  await act(()=>held(new Response(JSON.stringify({status:'ready'}))));assert.equal(calls.length,3);
  await act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Prepare view')).click());
  await act(()=>held(new Response(JSON.stringify({status:'ready'}))));assert.equal(calls.length,5);
  assert.match(document.body.textContent,/Prepare view/);
 }finally{await act(()=>root.unmount());await server.close();dom.window.close();for(const[k,v]of Object.entries(previous)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
});
