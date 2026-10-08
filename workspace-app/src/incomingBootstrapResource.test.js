import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('initial read offer is effect-owned, StrictMode safe, and retires on reload, pause, A-B-A and custom owners',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {useResource}=await server.ssrLoadModule('/src/api.js');
 const previous=globalThis.fetch,calls=[];let current,renderer;const renders=[];
 globalThis.fetch=async(path)=>{calls.push(path);return new Response(JSON.stringify({kind:'network',path}),{status:200});};
 function Probe({path='/epochs',revision=1,paused=false,initialRead,requestPort,cache=false}){current=useResource(path,revision,0,{paused,initialRead,requestPort,cache});renders.push({...current});return null;}
 const render=async props=>act(async()=>{const element=React.createElement(React.StrictMode,null,React.createElement(Probe,props));if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});
 const unmount=async()=>{await act(async()=>renderer.unmount());renderer=null;};
 const offer=()=>{let claimed=null;return {claim({consumer}){if(claimed&&claimed!==consumer)return undefined;claimed=consumer;return {kind:'offer'};}};};
 try{
  await render({});assert.equal(current.data.kind,'network','ordinary requests without an offer retain their behavior');await unmount();calls.length=0;
  const initialRead=offer();await render({initialRead});assert.equal(current.data.kind,'offer');assert.equal(calls.length,0);
  await act(async()=>current.reload());assert.equal(current.data.kind,'network');assert.equal(calls.length,1);await unmount();
  await render({initialRead});assert.equal(current.data.kind,'network','true remount cannot reuse a consumed offer');await unmount();
  for(const transition of [{path:'/other'},{revision:2},{paused:true}]){
   const initialRead=offer();await render({initialRead});assert.equal(current.data.kind,'offer');
   await render({initialRead,...transition});if(transition.paused)assert.equal(current.loading,true);
   const beforeResume=renders.length;await render({initialRead});
   assert.equal(renders[beforeResume].data,null,'retired page stays hidden on the first resumed render');
   assert.equal(renders[beforeResume].loading,true);assert.equal(current.data.kind,'network');await unmount();
  }
  const reused=offer();await render({initialRead:reused});const beforeRetirement=renders.length;await render({});
  assert.equal(renders[beforeRetirement].data,null,'offer retirement hides prior data before passive effects');
  assert.equal(renders[beforeRetirement].loading,true);await render({initialRead:reused});
  assert.equal(current.data.kind,'network','offer A to absent to A cannot resurrect freshness');await unmount();
  const cachedOffer=offer();await render({initialRead:cachedOffer});const beforeCache=renders.length;await render({initialRead:cachedOffer,cache:true});
  assert.equal(renders[beforeCache].data,null);assert.equal(current.data.kind,'network');await unmount();
  let transport=0;
  await render({initialRead:offer(),requestPort:{request:async()=>{transport++;return {kind:'custom'};}}});
  assert.equal(current.data.kind,'custom');assert.equal(transport,1);await unmount();
 }finally{if(renderer)await unmount();globalThis.fetch=previous;await server.close();}
});
