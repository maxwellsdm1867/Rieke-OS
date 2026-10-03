import test from 'node:test';
import assert from 'node:assert/strict';
import {createPageReadCache,searchReadDescriptor,pageReadKey,canonicalReadIdentity} from './pageReadCache.js';
const scope={projectUuid:'synthetic-project-a',activationId:'synthetic-activation-a',actorId:'synthetic-actor-a'};
const descriptor=(query='CellA',revision=0,context=scope)=>searchReadDescriptor(context,query,revision);
const response=(id='cell-a')=>({results:[{kind:'cell',id,label:`Synthetic ${id}`,detail:'fixture'}],total:1});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(options={}){const cache=createPageReadCache(options);cache.activate(scope);return cache;}

test('read identity normalizes object keys but preserves typed values, array order and exact scope',()=>{
 assert.equal(canonicalReadIdentity({a:1,b:null}),canonicalReadIdentity({b:null,a:1}));
 for(const [left,right] of [[1,'1'],[null,{}],[[1,2],[2,1]],[-0,0]])assert.notEqual(canonicalReadIdentity(left),canonicalReadIdentity(right));
 for(const invalid of [undefined,{a:undefined},NaN,[,1],new Date()])assert.throws(()=>canonicalReadIdentity(invalid));
 const first=descriptor();
 for(const patch of [{projectUuid:'other'},{activationId:'other'},{actorId:'other'}])assert.notEqual(pageReadKey(first),pageReadKey(descriptor('CellA',0,{...scope,...patch})));
 assert.notEqual(pageReadKey(first),pageReadKey(descriptor('CellA',1)));
 assert.notEqual(pageReadKey(descriptor('rate = 1')),pageReadKey(descriptor('rate = "1"')));
 assert.throws(()=>pageReadKey({...first,schemaVersion:0}));
});

test('only bounded GET search reads are allowlisted; no mutation or candidate fallback',async()=>{
 const cache=setup();let calls=0;const load=async()=>{calls++;return response();};
 for(const request of [{method:'POST',path:'/search?q=x&limit=20'}, {method:'GET',path:'/epochs/a'}, {method:'GET',path:'/protocols/p/workbench/candidates/c/epochs/a'}, {method:'GET',path:'/search?q=x&limit=200'}, {method:'GET',path:'/search?q=x&limit=20',body:{}}])await assert.rejects(cache.read({...descriptor(),request},{load}),/allowlisted|witnesses/);
 await assert.rejects(cache.read({...descriptor(),scope:{...scope,projectUuid:''}},{load}),/scope required/);
 assert.equal(calls,0);
});

test('fresh hits avoid reads, stale display revalidates, empty success replaces, expired entries prune',async()=>{
 let at=0,calls=0;const cache=setup({freshMs:30,retainMs:100,now:()=>at});
 const load=async()=>{calls++;return response();};
 await cache.read(descriptor(),{load});at=29;await cache.read(descriptor(),{load});assert.equal(calls,1);
 assert.equal(cache.peek(descriptor()).fresh,true);at=30;assert.equal(cache.peek(descriptor()).fresh,false);
 await cache.read(descriptor(),{load:async()=>{calls++;return {results:[],total:0};}});
 assert.deepEqual(cache.peek(descriptor()).data.results,[]);assert.equal(calls,2);
 at=130;assert.equal(cache.peek(descriptor()),undefined);assert.equal(cache.stats().entries,0);
});

test('retained snapshots are immutable, finite LRU and byte caps apply to envelopes and keys',async()=>{
 const cache=setup({entries:2,bytes:2000});const load=async path=>response(path);
 const first=await cache.read(descriptor('A'),{load});assert.ok(Object.isFrozen(first.results[0]));
 await cache.read(descriptor('B'),{load});await cache.read(descriptor('A'),{load});await cache.read(descriptor('C'),{load});
 assert.equal(cache.peek(descriptor('B')),undefined);assert.equal(cache.stats().entries,2);assert.ok(cache.stats().bytes<=2000);
 const tiny=setup({bytes:500});await tiny.read(descriptor(),{load:async()=>({results:[{kind:'cell',id:'a',label:'x'.repeat(2000)}],total:1})});
 assert.equal(tiny.stats().entries,0);assert.equal(tiny.stats().oversized,1);
 assert.throws(()=>createPageReadCache({bytes:Infinity}));
});

test('exact in-flight reads coalesce; one departing subscriber cannot cancel another',async()=>{
 const cache=setup(),held=deferred(),a=new AbortController(),b=new AbortController();let calls=0,signal;
 const load=async(_path,options)=>{calls++;signal=options.signal;return held.promise;};
 const first=cache.read(descriptor(),{load,signal:a.signal}),second=cache.read(descriptor(),{load,signal:b.signal});
 const cancelled=assert.rejects(first,{name:'AbortError'});await tick();a.abort();await cancelled;
 assert.equal(signal.aborted,false);held.resolve(response());assert.equal((await second).results[0].id,'cell-a');
 assert.equal(calls,1);assert.equal(cache.stats().coalesced,1);assert.equal(cache.stats().inflight,0);
});

test('last departure cancels and a transport ignoring abort cannot resurrect cached data',async()=>{
 const cache=setup(),held=deferred(),controller=new AbortController();let signal;
 const read=cache.read(descriptor(),{signal:controller.signal,load:async(_path,options)=>{signal=options.signal;return held.promise;}});
 const rejected=assert.rejects(read,{name:'AbortError'});await tick();controller.abort();await rejected;
 assert.equal(signal.aborted,true);held.resolve(response());await tick();assert.equal(cache.peek(descriptor()),undefined);
 assert.equal(cache.stats().inflight,0);
});

test('project or actor activation retirement rejects pending work even with matching entity labels',async()=>{
 const cache=setup(),held=deferred();const old=cache.read(descriptor(),{load:()=>held.promise});
 const rejected=assert.rejects(old,{name:'AbortError'});await tick();const next={...scope,actorId:'actor-b',activationId:'activation-b'};cache.activate(next);await rejected;
 held.resolve(response());await tick();assert.equal(cache.peek(descriptor()),undefined);
 await assert.rejects(cache.read(descriptor(),{load:async()=>response()}),{name:'AbortError'});
 await cache.read(descriptor('CellA',0,next),{load:async()=>response('cell-b')});
 assert.equal(cache.peek(descriptor('CellA',0,next)).data.results[0].id,'cell-b');cache.retire();assert.equal(cache.stats().entries,0);
});

test('errors never become successful empty pages; 409 revokes retained scope without retry',async()=>{
 const cache=setup();await cache.read(descriptor(),{load:async()=>response()});let calls=0;
 await assert.rejects(cache.read(descriptor(),{force:true,load:async()=>{calls++;throw Error('Offline');}}),/Offline/);
 assert.equal(cache.peek(descriptor()).data.results[0].id,'cell-a');
 await assert.rejects(cache.read(descriptor(),{force:true,load:async()=>{calls++;throw Object.assign(Error('Stale authority'),{status:409});}}),error=>error.status===409);
 assert.equal(calls,2);assert.equal(cache.stats().entries,0);
 await assert.rejects(cache.read(descriptor(),{load:async()=>({results:null,total:0})}),/Incomplete/);
 assert.equal(cache.stats().entries,0);
});

test('request path is captured before async work and in-flight ownership is finitely bounded',async()=>{
 const cache=setup({inflight:1}),held=deferred(),item=descriptor();let path;
 const read=cache.read(item,{load:async value=>{path=value;return held.promise;}});
 item.request.path='/annotations';await tick();assert.equal(path,'/search?q=CellA&limit=20');
 await assert.rejects(cache.read(descriptor('B'),{load:async()=>response()}),/limit reached/);
 held.resolve(response());await read;
 const stats=cache.stats();assert.equal(stats.inflight,0);assert.ok(!JSON.stringify(stats).includes('CellA'),'diagnostics contain no query or entity identifiers');
});

test('oversized successful replacement evicts its predecessor before reopen',async()=>{
 const cache=setup({bytes:1000});await cache.read(descriptor(),{load:async()=>response('A')});
 const oversized=await cache.read(descriptor(),{force:true,load:async()=>({results:[{kind:'cell',id:'B',label:'x'.repeat(2000)}],total:1})});
 assert.equal(oversized.results[0].id,'B');assert.equal(cache.peek(descriptor()),undefined);
 let reads=0;const reopened=await cache.read(descriptor(),{load:async()=>{reads++;return response('C');}});
 assert.equal(reads,1);assert.equal(reopened.results[0].id,'C');
});

test('abort-ignoring dispatched transports remain bounded across cancellation and activation',async()=>{
 const cache=setup({inflight:1}),held=deferred(),controller=new AbortController();let reads=0;
 const pending=cache.read(descriptor(),{signal:controller.signal,load:()=>{reads++;return held.promise;}});
 const cancelled=assert.rejects(pending,{name:'AbortError'});await tick();controller.abort();await cancelled;
 assert.equal(cache.stats().inflight,1);
 for(let index=0;index<3;index++){
   const next={...scope,activationId:`activation-${index}`};cache.activate(next);
   await assert.rejects(cache.read(descriptor('B',0,next),{load:async()=>{reads++;return response();}}),/limit reached/);
 }
 assert.equal(reads,1);held.resolve(response());await tick();assert.equal(cache.stats().inflight,0);assert.equal(cache.stats().entries,0);
});

test('typed negative zero is preserved in delivered and reused predicates',async()=>{
 const cache=setup();let calls=0;const load=async()=>{calls++;return {results:[{kind:'value',id:'v',label:'zero',predicate:{value:-0}}],total:1};};
 for(let index=0;index<2;index++){const data=await cache.read(descriptor('rate = -0'),{load});assert.ok(Object.is(data.results[0].predicate.value,-0));}
 assert.equal(calls,1);
});
