import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createOverviewCache} from './overviewCache.js';
import {useOverviewResource} from './useOverviewResource.js';

test('invalidating an unfinished root demand restarts it even when the hidden summary revision stays unchanged',async()=>{
 const cache=createOverviewCache(),oldFetch=globalThis.fetch,pending=[];let tree,current;
 globalThis.fetch=(path,options)=>new Promise(resolve=>pending.push({path,options,resolve}));
 function Probe(){current=useOverviewResource('/overview',0,{cache,scope:'project'});return null;}
 try{
  await act(()=>{tree=TestRenderer.create(React.createElement(Probe));});assert.equal(pending.length,1);
  await act(()=>cache.invalidate());assert.equal(pending[0].options.signal.aborted,true);assert.equal(pending.length,2);
  await act(()=>pending[1].resolve(new Response(JSON.stringify({counts:{epochs:12}}))));assert.equal(current.data.counts.epochs,12);assert.equal(current.loading,false);
  await act(()=>pending[0].resolve(new Response(JSON.stringify({counts:{epochs:1}}))));assert.equal(current.data.counts.epochs,12);
 }finally{await act(()=>tree?.unmount());cache.clear();globalThis.fetch=oldFetch;}
});

test('failed summary refresh preserves inert display separately from current data',async()=>{
 const cache=createOverviewCache(),oldFetch=globalThis.fetch;let tree,current,fail=false;
 globalThis.fetch=async()=>{if(fail)throw Error('offline');return new Response(JSON.stringify({counts:{epochs:12}}));};
 function Probe(){current=useOverviewResource('/overview',0,{cache,scope:'project'});return null;}
 try{
  await act(()=>{tree=TestRenderer.create(React.createElement(Probe));});assert.equal(current.data.counts.epochs,12);
  fail=true;await act(()=>cache.refresh(0));assert.equal(current.data,null);assert.equal(current.displayData.counts.epochs,12);assert.equal(current.error,'offline');
 }finally{await act(()=>tree?.unmount());cache.clear();globalThis.fetch=oldFetch;}
});

test('preparation is explicit, retries one read, and cancels on scope change',async()=>{
 const cache=createOverviewCache(),oldFetch=globalThis.fetch,requests=[];let tree,current,scope='a',held;
 const pending={status:'preparing',preparation:{status:'pending',resource:'overview'}};
 globalThis.fetch=async(path,options)=>{requests.push({path,options});if(path.endsWith('/prepare'))return new Promise(resolve=>{held=resolve;});return new Response(JSON.stringify(pending),{status:202});};
 function Probe(){current=useOverviewResource('/overview',0,{cache,scope});return null;}
 try{
  await act(()=>{tree=TestRenderer.create(React.createElement(Probe));});
  assert.equal(current.data,null);assert.equal(current.preparation.resource,'overview');assert.equal(requests.length,1);
  let work;await act(()=>{work=current.prepare();});assert.equal(requests.length,2);assert.equal(current.preparing,true);
  scope='b';await act(()=>tree.update(React.createElement(Probe)));assert.equal(requests[1].options.signal.aborted,true);
  await act(async()=>{held(new Response(JSON.stringify({status:'ready'})));await work;});
  assert.equal(requests.length,3);assert.equal(current.preparing,false);assert.equal(current.data,null);
  await act(()=>{work=current.prepare();});
  await act(async()=>{held(new Response(JSON.stringify({status:'ready'})));await work;});
  assert.equal(requests.length,5);assert.equal(current.preparation.status,'pending');assert.equal(current.preparing,false);
 }finally{await act(()=>tree?.unmount());cache.clear();globalThis.fetch=oldFetch;}
});
