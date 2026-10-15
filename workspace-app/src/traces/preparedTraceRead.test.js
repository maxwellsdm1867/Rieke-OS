import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useEffect,useLayoutEffect} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {usePreparedTraceRead} from './usePreparedTraceRead.js';

async function harness(){
 const requests=[],events=[];let renderer,current;
 const port=name=>({identity:name,request:(path,{signal})=>{events.push('request:'+path);return new Promise((resolve,reject)=>requests.push({path,signal,resolve,reject,name}));}});
 const owner=port('one');
 function Probe({path='/a',revision='captured-one',requestPort=owner}){
  current=usePreparedTraceRead(path,revision,requestPort);
  useLayoutEffect(()=>{events.push('following-layout:'+path);},[path,revision,requestPort]);
  useEffect(()=>{events.push('passive:'+path);},[path,revision,requestPort]);
  return null;
 }
 return {requests,events,owner,port,get current(){return current;},async render(props={}){await act(async()=>{const node=React.createElement(React.Activity,{mode:props.hidden?'hidden':'visible'},React.createElement(Probe,props));if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);});},async close(){await act(async()=>renderer?.unmount());}};
}
test('prepared read dispatches immediately before following layout and passive work without loading-state render',async()=>{
 const h=await harness();try{await h.render();assert.deepEqual(h.events,['request:/a','following-layout:/a','passive:/a']);assert.equal(h.current.loading,true);await act(async()=>h.requests[0].resolve({exact:'a'}));assert.deepEqual(h.current.data,{exact:'a'});assert.equal(h.current.loading,false);assert.equal(h.requests.length,1);}finally{await h.close();}
});
test('rapid A to B to A cancels each retired lifetime and rejects wrong late completions',async()=>{
 const h=await harness();try{
  await h.render();await h.render({path:'/b'});await h.render({path:'/a'});
  assert.deepEqual(h.requests.map(r=>r.path),['/a','/b','/a']);assert(h.requests[0].signal.aborted);assert(h.requests[1].signal.aborted);assert.equal(h.requests[2].signal.aborted,false);
  await act(async()=>{h.requests[0].resolve({stale:'first-a'});h.requests[1].resolve({stale:'b'});});assert.equal(h.current.data,null);assert.equal(h.current.loading,true);
  await act(async()=>h.requests[2].resolve({exact:'last-a'}));assert.deepEqual(h.current.data,{exact:'last-a'});
 }finally{await h.close();assert(h.requests[2].signal.aborted);}
});
test('reload nonce and owner session replacement fence identical paths and revisions',async()=>{
 const h=await harness();try{
  await h.render();await act(async()=>h.requests[0].resolve({exact:'initial'}));
  await act(async()=>h.current.reload());assert.equal(h.current.data,null);assert.equal(h.current.loading,true);assert(h.requests[0].signal.aborted);
  const next=h.port('two');await h.render({requestPort:next});assert(h.requests[1].signal.aborted);assert.equal(h.current.data,null);
  await act(async()=>h.requests[1].resolve({stale:'reload-old-owner'}));assert.equal(h.current.data,null);
  await act(async()=>h.requests[2].resolve({exact:'new-owner'}));assert.deepEqual(h.current.data,{exact:'new-owner'});
  await h.render({requestPort:next,revision:'captured-two'});assert.equal(h.current.data,null);assert(h.requests[2].signal.aborted);
  await act(async()=>h.requests[3].reject(Error('Current read failed')));assert.equal(h.current.error,'Current read failed');
  await act(async()=>h.current.reload());assert.equal(h.current.error,null);await act(async()=>h.requests[4].resolve({exact:'retry'}));assert.deepEqual(h.current.data,{exact:'retry'});
 }finally{await h.close();}
});
test('disabled prepared path aborts and discards data; missing owner fails closed',async()=>{
 const h=await harness();try{await h.render();await h.render({path:null});assert(h.requests[0].signal.aborted);await act(async()=>h.requests[0].resolve({stale:true}));assert.equal(h.current.data,null);assert.equal(h.current.loading,false);await h.render({requestPort:{}});assert.equal(h.current.loading,false);assert.match(h.current.error,/authority is unavailable/);assert.equal(h.requests.length,1);}finally{await h.close();}
});


test('completed success and error cannot resurrect when A returns after a pending B',async()=>{
 for(const outcome of ['success','error']){
  const h=await harness();try{
   await h.render();await act(async()=>outcome==='success'?h.requests[0].resolve({stale:'completed-a'}):h.requests[0].reject(Error('Old A error')));
   assert.equal(h.current.loading,false);await h.render({path:'/b'});await h.render({path:'/a'});
   assert.equal(h.current.data,null);assert.equal(h.current.error,null);assert.equal(h.current.loading,true);
   await act(async()=>h.requests[1].resolve({stale:'late-b'}));assert.equal(h.current.loading,true);
   await act(async()=>h.requests[2].resolve({exact:'new-a'}));assert.deepEqual(h.current.data,{exact:'new-a'});
  }finally{await h.close();}
 }
});
test('Activity hide and reconnect retire completed samples before the replacement read',async()=>{
 const h=await harness();try{
  await h.render();await act(async()=>h.requests[0].resolve({stale:'before-hide'}));assert.equal(h.current.loading,false);
  await h.render({hidden:true});assert.equal(h.requests[0].signal.aborted,true);
  await h.render();assert.equal(h.requests.length,2);assert.equal(h.current.loading,true);assert.equal(h.current.data,null);
  await act(async()=>h.requests[1].resolve({exact:'after-reconnect'}));assert.deepEqual(h.current.data,{exact:'after-reconnect'});
 }finally{await h.close();}
});
