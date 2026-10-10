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
 const read=change=>readWholeTrace({request:request(change),epochUuid:id(5),stream:importedStream,readContext:context});
 assert.equal((await read(()=>{})).count,67500);
 for(const change of [d=>d.read_context={...context,scope_data_revision:id(7)},d=>d.sample_rate=9999,d=>d.units=null,d=>d.source_sha256='b'.repeat(64)])await assert.rejects(read(change),/does not match/);
});
