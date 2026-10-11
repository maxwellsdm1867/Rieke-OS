import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

async function mountUnavailable({launcher=true}={}){
 const message='Project folders could not be read. Check folder access or reconnect the drive, then retry.';
 const bootstrap={projects:[],launcher,current_project_uuid:launcher?null:'owned-project',managed_root:'/owned',inventory_unavailable:true,inventory_error:message,...(!launcher?{project_data:{status:'unloaded'}}:{})};
 const dom=new JSDOM(`<html><head><script id="rieke-projects-bootstrap" type="application/json">${JSON.stringify(bootstrap)}</script></head><body></body></html>`,{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
 const values={window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,Event:dom.window.Event,requestAnimationFrame:dom.window.requestAnimationFrame.bind(dom.window),cancelAnimationFrame:dom.window.cancelAnimationFrame.bind(dom.window)};
 const old=Object.fromEntries(Object.keys(values).concat('fetch').map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(values))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 dom.window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});
 dom.window.riekeDesktop={loadDraft:async()=>null,saveDraft:async()=>{},startupSession:async()=>null,status:async()=>({state:'Current'}),onStatus:()=>()=>{}};
 const requests=[];let recover=false,renderer;
 globalThis.fetch=async(url,options={})=>{
  const path=String(url).replace(/^\/api/,'');requests.push({path,method:options.method||'GET'});
  if(path==='/projects')return new Response(JSON.stringify(recover?{projects:[{uuid:'owned-project',path:'/owned/study',name:'Owned study',available:true,current:false}],launcher:true,current_project_uuid:null,managed_root:'/owned'}:{error:message,code:'project_inventory_unavailable'}),{status:recover?200:503});
  if(path==='/app/appearance')return new Response(JSON.stringify({theme:'light',icon:'disco'}));
  return new Response(JSON.stringify({error:`Unexpected test request ${path}`} ),{status:500});
 };
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 try{
  const {default:App}=await server.ssrLoadModule('/src/App.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(App));});
 }catch(error){await server.close();dom.window.close();for(const [key,value] of Object.entries(old)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key];}throw error;}
 return {requests,get root(){return renderer.root;},text:()=>JSON.stringify(renderer.toJSON()),recover(){recover=true;},async close(){await act(async()=>renderer.unmount());await server.close();dom.window.close();for(const [key,value] of Object.entries(old)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key];}}};
}

test('unavailable inventory keeps the actual desktop chooser usable and retries without inventing an empty catalog',async()=>{
 const h=await mountUnavailable();
 try{
  assert.match(h.text(),/Your projects/);assert.match(h.text(),/folder access/);
  assert.doesNotMatch(h.text(),/No projects yet|Restoring your last view/);
  const retry=h.root.findAllByType('button').find(node=>node.children.includes('Retry project list'));
  assert.ok(retry);assert.equal(retry.props.disabled,false);
  h.recover();await act(async()=>retry.props.onClick());
  assert.match(h.text(),/Owned study/);assert.doesNotMatch(h.text(),/folder access|Retry project list/);
  assert.equal(h.requests.filter(request=>request.path==='/projects').length,2);
  assert.equal(h.requests.some(request=>request.path==='/project/activate'||request.path==='/overview'),false);
 }finally{await h.close();}
});

test('an unavailable project-shell inventory never activates scientific data from its fallback identity',async()=>{
 const h=await mountUnavailable({launcher:false});
 try{
  assert.match(h.text(),/Project list unavailable/);
  assert.equal(h.requests.some(request=>request.path==='/project/activate'||request.path==='/overview'),false);
 }finally{await h.close();}
});
