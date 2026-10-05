import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {act,create} from 'react-test-renderer';
import useProtocolTreeLayout from './useProtocolTreeLayout.js';
import {beginProjectUnmount} from '../desktopLifecycle.js';

const turn=()=>new Promise(resolve=>setImmediate(resolve));
// Real hook, saver, API serialization and write tracking. Fetch deliberately can
// resolve after abort, so cancellation and mounted-publication fences are distinct.
function fixture(){
 const previousFetch=globalThis.fetch,requests=[];let root,visible;
 globalThis.fetch=(url,options)=>new Promise(resolve=>{
  const request={url,options,body:options.body===undefined?undefined:JSON.parse(options.body),settled:false,
   reply(data,ok=true){assert.equal(request.settled,false);request.settled=true;resolve({ok,status:ok?200:503,json:async()=>data});}};
  requests.push(request);
 });
 function Probe({id,initial}){visible=useProtocolTreeLayout(id,initial);return React.createElement('output',null,JSON.stringify(visible.order));}
 return {
  requests,get state(){return visible;},
  async render(id='a',initial){await act(async()=>{const element=React.createElement(Probe,{id,initial});if(root)root.update(element);else root=create(element);});},
  async reply(index,data,ok=true){await act(async()=>{requests[index].reply(data,ok);await turn();});},
  async call(action){let result;await act(async()=>{result=action(visible);await turn();});return result;},
  async unmount(){if(root){await act(async()=>root.unmount());root=null;}},
  async close(){try{
   if(root){await act(async()=>root.unmount());root=null;}
   // Drain accepted API writes even if an assertion failed mid-flight. Subsequent
   // coalesced writes receive their exact receipt, without touching hook internals.
   for(let attempt=0;attempt<10;attempt++){
    await act(async()=>{for(const request of requests.filter(item=>!item.settled))request.reply(request.body?{version:request.body.expected_version+1,split_order:request.body.split_order}:{version:1,split_order:['date']});await turn();});
    if(requests.every(item=>item.settled))break;
   }
   assert.ok(requests.every(item=>item.settled),'all controlled requests settled');
   const release=beginProjectUnmount();release(); // no accepted writes leaked
  }finally{globalThis.fetch=previousFetch;}}
 };
}

test('layout hook reports pending and invalid loads, then reloads a valid saved order',async()=>{
 const h=fixture();try{
  await h.render();assert.equal(h.state.ready,false);assert.equal(h.state.error,null);
  assert.deepEqual(h.state.order,['date','cell','block']);
  assert.equal(h.requests[0].url,'/api/protocols/a/tree-layout');
  await h.reply(0,{version:'1',split_order:['cell']});
  assert.equal(h.state.ready,false);assert.equal(h.state.error,'Invalid saved tree layout.');
  await h.call(state=>state.reload());assert.equal(h.requests[0].options.signal.aborted,true);
  assert.equal(h.state.error,null);assert.equal(h.state.ready,false);
  await h.reply(1,{error:'Offline'},false);assert.equal(h.state.error,'Offline');
  await h.call(state=>state.reload());
  await h.reply(2,{version:4,split_order:['block','cell']});
  assert.equal(h.state.ready,true);assert.equal(h.state.error,null);
  assert.deepEqual(h.state.order,['block','cell']);assert.deepEqual(h.state.save,{status:'saved',version:4});
 }finally{await h.close();}
});

test('layout hook retains mount-scoped string or array initial order across prop and protocol changes',async()=>{
 for(const initial of [' cell, ,date ',['cell','date']]){
  const h=fixture();try{
   await h.render('a',initial);await h.reply(0,{version:2,split_order:['block']});
   assert.deepEqual(h.state.order,['cell','date']);
   await h.render('a',['block']);assert.equal(h.requests.length,1);
   await h.render('b',['block']);assert.equal(h.state.ready,false);
   await h.reply(1,{version:8,split_order:['date']});
   assert.deepEqual(h.state.order,['cell','date']);assert.equal(h.state.save.version,8);
  }finally{await h.close();}
 }
});

test('layout hook aborts switched loads and ignores late success or failure even when fetch resolves after abort',async()=>{
 const h=fixture();try{
  await h.render('a');await h.render('b');
  assert.equal(h.requests[0].options.signal.aborted,true);
  await h.reply(1,{version:5,split_order:['cell']});
  await h.reply(0,{version:90,split_order:['obsolete']});
  assert.deepEqual(h.state.order,['cell']);assert.equal(h.state.save.version,5);assert.equal(h.state.ready,true);
  await h.render('c');await h.render('d');
  await h.reply(3,{version:6,split_order:['block']});
  await h.reply(2,{error:'obsolete failure'},false);
  assert.equal(h.state.ready,true);assert.equal(h.state.error,null);assert.deepEqual(h.state.order,['block']);
  await h.render('e');await h.unmount();assert.equal(h.requests[4].options.signal.aborted,true);
  await h.reply(4,{version:7,split_order:['unmounted']});
 }finally{await h.close();}
});

test('layout hook publishes local edits immediately and serializes coalesced writes with acknowledged versions',async()=>{
 const h=fixture();try{
  await h.render();await h.reply(0,{version:3,split_order:['date']});
  assert.equal(await h.call(state=>state.remember(['cell'])),undefined);
  assert.deepEqual(h.state.order,['cell']);assert.equal(h.state.save.status,'saving');
  assert.equal(h.requests[1].options.method,'PUT');assert.deepEqual(h.requests[1].body,{split_order:['cell'],expected_version:3});
  await h.call(state=>state.remember(['block','cell']));assert.equal(h.requests.length,2);
  await h.reply(1,{version:4,split_order:['cell']});
  assert.deepEqual(h.requests[2].body,{split_order:['block','cell'],expected_version:4});
  await h.reply(2,{version:5,split_order:['block','cell']});
  assert.deepEqual(h.state.save,{status:'saved',version:5});
  await h.call(state=>state.remember(['block','cell']));assert.equal(h.requests.length,3);
 }finally{await h.close();}
});

test('layout hook retries failed or mismatched writes without advancing version or losing desired order',async()=>{
 for(const failed of [{data:{error:'Offline'},ok:false,message:'Offline'},
  {data:{version:9,split_order:['cell']},message:'Tree save returned an invalid receipt. Reload before retrying.'},
  {data:{version:1,split_order:['wrong']},message:'Tree save returned an invalid receipt. Reload before retrying.'}]){
  const h=fixture();try{
   await h.render();await h.reply(0,{version:0,split_order:['date']});
   await h.call(state=>state.remember(['cell']));await h.reply(1,failed.data,failed.ok??true);
   assert.deepEqual(h.state.save,{status:'error',version:0,error:failed.message});assert.deepEqual(h.state.order,['cell']);
   // Do not await retry while its controlled network response is still pending.
   await h.call(state=>{state.retrySave();});
   assert.deepEqual(h.requests[2].body,{split_order:['cell'],expected_version:0});
   await h.reply(2,{version:1,split_order:['cell']});assert.deepEqual(h.state.save,{status:'saved',version:1});
  }finally{await h.close();}
 }
});

test('layout hook retains old saver while replacement load is pending but fences its save publication',async()=>{
 const h=fixture();try{
  await h.render('a');await h.reply(0,{version:2,split_order:['date']});
  await h.render('b');assert.equal(h.state.ready,false);
  await h.call(state=>state.remember(['cell']));
  assert.deepEqual(h.state.order,['cell']);assert.equal(h.requests.length,3,'retained saver submits the edit while replacement load is pending');
  assert.equal(h.requests[2].url,'/api/protocols/a/tree-layout');
  assert.deepEqual(h.requests[2].body,{split_order:['cell'],expected_version:2});
  await h.reply(1,{version:8,split_order:['block']});
  await h.reply(2,{version:3,split_order:['cell']});
  assert.deepEqual(h.state.order,['block']);assert.deepEqual(h.state.save,{status:'saved',version:8});
  await h.call(state=>state.remember(['date']));assert.equal(h.requests[3].url,'/api/protocols/b/tree-layout');
  assert.deepEqual(h.requests[3].body,{split_order:['date'],expected_version:8});
  await h.reply(3,{version:9,split_order:['date']});
 }finally{await h.close();}
});
