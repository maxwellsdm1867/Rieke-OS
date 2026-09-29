import test from 'node:test';
import assert from 'node:assert/strict';
import {createResourceCache,cachedResourceRequest,requestEpochWithTrace,initialEpochTracePath,prefetchEpochMetadata,cacheableEpochPath} from './resourceCache.js';
const path='/epochs/one?protocol_uuid=protocol-a';
const epoch={epoch_uuid:'one',streams:[{uuid:'stim',kind:'stimuli',sample_count:50},{uuid:'response',kind:'responses',sample_count:40000}]};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
test('cache uses exact URL scope and revision, expires, and evicts least-recently used responses',()=>{
  let at=0;const cache=createResourceCache({entries:2,bytes:10000,ttlMs:30,now:()=>at});
  cache.put(path,1,{value:1});cache.put('/epochs/two',1,{value:2});
  assert.equal(cache.get(path,2),undefined);assert.equal(cache.get('/epochs/one?protocol_uuid=other',1),undefined);
  assert.equal(cache.get(path,1).value,1);cache.put('/epochs/three',1,{value:3});
  assert.equal(cache.get('/epochs/two',1),undefined);at=30;assert.equal(cache.get(path,1),undefined);
});
test('bounded cache rejects oversized responses and non-epoch endpoints',()=>{
  const cache=createResourceCache({entries:64,bytes:60});
  assert.equal(cache.put('/epochs/one',0,{text:'x'.repeat(100)}),false);
  assert.equal(cache.put('/protocols/p/epochs',0,{value:1}),false);
  for(let i=0;i<50;i++)cache.put(`/epochs/${i}`,0,{value:i});
  assert.ok(cache.stats().bytes<=60);assert.ok(cache.stats().entries<50);
  assert.equal(cacheableEpochPath('/epochs/one/trace?start=0'),true);
  assert.equal(cacheableEpochPath('/epochs/one/curation'),false);
});
test('successful responses are reused, but revision changes fetch fresh data',async()=>{
  const cache=createResourceCache();let calls=0;
  const options={cache,revision:1,request:async()=>({value:++calls})};
  assert.equal((await cachedResourceRequest(path,options)).value,1);
  assert.equal((await cachedResourceRequest(path,options)).value,1);
  assert.equal((await cachedResourceRequest(path,{...options,revision:2})).value,2);
});
test('errors and cancelled completions never enter the cache',async()=>{
  const cache=createResourceCache(),controller=new AbortController();let finish;
  const pending=cachedResourceRequest(path,{cache,signal:controller.signal,request:()=>new Promise(resolve=>finish=resolve)});
  controller.abort();finish({value:'stale'});await assert.rejects(pending,{name:'AbortError'});
  assert.equal(cache.get(path,0),undefined);
  await assert.rejects(cachedResourceRequest(path,{cache,request:async()=>{throw Error('source changed');}}),/source changed/);
  assert.equal(cache.stats().entries,0);
});
test('reload invalidation clears related trace snapshots and prevents late pre-reload writes',async()=>{
  const cache=createResourceCache();let finish;
  cache.put(initialEpochTracePath(epoch),3,{values:[1]});cache.put(path,3,epoch);
  const pending=cachedResourceRequest('/epochs/one?protocol_uuid=other',{revision:3,cache,request:()=>new Promise(resolve=>finish=resolve)});
  cache.invalidate(path,{related:true});finish(epoch);await pending;
  assert.equal(cache.get(initialEpochTracePath(epoch),3),undefined);
  assert.equal(cache.get('/epochs/one?protocol_uuid=other',3),undefined);
  assert.equal(cache.get(path,3),undefined);
});
test('epoch publication waits for the exact first-response initial trace window and warms its cache',async()=>{
  const cache=createResourceCache(),calls=[];let finish,settled=false;
  const pending=requestEpochWithTrace(path,{cache,revision:9,request:async url=>{calls.push(url);return url===path?epoch:new Promise(resolve=>finish=resolve);}}).then(value=>{settled=true;return value;});
  await sleep(0);assert.equal(settled,false);assert.deepEqual(calls,[path,'/epochs/one/trace?stream_uuid=response&start=0&count=20000']);
  finish({epoch_uuid:'one',stream_uuid:'response',start:0,count:20000,values:[]});
  assert.equal(await pending,epoch);assert.ok(cache.get(calls[1],9));
  assert.equal(initialEpochTracePath({...epoch,streams:[{uuid:'short',kind:'responses',sample_count:7}]}),'/epochs/one/trace?stream_uuid=short&start=0&count=7');
});
test('a trace failure does not hide metadata; cancellation during warming prevents publication',async()=>{
  const cache=createResourceCache();
  assert.equal(await requestEpochWithTrace(path,{cache,request:async url=>{if(url===path)return epoch;throw Error('H5 missing');}}),epoch);
  assert.equal(cache.get(initialEpochTracePath(epoch),0),undefined);
  const controller=new AbortController();let finish;
  const pending=requestEpochWithTrace(path,{cache,signal:controller.signal,request:()=>new Promise(resolve=>finish=resolve)});
  await sleep(0);controller.abort();finish({values:[1]});await assert.rejects(pending,{name:'AbortError'});
});
test('adjacent prefetch is capped, metadata-only, sequential, and abortable before any I/O',async()=>{
  const calls=[],cache=createResourceCache();
  const cancel=prefetchEpochMetadata(['/epochs/one','/epochs/one','/epochs/two','/epochs/three',initialEpochTracePath(epoch)],{cache,delayMs:0,request:async url=>{calls.push(url);return {epoch_uuid:url};}});
  await sleep(15);cancel();assert.deepEqual(calls,['/epochs/one','/epochs/two']);
  const stop=prefetchEpochMetadata(['/epochs/four'],{cache,delayMs:5,request:async()=>assert.fail('cancelled prefetch must not fetch')});stop();await sleep(10);
});
