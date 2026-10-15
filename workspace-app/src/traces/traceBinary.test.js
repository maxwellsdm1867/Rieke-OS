import {traceSampleStatistics,traceStatisticsExtent} from './traceStatistics.js';
import {finiteExtent} from './ui/traceGeometry.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeTraceBinary,TRACE_BINARY_TYPE} from './traceBinary.js';
import {readWholeTrace} from './readWholeTrace.js';
import {requestApi} from '../api.js';

function encoded({start=0,count=6,total=count,chunkSize=2,frozen=false,mutateHeader=()=>{},sample=i=>i+.25}={}){
 const base={epoch_uuid:'e',stream_uuid:'s',total_samples:total,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false};
 const windows=[];for(let offset=0;offset<count;offset+=chunkSize){const n=Math.min(chunkSize,count-offset);windows.push({...base,start:start+offset,count:n,byte_offset:offset*8,byte_length:n*8});}
 const header={...base,start,count,windows,...(frozen?{candidate_scope_revision:'exact'}:{})};mutateHeader(header);
 const text=new TextEncoder().encode(JSON.stringify(header)),payload=Math.ceil((8+text.length)/8)*8;
 const buffer=new ArrayBuffer(payload+count*8),bytes=new Uint8Array(buffer),view=new DataView(buffer);
 bytes.set([68,84,70,49]);view.setUint32(4,text.length,true);bytes.set(text,8);
 for(let i=0;i<count;i++)view.setFloat64(payload+i*8,sample(start+i),true);
 return {buffer,payload,headerLength:text.length};
}

test('binary decoding preserves every binary64 bit and exposes contiguous zero-copy window views',()=>{
 const expected=[-0,Number.MIN_VALUE,-Number.MIN_VALUE,Number.MAX_VALUE,1+Number.EPSILON,-123.45678901234567];
 const {buffer,payload}=encoded({sample:i=>expected[i]}),decoded=decodeTraceBinary(buffer);
 const values=decoded.windows.flatMap(w=>Array.from(w.values));
 for(let i=0;i<expected.length;i++)assert.ok(Object.is(values[i],expected[i]));
 assert(decoded.windows.every(w=>w.values instanceof Float64Array&&w.values.buffer===buffer));
 assert.equal(decoded.windows[0].values.byteOffset,payload);
 assert.equal(decoded.windows[2].values.byteOffset,payload+4*8);
});
for(const [name,mutateHeader] of Object.entries({count:h=>h.count++,total:h=>h.total_samples--,start:h=>h.start=-1,oversized:h=>h.count=1000001,empty:h=>h.windows=[],tooMany:h=>h.windows=Array(11).fill(h.windows[0]),gap:h=>h.windows[1].byte_offset+=8,overlap:h=>h.windows[1].byte_offset=0,unaligned:h=>h.windows[0].byte_offset=1,length:h=>h.windows[0].byte_length++,order:h=>h.windows.reverse(),windowCount:h=>h.windows[0].count=100001,values:h=>h.windows[0].values=[],outerValues:h=>h.values=[]})){
 test(`binary framing rejects ${name}`,()=>assert.throws(()=>decodeTraceBinary(encoded({mutateHeader}).buffer),/Invalid binary trace/));
}
for(const [name,mutate] of Object.entries({magic:({buffer})=>new Uint8Array(buffer)[0]=0,version:({buffer})=>new Uint8Array(buffer)[3]=50,hugeHeader:({buffer})=>new DataView(buffer).setUint32(4,65537,true),utf8:({buffer})=>new Uint8Array(buffer)[8]=255,nan:({buffer,payload})=>new DataView(buffer).setFloat64(payload,NaN,true),infinity:({buffer,payload})=>new DataView(buffer).setFloat64(payload,Infinity,true)})){
 test(`binary bytes reject ${name}`,()=>{const frame=encoded();mutate(frame);assert.throws(()=>decodeTraceBinary(frame.buffer),/Invalid binary trace/);});
}
test('binary framing refuses nonzero padding, truncation and trailing bytes',()=>{
 let frame=encoded();for(let marker=1;(8+frame.headerLength)%8===0;marker++)frame=encoded({mutateHeader:h=>h.paddingMarker='x'.repeat(marker)});
 new Uint8Array(frame.buffer)[8+frame.headerLength]=1;
 assert.throws(()=>decodeTraceBinary(frame.buffer),/Invalid binary trace/);
 const {buffer}=encoded();assert.throws(()=>decodeTraceBinary(buffer.slice(0,-1)),/Invalid binary trace/);
 const extra=new Uint8Array(buffer.byteLength+8);extra.set(new Uint8Array(buffer));assert.throws(()=>decodeTraceBinary(extra.buffer),/Invalid binary trace/);
});

test('API negotiates binary, permits ordinary JSON fallback, and refuses malformed or unsolicited binary',async()=>{
 const previous=globalThis.fetch,calls=[];
 try{
  globalThis.fetch=async(_path,options)=>{calls.push(options);return new Response(encoded().buffer,{headers:{'Content-Type':TRACE_BINARY_TYPE}});};
  const data=await requestApi('/epochs/e/trace?count=2&chunks=3',{headers:{Accept:TRACE_BINARY_TYPE}});
  assert.equal(calls[0].headers.Accept,TRACE_BINARY_TYPE);assert(data.windows[0].values instanceof Float64Array);
  await assert.rejects(requestApi('/ordinary'),/Unexpected trace response/);
  globalThis.fetch=async()=>new Response(JSON.stringify({values:[1,null,3]}),{headers:{'Content-Type':'application/json'}});
  assert.deepEqual(await requestApi('/epochs/e/trace?count=2&chunks=3',{headers:{Accept:TRACE_BINARY_TYPE}}),{values:[1,null,3]});
  globalThis.fetch=async()=>new Response(encoded().buffer.slice(0,-1),{headers:{'Content-Type':TRACE_BINARY_TYPE}});
  await assert.rejects(requestApi('/epochs/e/trace?chunks=3',{headers:{Accept:TRACE_BINARY_TYPE}}),/Invalid binary trace/);
  globalThis.fetch=async()=>new Response('{}',{headers:{'Content-Type':'text/plain'}});
  await assert.rejects(requestApi('/epochs/e/trace?chunks=3',{headers:{Accept:TRACE_BINARY_TYPE}}),/Unexpected trace response/);
 }finally{globalThis.fetch=previous;}
});

test('whole trace reuses one admitted binary payload and retains scoped identity checks',async()=>{
 const frame=encoded({count:300000,chunkSize:100000,frozen:true}),requests=[];
 const readContext={root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'exact'};
 const options={epochUuid:'e',stream:{uuid:'s',sample_count:300000,sample_rate:10000,units:'pA'},readContext,maxChunkSamples:100000};
 const data=await readWholeTrace({...options,request:async(path,options)=>{requests.push({path,...options});return decodeTraceBinary(frame.buffer);}});
 assert.equal(requests.length,1);assert.equal(requests[0].headers.Accept,TRACE_BINARY_TYPE);
 assert.equal(data.values.buffer,frame.buffer);assert.equal(data.values.byteOffset,frame.payload);assert.equal(data.values.length,300000);assert.equal(data.values.at(-1),299999.25);
 await assert.rejects(readWholeTrace({...options,request:async()=>{const data=decodeTraceBinary(frame.buffer);data.candidate_scope_revision='stale';return data;}}),/does not match/);
});
test('multiple binary batches join into one exact array and cancellation rejects the later response',async()=>{
 const options={epochUuid:'e',stream:{uuid:'s',sample_count:1200001,sample_rate:10000,units:'pA'},maxChunkSamples:100000},frames=[],controller=new AbortController();
 let cancel=false;
 const request=async(path)=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=Math.min(+q.get('count')*(+q.get('chunks')||1),1200001-start);
  const frame=encoded({start,count,total:1200001,chunkSize:100000});frames.push(frame);
  if(cancel&&start)controller.abort();return decodeTraceBinary(frame.buffer);
 };
 const data=await readWholeTrace({...options,request});
 assert.equal(frames.length,2);assert(data.values instanceof Float64Array);assert.notEqual(data.values.buffer,frames[0].buffer);assert.equal(data.values[500000],500000.25);assert.equal(data.values.at(-1),1200000.25);
 cancel=true;await assert.rejects(readWholeTrace({...options,request,signal:controller.signal}),{name:'AbortError'});
});
test('mixed binary and JSON response windows preserve null gaps without numeric coercion',async()=>{
 const total=1100000,options={epochUuid:'e',stream:{uuid:'s',sample_count:total},maxChunkSamples:100000};
 const data=await readWholeTrace({...options,request:async path=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start');
  if(!start)return decodeTraceBinary(encoded({count:1000000,total,chunkSize:100000}).buffer);
  return {epoch_uuid:'e',stream_uuid:'s',start,count:100000,total_samples:total,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array(100000).fill(null)};
 }});
 assert(Array.isArray(data.values));assert.equal(data.values[999999],999999.25);assert.equal(data.values[1000000],null);
});

test('actual viewer keeps typed samples valid through whole extent and zero-copy sample navigation',async()=>{
 const React=await import('react'),{default:TestRenderer,act}=await import('react-test-renderer');
 const {createServer}=await import('../test-support/isolatedVite.js');
 const {fileURLToPath}=await import('node:url');
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const frame=encoded({count:300000,chunkSize:100000});let reads=0,renderer;
 const port={identity:'binary-view',request:async()=>{reads++;return decodeTraceBinary(frame.buffer);}};
 const epoch={epoch_uuid:'e',streams:[{uuid:'s',kind:'responses',sample_count:300000,sample_rate:10000,units:'pA'}]};
 try{
  await act(async()=>{renderer=TestRenderer.create(React.createElement(WorkspaceRequestProvider,{port},React.createElement(Trace,{epoch})));});
  const root=renderer.root;
  assert.equal(root.findByProps({'aria-label':'Exact sample index for cursor'}).props.disabled,false);assert.equal(reads,1);
  await act(async()=>root.findAllByType('button').find(b=>b.props.children==='Sample').props.onClick());
  assert.equal(root.findByProps({'aria-label':'Sample count'}).props.value,'200');
  assert.equal(root.findByProps({'aria-label':'Exact sample index for cursor'}).props.disabled,false);
  const form=root.findByType('form');
  await act(async()=>root.findByProps({'aria-label':'Start sample'}).props.onChange({target:{value:'100000'}}));
  await act(async()=>form.props.onSubmit({preventDefault(){}}));
  assert.equal(root.findByProps({'aria-label':'Start sample'}).props.value,'100000');assert.equal(reads,1,'loaded typed interval serves viewport changes without another request');
 }finally{await act(async()=>renderer?.unmount());await server.close();}
});

test('one million full-rate samples use one bounded request and a direct exact payload view',async()=>{
 const total=1000000,calls=[];let release,published=false;
 const ready=new Promise(resolve=>{release=resolve;});
 const sample=index=>index===500000?-0:index+.25;
 const frame=encoded({count:total,total,chunkSize:100000,sample});
 const request=async(path,options)=>{
  const q=new URLSearchParams(path.split('?')[1]);calls.push({start:+q.get('start'),count:+q.get('count'),chunks:+q.get('chunks'),headers:options.headers});
  await ready;return decodeTraceBinary(frame.buffer);
 };
 const pending=readWholeTrace({request,epochUuid:'e',stream:{uuid:'s',sample_count:total,sample_rate:10000,units:'pA'},maxChunkSamples:100000}).then(value=>{published=true;return value;});
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(calls.map(({start,count,chunks})=>[start,count,chunks]),[[0,100000,10]]);
 assert.equal(calls[0].headers.Accept,TRACE_BINARY_TYPE);assert.equal(published,false,'nothing publishes before the whole response validates');
 release();const data=await pending;
 assert(data.values instanceof Float64Array);assert.equal(data.values.length,total);assert.equal(data.count,total);
 assert.equal(data.values.buffer,frame.buffer,'one million samples never require a join copy');assert.equal(data.values.byteOffset,frame.payload);
 for(let i=0;i<total;i++)assert.ok(Object.is(data.values[i],sample(i)),`sample ${i} stays exact`);
});

test('one million plus one samples require one bounded binary batch and the exact remaining sample',async()=>{
 const total=1000001,calls=[];
 const data=await readWholeTrace({epochUuid:'e',stream:{uuid:'s',sample_count:total},maxChunkSamples:100000,request:async(path)=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count'),chunks=+(q.get('chunks')||1);calls.push([start,count,chunks]);
  if(!start)return decodeTraceBinary(encoded({count:1000000,total,chunkSize:100000}).buffer);
  return {epoch_uuid:'e',stream_uuid:'s',start,count,total_samples:total,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:[-0]};
 }});
 assert.deepEqual(calls,[[0,100000,10],[1000000,1,1]]);assert.equal(data.values.length,total);assert(Object.is(data.values.at(-1),-0));
});

test('binary frame above one million samples is refused even with consistent metadata and payload',()=>{
 assert.throws(()=>decodeTraceBinary(encoded({count:1000001,chunkSize:100000}).buffer),/Invalid binary trace/);
});


test('decoded statistics come from exact samples and survive whole-interval admission without trusting wire metadata',async()=>{
 const sample=i=>i===12345?-99.25:i===198765?101.5:i===50000?-0:2.25;
 const frame=encoded({count:300000,chunkSize:100000,sample,mutateHeader:header=>{
  header.statistics={min:0,max:0,finiteCount:0,missingCount:300000};
  for(const window of header.windows)window.statistics=header.statistics;
 }});
 const data=await readWholeTrace({request:async()=>decodeTraceBinary(frame.buffer),epochUuid:'e',stream:{uuid:'s',sample_count:300000},maxChunkSamples:100000});
 const facts=traceSampleStatistics(data.values);
 assert.deepEqual(facts,{min:-99.25,max:101.5,finiteCount:300000,missingCount:0});
 assert(Object.isFrozen(facts));assert.equal(traceSampleStatistics(data.values),facts,'admitted exact buffer facts need no repeated scan');
 assert.deepEqual(traceStatisticsExtent(facts),finiteExtent(data.values));
 const viewport=data.values.subarray(70000,70200),viewportFacts=traceSampleStatistics(viewport);
 assert.deepEqual(viewportFacts,{min:2.25,max:2.25,finiteCount:200,missingCount:0});
 assert.deepEqual(traceStatisticsExtent(viewportFacts),finiteExtent(viewport));
 assert(Object.is(data.values[50000],-0));
});

test('JSON and custom array statistics retain gaps, viewport extrema and producer mutations',()=>{
 for(const values of [[null,NaN,Infinity,-Infinity,-5,8,-0],new Float64Array([NaN,Infinity,-Infinity,-5,8,-0])]){
  const first=traceSampleStatistics(values);
  assert.equal(first.finiteCount,3);assert.equal(first.missingCount,values.length-3);
  assert.deepEqual(traceStatisticsExtent(first),finiteExtent(values));
  values[values.length-2]=77;
  assert.equal(traceSampleStatistics(values).max,77,'producer-owned arrays are never granted decoder statistics');
  const viewport=values.slice(-2);
  assert.deepEqual(traceStatisticsExtent(traceSampleStatistics(viewport)),finiteExtent(viewport));
 }
 assert.equal(traceStatisticsExtent(traceSampleStatistics([null,NaN,Infinity])),null);
});
