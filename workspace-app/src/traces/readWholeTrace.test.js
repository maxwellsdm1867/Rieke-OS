import test from 'node:test';
import assert from 'node:assert/strict';
import {readWholeTrace} from './readWholeTrace.js';
const stream={uuid:'s',sample_count:67500,sample_rate:10000,units:'pA'};
function fixture(change=()=>{}){
 const calls=[];
 return {calls,request:async(path,{signal})=>{
  const query=new URLSearchParams(path.split('?')[1]),start=Number(query.get('start')),count=Number(query.get('count'));
  calls.push({path,start,count,signal});
  const result={epoch_uuid:'e',stream_uuid:'s',start,count,total_samples:67500,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array.from({length:count},(_,i)=>start+i===20000?null:start+i)};
  change(result,calls.length);return result;
 }};
}
test('whole epoch reads exact bounded chunks, final partial chunk and missing boundary',async()=>{
 const f=fixture();const data=await readWholeTrace({...f,epochUuid:'e',stream});
 assert.deepEqual(f.calls.map(({start,count})=>[start,count]),[[0,20000],[20000,20000],[40000,20000],[60000,7500]]);
 assert.equal(data.count,67500);assert.equal(data.values.length,67500);assert.equal(data.values[19999],19999);assert.equal(data.values[20000],null);assert.equal(data.values.at(-1),67499);
});
for(const [name,change] of Object.entries({epoch:d=>d.epoch_uuid='other',stream:d=>d.stream_uuid='other',start:d=>d.start++,count:d=>d.count--,length:d=>d.values.pop(),total:d=>d.total_samples++,rate:d=>d.sample_rate++,units:d=>d.units='mV',source:d=>d.source_sha256='other',decimation:d=>d.decimated=true})){
 test(`whole epoch rejects ${name} mismatch without publishing partial data`,async()=>{
  const f=fixture((data,n)=>{if(n===2)change(data);});
  await assert.rejects(readWholeTrace({...f,epochUuid:'e',stream}),/does not match/);assert.equal(f.calls.length,2);
 });
}
test('abort prevents subsequent reads even when transport ignores abort',async()=>{
 const controller=new AbortController(),f=fixture(()=>controller.abort());
 await assert.rejects(readWholeTrace({...f,epochUuid:'e',stream,signal:controller.signal}),{name:'AbortError'});assert.equal(f.calls.length,1);
});
test('frozen authority is carried on every read; failure rejects the whole result',async()=>{
 const f=fixture();await readWholeTrace({...f,epochUuid:'e',stream,readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'exact'}});
 assert(f.calls.every(({path})=>path.startsWith('/protocols/p/workbench/candidates/c/epochs/e/trace?')&&path.includes('candidate_scope_revision=exact')));
 const failure=fixture((_data,n)=>{if(n===3)throw Error('source unavailable');});
 await assert.rejects(readWholeTrace({...failure,epochUuid:'e',stream}),/source unavailable/);
});
test('imported whole trace checks historical context, recorded units/rate and source on every chunk',async()=>{
 const id=n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
 const context={kind:'imported_snapshot',project_uuid:id(1),publication_revision:id(2),scope_data_revision:id(3),protocol_uuid:id(4),source_sha256:'a'.repeat(64),processing_version:'stored-v1'};
 const importedStream={...stream,uuid:id(6)};
 const request=change=>async path=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count');
  const data={epoch_uuid:id(5),stream_uuid:id(6),start,count,total_samples:67500,sample_rate:10000,units:'pA',source_sha256:context.source_sha256,decimated:false,values:Array(count).fill(1),read_context:context};
  if(start===20000)change(data);return data;
 };
 const read=change=>readWholeTrace({request:request(change),epochUuid:id(5),stream:importedStream,readContext:context,maxChunkSamples:100000});
 assert.equal((await read(()=>{})).count,67500);
 for(const change of [d=>d.read_context={...context,scope_data_revision:id(7)},d=>d.sample_rate=9999,d=>d.units=null,d=>d.source_sha256='b'.repeat(64)])await assert.rejects(read(change),/does not match/);
});

test('a large selected window reads only its exact interval in bounded chunks',async()=>{
 const f=fixture();const data=await readWholeTrace({...f,epochUuid:'e',stream,window:{start:15000,count:35001}});
 assert.deepEqual(f.calls.map(({start,count})=>[start,count]),[[15000,20000],[35000,15001]]);
 assert.equal(data.start,15000);assert.equal(data.count,35001);assert.equal(data.values[0],15000);assert.equal(data.values.at(-1),50000);
});


for(const frozen of [false,true])test(`300k whole trace uses three bounded requests with exact samples${frozen?' and frozen authority':''}`,async()=>{
 const calls=[],longStream={...stream,sample_count:300000};
 const readContext=frozen?{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'exact'}:null;
 const request=async path=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count');calls.push({path,start,count});
  return {epoch_uuid:'e',stream_uuid:'s',start,count,total_samples:300000,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array.from({length:count},(_,i)=>start+i===100000?null:start+i)};
 };
 const data=await readWholeTrace({request,epochUuid:'e',stream:longStream,readContext,maxChunkSamples:100000});
 assert.deepEqual(calls.map(({start,count})=>[start,count]),[[0,100000],[100000,100000],[200000,100000]]);
 assert.equal(data.values.length,300000);assert.equal(data.values[99999],99999);assert.equal(data.values[100000],null);assert.equal(data.values.at(-1),299999);
 if(frozen)assert(calls.every(({path})=>path.startsWith(readContext.root+'/epochs/e/trace?')&&path.includes('candidate_scope_revision=exact')));
 calls.length=0;
 await assert.rejects(readWholeTrace({request:async path=>{const value=await request(path);return value.start===100000?{...value,source_sha256:'changed'}:value;},epochUuid:'e',stream:longStream,readContext,maxChunkSamples:100000}),/does not match/);
 assert.equal(calls.length,2,'later corruption rejects before publication or another chunk');
});

function batchFixture({total=300000,frozen=false,change=()=>{}}={}){
 const calls=[],readContext=frozen?{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'exact'}:null;
 const request=async(path,{signal})=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count'),chunks=+(q.get('chunks')||1);calls.push({path,start,count,chunks,signal});
  const base={epoch_uuid:'e',stream_uuid:'s',total_samples:total,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false};
  const windows=Array.from({length:chunks},(_,i)=>{const at=start+i*count,n=Math.min(count,total-at);return {...base,start:at,count:n,values:Array.from({length:n},(_,j)=>at+j===100000?null:at+j)};});
  const result=chunks===1?windows[0]:{...base,start,count:windows.reduce((n,w)=>n+w.count,0),windows,...(frozen?{candidate_scope_revision:'exact'}:{})};
  change(result,calls.length);return result;
 };
 return {calls,request,epochUuid:'e',stream:{...stream,sample_count:total},readContext,maxChunkSamples:100000};
}
for(const frozen of [false,true])test(`300k whole trace publishes one exact bounded batch${frozen?' with frozen authority':''}`,async()=>{
 const f=batchFixture({frozen}),data=await readWholeTrace(f);
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].chunks,3);assert.equal(f.calls[0].count,100000);
 assert.equal(data.count,300000);assert.equal(data.values[99999],99999);assert.equal(data.values[100000],null);assert.equal(data.values.at(-1),299999);
});
for(const [name,change] of Object.entries({missing:d=>d.windows.splice(1,1),order:d=>d.windows.reverse(),middle:d=>d.windows[1].start++,source:d=>d.windows[1].source_sha256='changed',rate:d=>d.sample_rate++,count:d=>d.count--,oversized:d=>d.windows.push(d.windows[0]),authority:d=>d.candidate_scope_revision='retired'})){
 test(`whole batch rejects ${name} without publishing partial data`,async()=>{
  const f=batchFixture({frozen:true,change});await assert.rejects(readWholeTrace(f),/does not match/);assert.equal(f.calls.length,1);
 });
}
test('large whole trace batches at most ten windows and cancels a later response before publication',async()=>{
 const f=batchFixture({total:1200001}),data=await readWholeTrace(f);
 assert.deepEqual(f.calls.map(({start,count,chunks})=>[start,count,chunks]),[[0,100000,10],[1000000,100000,3]]);
 assert.equal(data.values.length,1200001);assert.equal(data.values.at(-1),1200000);
 const controller=new AbortController(),cancelled=batchFixture({total:1200001,change:(_data,n)=>{if(n===2)controller.abort();}});
 await assert.rejects(readWholeTrace({...cancelled,signal:controller.signal}),{name:'AbortError'});assert.equal(cancelled.calls.length,2);
});
test('legacy ordinary response to batch opt-in finishes every sample with ordinary fallback reads',async()=>{
 const f=batchFixture(),calls=[];
 const request=async(path,options)=>{
  calls.push(path);const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count');
  return {epoch_uuid:'e',stream_uuid:'s',start,count,total_samples:300000,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array.from({length:count},(_,i)=>start+i)};
 };
 const data=await readWholeTrace({...f,request});
 assert.equal(data.count,300000);assert.equal(data.values.at(-1),299999);assert.equal(calls.length,3);
 assert.ok(calls[0].includes('chunks=3'));assert(calls.slice(1).every(path=>!path.includes('chunks=')));
});
