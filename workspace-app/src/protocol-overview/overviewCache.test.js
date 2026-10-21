import test from 'node:test';
import assert from 'node:assert/strict';
import {createOverviewCache} from './overviewCache.js';
const descriptor=(path='/protocols/a/overview',revision=0,scope='project:actor')=>({path,revision,scope});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {resolve,reject,promise};};

test('project and all protocol overview returns reuse snapshots without another request',async()=>{
 const cache=createOverviewCache();let calls=0;
 const request=async path=>{calls++;return {path,count:96};};
 for(const path of ['/overview','/protocols/ordinary/overview','/protocols/pinned/overview','/protocols/typing/overview'])await cache.read(descriptor(path),{request});
 for(const path of ['/overview','/protocols/ordinary/overview','/protocols/pinned/overview','/protocols/typing/overview']){
  assert.equal(cache.peek(descriptor(path)).data.count,96);
  await cache.read(descriptor(path),{request});
 }
 assert.equal(calls,4);
});

test('changes refresh only visited pages in the background and foreground shares that request',async()=>{
 const cache=createOverviewCache(),pending=deferred();let calls=0;
 const request=async(path,options)=>{calls++;return calls===1?{count:96}:pending.promise;};
 await cache.read(descriptor(),{request});
 const refresh=cache.refresh(1);await Promise.resolve();
 assert.equal(cache.peek(descriptor()).data.count,96);
 assert.equal(cache.peek(descriptor()).loading,true);
 const foreground=cache.read(descriptor(undefined,1),{request});
 pending.resolve({count:100});await refresh;await foreground;
 assert.equal(calls,2);assert.equal(cache.peek(descriptor()).data.count,100);
 assert.equal(cache.peek(descriptor()).loading,false);
});

test('freshness revalidation sends the prior ETag but normal navigation makes no request',async()=>{
 const cache=createOverviewCache();let calls=0;
 const value={count:96};
 const request=async(path,options)=>{
  calls++;options.onResponse({headers:{get:()=> '"same"'}});
  if(calls===2){assert.equal(options.headers['If-None-Match'],'"same"');assert.equal(options.notModified,value);}
  return value;
 };
 await cache.read(descriptor(),{request});await cache.read(descriptor(),{request});assert.equal(calls,1);
 await cache.refresh(0);assert.equal(calls,2);assert.equal(cache.peek(descriptor()).data,value);
});

test('project/actor namespaces and newer invalidations reject late transport completions',async()=>{
 const cache=createOverviewCache(),old=deferred();let count=0;
 const request=async()=>++count===1?old.promise:{count:100};
 const first=cache.read(descriptor(),{request});await Promise.resolve();
 await cache.refresh(1);old.resolve({count:1});await first;
 assert.equal(cache.peek(descriptor()).data.count,100);
 assert.equal(cache.peek(descriptor(undefined,1,'other-project')),null);
});

test('failure removes cached authority and retry obtains a new response',async()=>{
 const cache=createOverviewCache();let fail=false;
 const request=async()=>{if(fail)throw Error('Unavailable');return {count:96};};
 await cache.read(descriptor(),{request});fail=true;await cache.refresh(1);
 assert.equal(cache.peek(descriptor()).data,null);assert.equal(cache.peek(descriptor()).error,'Unavailable');
 fail=false;await cache.read(descriptor(undefined,1),{request,force:true});assert.equal(cache.peek(descriptor()).data.count,96);
});

test('bounded retention evicts hidden entries while retaining visible consumers',async()=>{
 const cache=createOverviewCache({maxEntries:2}),request=async path=>({path});
 const visible=descriptor('/overview');cache.acquire(visible);await cache.read(visible,{request});
 for(const path of ['/one','/two','/three'])await cache.read(descriptor(path),{request});
 assert.equal(cache.stats().entries,2);assert.ok(cache.peek(visible));assert.equal(cache.peek(descriptor('/one')),null);
 cache.release(visible);cache.clear();assert.equal(cache.stats().bytes,0);
});

test('delayed background refresh preserves a fresh protocol-owned revision',async()=>{
 const cache=createOverviewCache();let calls=0;
 const own=descriptor('/protocols/a/overview','[0,0,0]');
 cache.invalidate();
 await cache.read(own,{request:async()=>({count:++calls})});
 await cache.prefetch('[0,0]');
 assert.equal(calls,1,'the project clock cannot replace an already refreshed protocol summary');
 assert.equal(cache.peek(own).revision,own.revision);
 await cache.read(own,{request:async()=>({count:++calls})});assert.equal(calls,1);
});

test('delayed background refresh shares an active protocol read with a distinct clock',async()=>{
 const cache=createOverviewCache(),pending=deferred();let calls=0,signal;
 const own=descriptor('/protocols/a/overview','[0,0,0]');
 cache.invalidate();
 const foreground=cache.read(own,{request:async(path,options)=>{calls++;signal=options.signal;return pending.promise;}});
 await Promise.resolve();const originalSignal=signal,background=cache.prefetch('[0,0]');await Promise.resolve();
 pending.resolve({count:132});await Promise.all([foreground,background]);
 assert.equal(calls,1);assert.equal(originalSignal.aborted,false);
 assert.equal(cache.peek(own).revision,own.revision);assert.equal(cache.peek(own).data.count,132);
});
