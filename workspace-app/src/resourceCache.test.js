import test from 'node:test';
import assert from 'node:assert/strict';
import {createResourceCache,cachedResourceRequest,requestEpochWithTrace,initialEpochTracePath,peekEpochWithTrace,prefetchEpochMetadata,cacheableEpochPath} from './resourceCache.js';
const path='/epochs/one?protocol_uuid=protocol-a';
const epoch={epoch_uuid:'one',streams:[{uuid:'stim',kind:'stimuli',sample_count:50},{uuid:'response',kind:'responses',sample_count:40000}]};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const initialTrace=(metadata=epoch)=>({epoch_uuid:metadata.epoch_uuid,stream_uuid:metadata.streams.find(stream=>stream.kind==='responses'&&stream.sample_count>0).uuid,start:0,count:Math.min(20000,metadata.streams.find(stream=>stream.kind==='responses'&&stream.sample_count>0).sample_count),sample_rate:10000,values:Array(Math.min(20000,metadata.streams.find(stream=>stream.kind==='responses'&&stream.sample_count>0).sample_count)).fill(null)});
test('complete warm peek requires exact global metadata URL, revision and matching initial trace',()=>{
 const cache=createResourceCache();cache.put(path,7,epoch);
 assert.equal(peekEpochWithTrace(path,7,cache),undefined,'metadata-only prefetch is not complete');
 cache.put(initialEpochTracePath(epoch),7,initialTrace());
 assert.equal(peekEpochWithTrace(path,7,cache),epoch);
 for(const [url,revision] of [[path,8],['/epochs/one',7],['/epochs/one?protocol_uuid=other',7],[initialEpochTracePath(epoch),7],['/protocols/p/workbench/candidates/r/epochs/one?candidate_scope_revision=token',7]])assert.equal(peekEpochWithTrace(url,revision,cache),undefined);
 cache.put(path,8,epoch);assert.equal(peekEpochWithTrace(path,8,cache),undefined,'trace revision must match metadata revision');
});
test('warm peek rejects malformed metadata and every mismatched or incomplete trace identity',()=>{
 const cache=createResourceCache();const trace=initialTrace();cache.put(path,7,epoch);
 for(const change of [{epoch_uuid:'other'},{stream_uuid:'stim'},{start:1},{count:7},{sample_rate:0},{sample_rate:Infinity},{sample_rate:'10000'},{values:[]},{values:{length:20000}}]){
  cache.put(initialEpochTracePath(epoch),7,{...trace,...change});assert.equal(peekEpochWithTrace(path,7,cache),undefined,JSON.stringify(change));
 }
 cache.put(initialEpochTracePath(epoch),7,trace);
 for(const change of [{epoch_uuid:'other'},{streams:null},{streams:[null]},{streams:[{kind:'responses',uuid:'response',sample_count:'40000'}]},{streams:[{kind:'responses',sample_count:40000}]}]){
  cache.put(path,7,{...epoch,...change});assert.equal(peekEpochWithTrace(path,7,cache),undefined);
 }
 assert.equal(peekEpochWithTrace('/epochs/%ZZ',7,cache),undefined);
});
test('warm peek expires either member independently and reload invalidates the complete pair',()=>{
 let at=0;const cache=createResourceCache({ttlMs:30,now:()=>at});const tracePath=initialEpochTracePath(epoch);
 cache.put(tracePath,7,initialTrace());at=10;cache.put(path,7,epoch);assert.equal(peekEpochWithTrace(path,7,cache),epoch);
 at=30;assert.equal(peekEpochWithTrace(path,7,cache),undefined,'expired trace cannot complete fresh metadata');
 cache.put(tracePath,7,initialTrace());at=40;assert.equal(peekEpochWithTrace(path,7,cache),undefined,'expired metadata cannot use fresh trace');
 cache.put(path,7,epoch);assert.equal(peekEpochWithTrace(path,7,cache),epoch);
 cache.invalidate(path,{related:true});assert.equal(peekEpochWithTrace(path,7,cache),undefined);assert.equal(cache.peek(tracePath,7),undefined);
});
test('warm peek uses the first response and bounded count, while indexed-empty epochs need no trace',()=>{
 const cache=createResourceCache();const short={epoch_uuid:'one',streams:[{kind:'responses',uuid:'short',sample_count:7},{kind:'responses',uuid:'other',sample_count:10}]};
 cache.put(path,0,short);cache.put(initialEpochTracePath(short),0,initialTrace(short));assert.equal(peekEpochWithTrace(path,0,cache),short);
 for(const streams of [[],[{kind:'responses',uuid:'empty',sample_count:0}],[{kind:'stimuli',uuid:'stim',sample_count:5}]]){
  const empty={epoch_uuid:'one',streams};cache.put(path,0,empty);assert.equal(peekEpochWithTrace(path,0,cache),empty);
 }
});
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

test('candidate detail does not prewarm through global trace authority or consume a warmed global trace',async()=>{
 const cache=createResourceCache(),calls=[];
 cache.put(initialEpochTracePath(epoch),4,{epoch_uuid:'one',values:['global snapshot']});
 const root='/protocols/p/workbench/candidates/r';
 const candidatePath=`${root}/epochs/one?candidate_scope_revision=exact-token`;
 const result=await requestEpochWithTrace(candidatePath,{cache,revision:4,request:async url=>{calls.push(url);assert.equal(url,candidatePath);return {...epoch,candidate_scope_revision:'exact-token'};}});
 assert.equal(result.candidate_scope_revision,'exact-token');assert.deepEqual(calls,[candidatePath]);
 assert.equal(cache.get(candidatePath,4),undefined,'Candidate reads are uncached until scoped caching is certified');
 assert.equal(cache.get(initialEpochTracePath(epoch),4).values[0],'global snapshot');
});
test('candidate token changes request exact metadata again without global prewarming',async()=>{
 const cache=createResourceCache(),calls=[];
 for(const token of ['first','second']){
  const url=`/protocols/p/workbench/candidates/r/epochs/one?candidate_scope_revision=${token}`;
  await requestEpochWithTrace(url,{cache,request:async path=>{calls.push(path);return epoch;}});
 }
 assert.deepEqual(calls,['/protocols/p/workbench/candidates/r/epochs/one?candidate_scope_revision=first','/protocols/p/workbench/candidates/r/epochs/one?candidate_scope_revision=second']);
 assert.equal(cache.stats().entries,0);
});
