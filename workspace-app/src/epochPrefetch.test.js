import test from 'node:test';
import assert from 'node:assert/strict';
import {createResourceCache,cachedResourceRequest,prefetchEpochTraces,prefetchTraceWindows,epochPrefetchPaths,initialEpochTracePath} from './resourceCache.js';
const metadata=uuid=>({epoch_uuid:uuid,streams:[{kind:'responses',uuid:`stream-${uuid}`,sample_count:40000}]});
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};

test('look-ahead chooses four following epochs and one preceding within the current page',()=>{
  const rows=Array.from({length:12},(_,i)=>({epoch_uuid:String(i)})),path=row=>`/epochs/${row.epoch_uuid}`;
  assert.deepEqual(epochPrefetchPaths(rows,4,path),['/epochs/5','/epochs/6','/epochs/7','/epochs/8','/epochs/3']);
  assert.deepEqual(epochPrefetchPaths(rows,11,path),['/epochs/10']);
  assert.deepEqual(epochPrefetchPaths(rows,-1,path),[]);
});

test('trace look-ahead is idle-delayed, capped at five epochs and one bounded read at a time',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const cache=createResourceCache(),calls=[];
  const request=(path,{signal})=>new Promise(resolve=>calls.push({path,signal,resolve}));
  const cancel=prefetchEpochTraces(Array.from({length:8},(_,i)=>`/epochs/${i}`),{request,cache});
  try{
    t.mock.timers.tick(179);await flush();assert.equal(calls.length,0);
    t.mock.timers.tick(1);await flush();assert.equal(calls.length,1);
    for(let i=0;i<5;i++){
      assert.equal(calls.length,i*2+1);assert.equal(calls.at(-1).path,`/epochs/${i}`);
      calls.at(-1).resolve(metadata(String(i)));await flush();
      assert.equal(calls.length,i*2+2);assert.equal(calls.at(-1).path,`/epochs/${i}/trace?stream_uuid=stream-${i}&start=0&count=20000`);
      await flush();assert.equal(calls.length,i*2+2,'next metadata waits until this trace settles');
      calls.at(-1).resolve({values:[i]});await flush();
    }
    assert.equal(calls.length,10);
  }finally{cancel();t.mock.timers.reset();}
});

test('invalidated look-ahead stops before trace/next epoch and cannot populate a new generation',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const cache=createResourceCache(),calls=[];
  const cancel=prefetchEpochTraces(['/epochs/a','/epochs/b'],{cache,delayMs:0,request:(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}))});
  try{
    t.mock.timers.tick(0);await flush();cache.invalidate();calls[0].resolve(metadata('a'));await flush();
    assert.equal(calls.length,1);assert.equal(cache.stats().entries,0);
  }finally{cancel();t.mock.timers.reset();}
});

test('speculation excludes candidate routes and does not follow mismatched metadata identities',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});const calls=[];
  const cancel=prefetchEpochTraces(['/protocols/p/workbench/candidates/c/epochs/a','/epochs/a'],{cache:createResourceCache(),delayMs:0,request:async path=>{calls.push(path);return metadata('wrong');}});
  try{t.mock.timers.tick(0);await flush();assert.deepEqual(calls,['/epochs/a']);}finally{cancel();t.mock.timers.reset();}
});

test('shared epoch requests isolate revision, generation, transport and cache; rejected reads retry',async()=>{
  const cache=createResourceCache(),calls=[];
  const request=(path,{signal})=>new Promise((resolve,reject)=>calls.push({path,signal,resolve,reject}));
  const first=cachedResourceRequest('/epochs/a',{cache,request}),joined=cachedResourceRequest('/epochs/a',{cache,request});
  const nextRevision=cachedResourceRequest('/epochs/a',{cache,request,revision:1});
  cache.invalidate();const nextGeneration=cachedResourceRequest('/epochs/a',{cache,request});
  const otherCache=cachedResourceRequest('/epochs/a',{cache:createResourceCache(),request});
  const otherTransport=cachedResourceRequest('/epochs/a',{cache,request:(...args)=>request(...args)});
  assert.equal(calls.length,5);calls.forEach((call,i)=>call.resolve({epoch_uuid:'a',value:i}));
  const values=await Promise.all([first,joined,nextRevision,nextGeneration,otherCache,otherTransport]);
  assert.equal(values[0],values[1]);assert.notEqual(values[0],values[3]);
  const failed=cachedResourceRequest('/epochs/error',{cache,request});calls.at(-1).reject(Error('unavailable'));await assert.rejects(failed,/unavailable/);
  const retry=cachedResourceRequest('/epochs/error',{cache,request});calls.at(-1).resolve(metadata('error'));await retry;
});

test('cancelling speculative ownership allows foreground takeover in the same effect turn',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});const cache=createResourceCache(),calls=[];
  const epoch=metadata('a'),tracePath=initialEpochTracePath(epoch);cache.put('/epochs/a',0,epoch);
  const request=(path,{signal})=>new Promise(resolve=>calls.push({path,signal,resolve}));
  const cancel=prefetchEpochTraces(['/epochs/a'],{cache,request,delayMs:0});
  try{
    t.mock.timers.tick(0);await flush();assert.equal(calls[0].path,tracePath);cancel();
    // Foreground first resolves its already-cached metadata, then joins the trace.
    await cachedResourceRequest('/epochs/a',{cache,request});
    const foreground=cachedResourceRequest(tracePath,{cache,request});
    t.mock.timers.tick(0);await flush();assert.equal(calls.length,1);assert.equal(calls[0].signal.aborted,false);
    const data={values:[1]};calls[0].resolve(data);assert.equal(await foreground,data);
  }finally{cancel();t.mock.timers.reset();}
});


test('trace-only speculation uses admitted locators without fetching metadata and obeys generation retirement',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const cache=createResourceCache(),calls=[];
 const paths=['/epochs/a','/protocols/p/workbench/candidates/c/epochs/a/trace',...Array.from({length:7},(_,i)=>initialEpochTracePath(metadata(String(i))))];
 const stop=prefetchTraceWindows(paths,{cache,delayMs:0,request:(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}))});
 try{t.mock.timers.tick(0);await flush();assert.equal(calls.length,1);assert.equal(calls[0].path,initialEpochTracePath(metadata('0')));calls[0].resolve({values:[1]});await flush();assert.equal(calls.length,2);cache.invalidate();calls[1].resolve({values:[2]});await flush();assert.equal(calls.length,2);assert.equal(cache.stats().entries,0);}finally{stop();t.mock.timers.reset();}
});

test('progressive warming visits the admitted page once, nearby first, with a finite frontier',()=>{
 const rows=Array.from({length:100},(_,i)=>i),path=x=>String(x);
 const selected=epochPrefetchPaths(rows,4,path,{progressive:true});
 assert.deepEqual(selected.slice(0,6),['5','6','7','8','3','9']);assert.equal(selected.length,60);assert.equal(new Set(selected).size,60);assert.ok(!selected.includes('4'));
 assert.deepEqual(epochPrefetchPaths(rows.slice(0,8),4,path,{progressive:true}),['5','6','7','3','2','1','0']);
});

test('progressive workers bound parallel reads and continue beyond the initial five',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const calls=[],cache=createResourceCache();
 const paths=Array.from({length:9},(_,i)=>initialEpochTracePath(metadata(String(i))));
 const stop=prefetchTraceWindows(paths,{cache,delayMs:0,progressive:true,concurrency:2,request:(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}))});
 try{t.mock.timers.tick(0);await flush();assert.equal(calls.length,2);
  for(let i=0;i<9;i++){assert.equal(calls.length,Math.min(9,i+2));calls[i].resolve({values:[i]});await flush();}
  assert.deepEqual(calls.map(x=>x.path),paths);assert.equal(cache.stats().entries,9);
 }finally{stop();t.mock.timers.reset();}
});

test('foreground cache misses pause queued warming; resumed warming reuses demand result',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const cache=createResourceCache(),calls=[];
 const paths=['a','b','c'].map(x=>initialEpochTracePath(metadata(x)));
 const request=(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}));
 const stop=prefetchTraceWindows(paths,{cache,request,delayMs:0,progressive:true});
 try{t.mock.timers.tick(0);await flush();assert.equal(calls.length,1);
  const foreground=cachedResourceRequest(paths[1],{request,cache});assert.equal(calls.length,2);
  calls[0].resolve({values:[0]});await flush();t.mock.timers.tick(8);await flush();assert.equal(calls.length,2,'no speculative dispatch while foreground pending');
  calls[1].resolve({values:[1]});await foreground;t.mock.timers.tick(8);await flush();assert.equal(calls.length,3);assert.equal(calls[2].path,paths[2]);calls[2].resolve({values:[2]});await flush();
 }finally{stop();t.mock.timers.reset();}
});

test('speculative capacity is reserved before dispatch and expiration restores headroom',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});let now=0;const cache=createResourceCache({bytes:2*1024*1024,entries:8,ttlMs:20,now:()=>now}),calls=[];
 cache.put('/epochs/selected',0,{values:'x'.repeat(350000)});
 const paths=['a','b'].map(x=>initialEpochTracePath(metadata(x)));
 const options={cache,delayMs:0,progressive:true,concurrency:4,request:async path=>{calls.push(path);return {values:[1]};}};
 const stop=prefetchTraceWindows(paths,options);
 try{t.mock.timers.tick(0);await flush();assert.equal(calls.length,0);assert.ok(cache.peek('/epochs/selected',0));
  now=21;const again=prefetchTraceWindows(paths,options);t.mock.timers.tick(0);await flush();assert.equal(calls.length,1,'only one reservation fits concurrently');t.mock.timers.tick(8);await flush();assert.equal(calls.length,2,'released capacity admits the waiting item');again();
 }finally{stop();t.mock.timers.reset();}
});

test('speculative hits do not displace demand recency; large results cannot evict demand',async()=>{
 const cache=createResourceCache({entries:4,bytes:4*1024*1024});
 cache.put('/epochs/a',0,{});cache.put('/epochs/b',0,{});cache.put('/epochs/c',0,{});cache.put('/epochs/d',0,{});
 await cachedResourceRequest('/epochs/a',{cache,speculative:true,request:()=>assert.fail('hit')});
 cache.put('/epochs/e',0,{});assert.equal(cache.peek('/epochs/a',0),undefined);assert.ok(cache.peek('/epochs/d',0));
 assert.equal(cache.put('/epochs/huge',0,{values:'x'.repeat(600000)},cache.token(),{speculative:true}),false);assert.ok(cache.peek('/epochs/d',0));
});

test('speculation refuses noninitial or oversized trace windows and cancels every parallel subscriber',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const cache=createResourceCache(),calls=[];
 const valid=['a','b','c','d'].map(x=>initialEpochTracePath(metadata(x)));
 const stop=prefetchTraceWindows([...valid,valid[0].replace('count=20000','count=20001'),valid[1].replace('start=0','start=1')],{cache,delayMs:0,progressive:true,concurrency:4,request:(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}))});
 try{t.mock.timers.tick(0);await flush();assert.equal(calls.length,4);stop();t.mock.timers.tick(0);assert.ok(calls.every(x=>x.signal.aborted));calls.forEach(x=>x.resolve({values:[1]}));await flush();assert.equal(calls.length,4);assert.equal(cache.stats().entries,0);}finally{stop();t.mock.timers.reset();}
});

test('annotation and page reads pause global speculation until all foreground reads settle',async t=>{
 const {createApiRequest}=await import('./api.js');const {epochResourceCache:cache}=await import('./resourceCache.js');
 t.mock.timers.enable({apis:['setTimeout']});cache.invalidate();const calls=[];
 const request=createApiRequest((path,options)=>new Promise(resolve=>calls.push({path,...options,resolve})));
 const paths=['a','b'].map(x=>initialEpochTracePath(metadata(x)));
 const stop=prefetchTraceWindows(paths,{request,cache,delayMs:0,progressive:true});
 try{t.mock.timers.tick(0);await flush();assert.equal(calls.length,1);assert.equal(cache.hasDemand(),false,'speculation is not foreground');
  const tags=request('/epochs/a/annotations'),page=request('/explore/epochs',{method:'POST',body:{limit:60}});
  calls[0].resolve({values:[1]});await flush();t.mock.timers.tick(8);await flush();assert.equal(calls.length,3);
  calls[1].resolve({annotations:[]});await tags;t.mock.timers.tick(8);await flush();assert.equal(calls.length,3,'page still holds foreground priority');
  calls[2].resolve({epochs:[]});await page;t.mock.timers.tick(8);await flush();assert.equal(calls.length,4);calls[3].resolve({values:[2]});await flush();assert.equal(cache.hasDemand(),false);
  await assert.rejects(createApiRequest(()=>{throw Error('transport');})('/epochs/a/annotations'),/transport/);assert.equal(cache.hasDemand(),false);
 }finally{stop();cache.invalidate();t.mock.timers.reset();}
});

test('new admitted pages replace unused speculation while retaining visited and protected windows',()=>{
 const cache=createResourceCache({bytes:3*1024*1024,entries:8});
 const data={values:'x'.repeat(320000)};
 for(const id of ['visited','old','current'])assert(cache.put(`/epochs/${id}`,0,data,cache.token(),{speculative:true}));
 cache.get('/epochs/visited',0);
 const release=cache.reservePrefetch(new Set(['/epochs/current']),0);assert.ok(release);
 assert.ok(cache.peek('/epochs/visited',0));assert.ok(cache.peek('/epochs/current',0));assert.equal(cache.peek('/epochs/old',0),undefined);release();
});

test('foreground takeover promotes a speculative result before a new page can evict it',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const cache=createResourceCache({bytes:2*1024*1024,entries:8}),calls=[];
 const path=initialEpochTracePath(metadata('a')),request=(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}));
 const stop=prefetchTraceWindows([path],{cache,request,delayMs:0});
 try{t.mock.timers.tick(0);await flush();const foreground=cachedResourceRequest(path,{request,cache});assert.equal(calls.length,1);
  calls[0].resolve({values:'x'.repeat(350000)});await foreground;await flush();
  assert.equal(cache.reservePrefetch(new Set(['/epochs/next']),0),null);assert.ok(cache.peek(path,0),'viewed trace survives speculative capacity pressure');
 }finally{stop();t.mock.timers.reset();}
});

test('live progressive warming protects earlier derived trace windows from its own later reads',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const cache=createResourceCache({bytes:3*1024*1024,entries:32}),calls=[];
 const stop=prefetchEpochTraces(['a','b','c','d'].map(x=>`/epochs/${x}`),{cache,delayMs:0,progressive:true,request:async path=>{calls.push(path);return path.includes('/trace?')?{values:'x'.repeat(320000)}:metadata(path.split('/')[2]);}});
 try{t.mock.timers.tick(0);for(let i=0;i<5;i++)await flush();assert.ok(cache.peek(initialEpochTracePath(metadata('a')),0));assert.ok(cache.peek(initialEpochTracePath(metadata('b')),0));assert.ok(cache.peek(initialEpochTracePath(metadata('c')),0));assert.ok(!calls.includes('/epochs/d'),'stop when protected working set fills speculative budget');}finally{stop();t.mock.timers.reset();}
});

test('Inspector progressive frontier keeps immediate neighbors but skips distant unrelated cells',()=>{
 const rows=Array.from({length:30},(_,i)=>({epoch_uuid:String(i),cell_uuid:i<10?'previous':i<20?'active':'next'}));
 assert.deepEqual(epochPrefetchPaths(rows,12,r=>r.epoch_uuid,{progressive:true,activeCellOnly:true}),['13','14','15','16','11','17','18','19','10']);
 assert.deepEqual(epochPrefetchPaths(rows,19,r=>r.epoch_uuid,{progressive:true,activeCellOnly:true}).slice(0,5),['20','21','22','23','18']);
});
