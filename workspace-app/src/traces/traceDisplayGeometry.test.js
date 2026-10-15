import test from 'node:test';
import assert from 'node:assert/strict';
import {TRACE_GEOMETRY_TYPE,TRACE_GEOMETRY_ALGORITHM,GEOMETRY_UNAVAILABLE,decodeTraceGeometry,admitTraceGeometry,readTraceGeometry,traceDisplayPath,geometryEligible} from './traceDisplayGeometry.js';
import {TRACE_BINARY_TYPE} from './traceBinary.js';
import {requestApi} from '../api.js';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const context={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
const stream={uuid:uid(7),sample_count:1001,sample_rate:10000,units:'pA'};
const header={representation:'m4_geometry',algorithm:TRACE_GEOMETRY_ALGORITHM,read_context:context,epoch_uuid:uid(6),stream_uuid:stream.uuid,source_sha256:'b'.repeat(64),sample_rate:stream.sample_rate,units:stream.units,total_samples:1001,raw_start:0,raw_count:1001,physical_width:1.25,point_count:4,statistics:{min:-3,max:2,finiteCount:1001,missingCount:0}};
const identity={epochUuid:uid(6),sourceSha256:header.source_sha256,stream,readContext:context,physicalWidth:header.physical_width};
function frame(change={},indices=[0,799,800,1000],points=[-0,2,-3,1]){
 const h={...header,...change},json=new TextEncoder().encode(JSON.stringify(h)),indexStart=Math.ceil((8+json.length)/8)*8,valueStart=Math.ceil((indexStart+indices.length*4)/8)*8,buffer=new ArrayBuffer(valueStart+points.length*8),view=new DataView(buffer),bytes=new Uint8Array(buffer);
 bytes.set([68,84,77,49]);view.setUint32(4,json.length,true);bytes.set(json,8);indices.forEach((value,i)=>view.setUint32(indexStart+i*4,value,true));points.forEach((value,i)=>view.setFloat64(valueStart+i*8,value,true));return {buffer,indexStart,valueStart,jsonLength:json.length};
}
test('DTM1 geometry is separate from raw arrays and preserves original point bits',()=>{
 const {buffer}=frame(),value=decodeTraceGeometry(buffer);assert.equal(value.point_values.buffer,buffer);assert.equal(value.indices.buffer,buffer);assert(Object.is(value.point_values[0],-0));assert.equal(value.values,undefined);assert.equal(value.raw_count,1001);assert.deepEqual([...value.indices],[0,799,800,1000]);assert.equal(admitTraceGeometry(value,identity),value);
 const path=traceDisplayPath(uid(6),stream,context,1.25);assert(path.startsWith(`/trace-views/${context.token}/epochs/${uid(6)}/display?`));assert(path.includes('physical_width=1.25'));assert(!path.includes('candidate_scope_revision'));
 assert.equal(geometryEligible(1000001,10),false);assert.equal(geometryEligible(1000,250),false);assert.equal(geometryEligible(1000,0),false);assert.equal(geometryEligible(1000000,16385),false);
});
test('geometry framing rejects malformed dimensions, raw masquerades, unordered indices and wrong statistics',()=>{
 for(const change of [{representation:'raw'},{algorithm:'other'},{raw_start:1},{raw_count:1000001,total_samples:1000001},{physical_width:Infinity},{physical_width:16385},{physical_width:300},{point_count:5},{values:[]},{decimated:false},{windows:[]},{statistics:{min:-4,max:2,finiteCount:1001,missingCount:0}},{statistics:{min:-3,max:2,finiteCount:1000,missingCount:1}}])assert.throws(()=>decodeTraceGeometry(frame(change).buffer),/Invalid trace display/);
 for(const indices of [[0,3,3,1000],[1,3,400,1000],[0,3,400,999],[0,400,3,1000]])assert.throws(()=>decodeTraceGeometry(frame({},indices).buffer),/Invalid trace display/);
 assert.throws(()=>decodeTraceGeometry(frame({},undefined,[-0,NaN,-3,1]).buffer),/Invalid trace display/);
 const good=frame();for(const mutate of [view=>view.setUint8(0,1),view=>view.setUint32(4,65537,true),view=>view.setFloat64(good.valueStart,Infinity,true)]){const copy=good.buffer.slice(0);mutate(new DataView(copy));assert.throws(()=>decodeTraceGeometry(copy),/Invalid trace display/);}
 assert.throws(()=>decodeTraceGeometry(good.buffer.slice(0,-1)),/Invalid trace display/);const trailing=new Uint8Array(good.buffer.byteLength+1);trailing.set(new Uint8Array(good.buffer));assert.throws(()=>decodeTraceGeometry(trailing.buffer),/Invalid trace display/);
 const odd=frame({point_count:3,physical_width:1,statistics:{min:-3,max:2,finiteCount:1001,missingCount:0}},[0,400,1000],[2,-3,1]);const padding=odd.buffer.slice(0);new Uint8Array(padding)[odd.indexStart+12]=1;assert.throws(()=>decodeTraceGeometry(padding),/Invalid trace display/);
});
test('geometry admission fences viewport, capability, source and descriptor independently',()=>{
 for(const change of [{epoch_uuid:uid(10)},{stream_uuid:uid(10)},{source_sha256:'c'.repeat(64)},{sample_rate:999},{units:'mV'},{read_context:{...context,token:uid(10)}},{candidate_scope_revision:'forbidden'}])assert.throws(()=>admitTraceGeometry(decodeTraceGeometry(frame(change).buffer),identity),/Invalid trace display/);
 assert.throws(()=>admitTraceGeometry(decodeTraceGeometry(frame().buffer),{...identity,physicalWidth:10.5}),/Invalid trace display/);
});
test('API geometry negotiation fails closed for JSON, raw binary and unsolicited geometry',async()=>{
 const old=globalThis.fetch;try{
  globalThis.fetch=async()=>new Response(frame().buffer,{headers:{'Content-Type':TRACE_GEOMETRY_TYPE}});assert.equal((await requestApi('/display',{headers:{Accept:TRACE_GEOMETRY_TYPE}})).point_count,4);
  await assert.rejects(requestApi('/display'),/Unexpected trace response/);await assert.rejects(requestApi('/display',{headers:{Accept:TRACE_BINARY_TYPE}}),/Unexpected trace response/);
  for(const type of ['application/json',TRACE_BINARY_TYPE]){globalThis.fetch=async()=>new Response('{}',{headers:{'Content-Type':type}});await assert.rejects(requestApi('/display',{headers:{Accept:TRACE_GEOMETRY_TYPE}}),/Unexpected trace response/);}
 }finally{globalThis.fetch=old;}
});
test('only the explicit unavailable code permits same-capability raw fallback; cancellation never does',async()=>{
 const error=(status,code)=>Object.assign(Error('refused'),{status,data:{code}});
 for(const [status,code,allowed] of [[409,'trace_geometry_unavailable',true],[409,'expired',false],[400,'trace_geometry_unavailable',false]]){
  const result=readTraceGeometry(async()=>{throw error(status,code);},'/display',{},identity);if(allowed)assert.equal(await result,GEOMETRY_UNAVAILABLE);else await assert.rejects(result,/refused/);
 }
 const controller=new AbortController();controller.abort();await assert.rejects(readTraceGeometry(async()=>{throw error(409,'trace_geometry_unavailable');},'/display',{signal:controller.signal},identity),{name:'AbortError'});
 await assert.rejects(readTraceGeometry(async()=>({...decodeTraceGeometry(frame().buffer),source_sha256:'c'.repeat(64)}),'/display',{},identity),/Invalid trace display/);
});
test('geometry shape requires each exact physical bin first and last and no more than four original points',()=>{
 assert.throws(()=>decodeTraceGeometry(frame({point_count:2,statistics:{min:0,max:1,finiteCount:1001,missingCount:0}},[0,1000],[0,1]).buffer),/Invalid trace display/);
 assert.throws(()=>decodeTraceGeometry(frame({physical_width:2.25},[0,444,889,1000]).buffer),/Invalid trace display/);
 assert.throws(()=>decodeTraceGeometry(frame({physical_width:1.00001,point_count:6},[0,1,2,3,999,1000],[0,2,-3,1,0,1]).buffer),/Invalid trace display/);
 const lastSingleton=frame({physical_width:1.00001,point_count:3},[0,999,1000],[2,-3,1]);assert.equal(decodeTraceGeometry(lastSingleton.buffer).point_count,3);
});
