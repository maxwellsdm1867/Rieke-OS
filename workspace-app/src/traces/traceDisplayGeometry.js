import {traceRequestPath,traceResponseMatches} from './traceReadContext.js';

export const TRACE_GEOMETRY_TYPE='application/vnd.disco.trace-m4le.v1';
export const TRACE_GEOMETRY_ALGORITHM='first-last-extrema-v1';
export const GEOMETRY_UNAVAILABLE=Symbol('prepared geometry unavailable');
const MAX_HEADER_BYTES=65536,MAX_SAMPLES=1000000,MAX_WIDTH=16384;
const littleEndian=new Uint8Array(new Uint16Array([1]).buffer)[0]===1;
const integer=(value,min,max)=>Number.isSafeInteger(value)&&value>=min&&value<=max;
const invalid=()=>{throw Error('Invalid trace display geometry. No plot is shown.');};
export function geometryEligible(count,physicalWidth){
 return integer(count,1,MAX_SAMPLES)&&Number.isFinite(physicalWidth)&&physicalWidth>0&&physicalWidth<=MAX_WIDTH&&count>4*Math.ceil(physicalWidth);
}
function validate(value){
 if(!value||value.representation!=='m4_geometry'||value.algorithm!==TRACE_GEOMETRY_ALGORITHM||
  Object.hasOwn(value,'values')||Object.hasOwn(value,'decimated')||Object.hasOwn(value,'windows')||
  value.raw_start!==0||value.total_samples!==value.raw_count||!geometryEligible(value.raw_count,value.physical_width)||
  !integer(value.point_count,2,4*Math.ceil(value.physical_width))||
  !(value.indices instanceof Uint32Array)||!(value.point_values instanceof Float64Array)||
  value.indices.length!==value.point_count||value.point_values.length!==value.point_count||
  value.indices[0]!==0||value.indices.at(-1)!==value.raw_count-1)invalid();
 const stats=value.statistics;
 if(!stats||!Number.isFinite(stats.min)||!Number.isFinite(stats.max)||stats.min>stats.max||
  stats.finiteCount!==value.raw_count||stats.missingCount!==0)invalid();
 let min=Infinity,max=-Infinity;
 for(let index=0;index<value.point_count;index++){
  const sample=value.indices[index],point=value.point_values[index];
  if(sample>=value.raw_count||index>0&&sample<=value.indices[index-1]||!Number.isFinite(point))invalid();
  min=Math.min(min,point);max=Math.max(max,point);
 }
 // Bounds are numerical; original signed-zero point bits remain untouched.
 if(min!==stats.min||max!==stats.max)invalid();
 // Validate full bin coverage without loading or scanning the raw recording.
 // Binary search uses the identical JS operation order at floating boundaries.
 const columns=Math.ceil(value.physical_width),count=value.raw_count;
 const binOf=index=>Math.min(columns-1,Math.floor(index/(count-1)*value.physical_width));
 let first=0,position=0;
 for(let column=0;column<columns;column++){
  let next=count;
  if(column<columns-1){let lo=first,hi=count;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(binOf(mid)<column+1)lo=mid+1;else hi=mid;}next=lo;}
  const begin=position;while(position<value.point_count&&value.indices[position]<next)position++;
  const size=position-begin;
  if(next<=first||size<1||size>4||value.indices[begin]!==first||value.indices[position-1]!==next-1||
    (next-first===1?size!==1:size<2))invalid();
  first=next;
 }
 if(position!==value.point_count)invalid();
 return value;
}
export function decodeTraceGeometry(buffer){
 if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<8||buffer.byteLength>8+MAX_HEADER_BYTES+14+4*MAX_WIDTH*12)invalid();
 const bytes=new Uint8Array(buffer),view=new DataView(buffer);
 if(bytes[0]!==68||bytes[1]!==84||bytes[2]!==77||bytes[3]!==49)invalid();
 const length=view.getUint32(4,true),indicesStart=Math.ceil((8+length)/8)*8;
 if(!integer(length,1,MAX_HEADER_BYTES)||indicesStart>buffer.byteLength)invalid();
 let header;try{header=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes.subarray(8,8+length)));}catch{invalid();}
 if(!header||typeof header!=='object'||Array.isArray(header)||Object.hasOwn(header,'indices')||Object.hasOwn(header,'point_values')||
  !integer(header.point_count,2,4*MAX_WIDTH))invalid();
 const valuesStart=Math.ceil((indicesStart+header.point_count*4)/8)*8;
 if(valuesStart+header.point_count*8!==buffer.byteLength)invalid();
 for(let i=8+length;i<indicesStart;i++)if(bytes[i]!==0)invalid();
 for(let i=indicesStart+header.point_count*4;i<valuesStart;i++)if(bytes[i]!==0)invalid();
 const indices=littleEndian?new Uint32Array(buffer,indicesStart,header.point_count):new Uint32Array(header.point_count);
 const point_values=littleEndian?new Float64Array(buffer,valuesStart,header.point_count):new Float64Array(header.point_count);
 if(!littleEndian)for(let i=0;i<header.point_count;i++){indices[i]=view.getUint32(indicesStart+i*4,true);point_values[i]=view.getFloat64(valuesStart+i*8,true);}
 return validate({...header,indices,point_values});
}
export function traceDisplayPath(epochUuid,stream,readContext,physicalWidth){
 if(readContext?.kind!=='prepared_display'||!geometryEligible(stream?.sample_count,physicalWidth))invalid();
 traceRequestPath(epochUuid,stream,{start:0,count:Math.min(100000,stream.sample_count)},readContext);
 return `/trace-views/${readContext.token}/epochs/${epochUuid}/display?${new URLSearchParams({stream_uuid:stream.uuid,count:String(stream.sample_count),physical_width:String(physicalWidth),algorithm:TRACE_GEOMETRY_ALGORITHM})}`;
}
export function admitTraceGeometry(value,{epochUuid,sourceSha256,stream,readContext,physicalWidth}){
 validate(value);
 if(!traceResponseMatches(value,readContext)||value.epoch_uuid!==epochUuid||value.stream_uuid!==stream.uuid||
  value.source_sha256!==sourceSha256||!/^[0-9a-f]{64}$/.test(value.source_sha256)||
  value.sample_rate!==stream.sample_rate||!Number.isFinite(value.sample_rate)||value.sample_rate<=0||
  !(typeof stream.units==='string'||stream.units===null)||value.units!==stream.units||
  value.raw_count!==stream.sample_count||value.physical_width!==physicalWidth)invalid();
 return value;
}
export async function readTraceGeometry(request,path,options,identity){
 let value;
 try{value=await request(path,{...options,headers:{Accept:TRACE_GEOMETRY_TYPE}});}
 catch(error){options.signal?.throwIfAborted();if(error.status===409&&error.data?.code==='trace_geometry_unavailable')return GEOMETRY_UNAVAILABLE;throw error;}
 options.signal?.throwIfAborted();
 return admitTraceGeometry(value,identity);
}
