import {combineDecodedTraceStatistics} from './traceStatistics.js';
import {TRACE_BINARY_TYPE} from './traceBinary.js';
import {MAX_TRACE_SAMPLES} from './ui/traceGeometry.js';
import {traceRequestPath,traceResponseMatches} from './traceReadContext.js';

export const MAX_WHOLE_TRACE_CHUNK_SAMPLES=100000;

// Demand-read only the focused stream. Each transport read retains its existing
// bounded contract; the complete array belongs to one mounted resource lifetime.
export async function readWholeTrace({request,epochUuid,stream,readContext,sourceSha256,signal,window={start:0,count:stream.sample_count},maxChunkSamples=MAX_TRACE_SAMPLES}){
  const total=stream.sample_count;
  if(!Number.isSafeInteger(total)||total<1)throw Error('Invalid recorded sample count.');
  if(!Number.isSafeInteger(window.start)||!Number.isSafeInteger(window.count)||window.start<0||window.count<1||window.start+window.count>total)throw Error('Invalid recorded sample window.');
  if(![MAX_TRACE_SAMPLES,MAX_WHOLE_TRACE_CHUNK_SAMPLES].includes(maxChunkSamples))throw Error('Invalid trace transport bound.');
  const imported=['imported_snapshot','imported_cell_snapshot'].includes(readContext?.kind);
  // Snapshot endpoints retain their separate 20k contract. Canonical/frozen
  // whole-stream demand can use the existing 100k HTTP bound.
  const chunkSize=imported?MAX_TRACE_SAMPLES:maxChunkSamples;
  let first;
  const parts=[],end=window.start+window.count;
  let batchEnabled=!imported&&maxChunkSamples===MAX_WHOLE_TRACE_CHUNK_SAMPLES&&window.start===0&&window.count===total;
  const invalid=()=>{throw Error('Trace identity, sample rate, units or window does not match the request. No plot is shown.');};
  const matchesHeader=chunk=>traceResponseMatches(chunk,readContext)&&chunk?.epoch_uuid===epochUuid&&chunk?.stream_uuid===stream.uuid&&
    chunk.sample_rate>0&&Number.isFinite(chunk.sample_rate)&&chunk.decimated===false&&chunk.total_samples===total&&
    typeof chunk.source_sha256==='string'&&!!chunk.source_sha256&&(!sourceSha256||chunk.source_sha256===sourceSha256)&&
    (!imported||chunk.source_sha256===readContext.source_sha256&&chunk.sample_rate===stream.sample_rate&&
      (typeof stream.units==='string'||stream.units===null)&&chunk.units===stream.units)&&
    (!first||chunk.sample_rate===first.sample_rate&&chunk.units===first.units&&chunk.source_sha256===first.source_sha256);
  for(let start=window.start;start<end;){
    signal?.throwIfAborted();
    const count=Math.min(chunkSize,end-start),chunks=batchEnabled?Math.min(10,Math.ceil((end-start)/chunkSize)):1;
    const path=traceRequestPath(epochUuid,stream,{start,count},readContext)+(chunks>1?`&chunks=${chunks}`:'');
    const response=await request(path,{signal,...(chunks>1?{headers:{Accept:TRACE_BINARY_TYPE}}:{})});
    signal?.throwIfAborted();
    const batch=Object.hasOwn(response??{},'windows');
    if(batch){
      if(chunks===1||!Array.isArray(response.windows)||response.windows.length!==chunks||
        !matchesHeader(response)||response.start!==start||response.count!==Math.min(chunks*count,end-start)||
        (readContext&&response.candidate_scope_revision!==readContext.candidate_scope_revision))invalid();
    }else if(chunks>1){
      // Older endpoints ignore the opt-in parameter. Admit their one ordinary
      // window and finish with ordinary requests; never treat it as a full batch.
      batchEnabled=false;
    }
    for(const chunk of batch?response.windows:[response]){
      const expectedCount=Math.min(chunkSize,end-start);
      if(!matchesHeader(chunk)||chunk.start!==start||chunk.count!==expectedCount||
        !(Array.isArray(chunk.values)||!imported&&chunk.values instanceof Float64Array)||chunk.values.length!==expectedCount)invalid();
      if(batch&&(chunk.sample_rate!==response.sample_rate||chunk.units!==response.units||chunk.source_sha256!==response.source_sha256))invalid();
      if(!first)first={...chunk,values:undefined};
      parts.push(chunk.values);
      start+=expectedCount;
    }
  }
  let values;
  if(parts.every(part=>part instanceof Float64Array)){
    let offset=parts[0].byteOffset;
    const contiguous=parts.every(part=>{const valid=part.buffer===parts[0].buffer&&part.byteOffset===offset;offset+=part.byteLength;return valid;});
    if(contiguous)values=new Float64Array(parts[0].buffer,parts[0].byteOffset,window.count);
    else{values=new Float64Array(window.count);let at=0;for(const part of parts){values.set(part,at);at+=part.length;}}
  }else{
    // JSON fallback retains null gaps and exact existing values, without coercion.
    values=new Array(window.count);let at=0;for(const part of parts)for(const value of part)values[at++]=value;
  }
  combineDecodedTraceStatistics(values,parts);
  return {...first,start:window.start,count:window.count,values};
}
