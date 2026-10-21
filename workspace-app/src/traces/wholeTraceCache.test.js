import test from 'node:test';
import assert from 'node:assert/strict';
import {requestTraceWindow,requestWholeTrace,warmNextWholeTrace,wholeTraceIdentity} from '../api.js';
import {epochResourceCache} from '../resourceCache.js';

// Canonical global trace reads through the real api adapter and shared cache.
// Only fetch is a fixture; responses use the ordinary JSON window contract.
const sha='a'.repeat(64);
function serve(){
 const requests=[],previous=globalThis.fetch;let source=sha;
 globalThis.fetch=async(input,options={})=>{
  const url=new URL(input,'http://fixture'),path=url.pathname.replace(/^\/api/,'');
  requests.push({path:path+url.search,background:options.headers?.['X-Disco-Trace-Priority']==='background'});
  const start=Number(url.searchParams.get('start')),count=Number(url.searchParams.get('count')),epoch=path.split('/')[2];
  const total=Number(epoch.split('-')[1]);
  const body={epoch_uuid:epoch,stream_uuid:'s',start,count,total_samples:total,decimated:false,sample_rate:10000,units:'pA',source_sha256:source,values:Array.from({length:count},(_,i)=>start+i)};
  return {ok:true,status:200,headers:new Map([['Content-Type','application/json']]),json:async()=>body};
 };
 return {requests,source:value=>{source=value;},restore(){globalThis.fetch=previous;epochResourceCache.invalidate();}};
}
const epochOf=(total,source=sha)=>({epoch_uuid:`e-${total}`,source_sha256:source,streams:[{kind:'responses',uuid:'s',sample_count:total,sample_rate:10000,units:'pA'}]});

test('a whole stream over 20k is read once, retained, and serves exact windows inside it',async()=>{
 const http=serve();
 try{
  const epoch=epochOf(50000),stream=epoch.streams[0];
  const whole=await requestWholeTrace({revision:3,epoch,stream});
  assert.equal(http.requests.length,1);assert.equal(whole.values.length,50000);
  assert.equal(await requestWholeTrace({revision:3,epoch,stream}),whole,'revisit is served from the decoded cache');
  const sample=await requestTraceWindow(`/epochs/${epoch.epoch_uuid}/trace?stream_uuid=s&start=100&count=200`,{revision:3,epoch,stream,window:{start:100,count:200}});
  assert.deepEqual([sample.start,sample.count,sample.values[0],sample.values.at(-1),sample.values.length],[100,200,100,299,200],'exact samples, no resampling');
  const wide=await requestWholeTrace({revision:3,epoch,stream,window:{start:1000,count:30000}});
  assert.deepEqual([wide.start,wide.count,wide.values[0]],[1000,30000,1000]);
  assert.equal(http.requests.length,1,'windows inside a retained stream send no request');
  // A different trace revision (structure/source event) or source hash never reuses it.
  await requestWholeTrace({revision:4,epoch,stream});assert.equal(http.requests.length,2);
  http.source('b'.repeat(64));const changed=epochOf(50000,'b'.repeat(64));
  await requestWholeTrace({revision:4,epoch:changed,stream:changed.streams[0]});assert.equal(http.requests.length,3,'new source revision is read fresh');
  // A whole read whose response source differs from the descriptor fails closed.
  await assert.rejects(requestWholeTrace({revision:5,epoch,stream}),/does not match/);
 }finally{http.restore();}
});

test('Sample windows inside a warmed <=20k whole-stream snapshot need no request',async()=>{
 const http=serve();
 try{
  const epoch=epochOf(1000),stream=epoch.streams[0],path=`/epochs/${epoch.epoch_uuid}/trace?stream_uuid=s&start=0&count=1000`;
  await requestTraceWindow(path,{revision:0,epoch,stream,window:{start:0,count:1000}});
  const sample=await requestTraceWindow(`/epochs/${epoch.epoch_uuid}/trace?stream_uuid=s&start=0&count=200`,{revision:0,epoch,stream,window:{start:0,count:200}});
  assert.equal(http.requests.length,1);assert.deepEqual([sample.count,sample.values.length,sample.values[199]],[200,200,199]);
 }finally{http.restore();}
});

test('next-epoch warming reads one bounded whole stream in the background and is cancellable',async()=>{
 const http=serve();
 try{
  const next=epochOf(60000);
  warmNextWholeTrace(next,{revision:1,delayMs:0});
  await new Promise(resolve=>setTimeout(resolve,30));
  assert.equal(http.requests.length,1);assert.equal(http.requests[0].background,true);
  assert.ok(epochResourceCache.peekWholeTrace(wholeTraceIdentity(1,next,next.streams[0])));
  await requestWholeTrace({revision:1,epoch:next,stream:next.streams[0]});assert.equal(http.requests.length,1,'demand uses the warmed stream');
  const cancel=warmNextWholeTrace(epochOf(70000),{revision:1,delayMs:20});cancel();
  for(const skipped of [epochOf(20000),epochOf(1000001)])warmNextWholeTrace(skipped,{revision:1,delayMs:0});
  await new Promise(resolve=>setTimeout(resolve,40));
  assert.equal(http.requests.length,1,'cancelled, short and oversized streams are not warmed');
 }finally{http.restore();}
});
