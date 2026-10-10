import {MAX_TRACE_SAMPLES} from './ui/traceGeometry.js';
import {traceRequestPath,traceResponseMatches} from './traceReadContext.js';

// Demand-read only the focused stream. Each transport read retains its existing
// bounded contract; the complete array belongs to one mounted resource lifetime.
export async function readWholeTrace({request,epochUuid,stream,readContext,sourceSha256,signal}){
  const total=stream.sample_count;
  if(!Number.isSafeInteger(total)||total<1)throw Error('Invalid recorded sample count.');
  let first;
  const values=[];
  for(let start=0;start<total;start+=MAX_TRACE_SAMPLES){
    signal?.throwIfAborted();
    const count=Math.min(MAX_TRACE_SAMPLES,total-start);
    const chunk=await request(traceRequestPath(epochUuid,stream,{start,count},readContext),{signal});
    signal?.throwIfAborted();
    const imported=['imported_snapshot','imported_cell_snapshot'].includes(readContext?.kind);
    if(!traceResponseMatches(chunk,readContext)||chunk?.epoch_uuid!==epochUuid||chunk?.stream_uuid!==stream.uuid||
       chunk.start!==start||chunk.count!==count||!Array.isArray(chunk.values)||chunk.values.length!==count||
       !(chunk.sample_rate>0)||!Number.isFinite(chunk.sample_rate)||chunk.decimated!==false||
       (chunk.total_samples!==total)||typeof chunk.source_sha256!=='string'||!chunk.source_sha256||
       (sourceSha256&&chunk.source_sha256!==sourceSha256)||
       (imported&&(chunk.source_sha256!==readContext.source_sha256||chunk.sample_rate!==stream.sample_rate||
         (typeof stream.units!=='string'&&stream.units!==null)||chunk.units!==stream.units))||
       (first&&(chunk.sample_rate!==first.sample_rate||chunk.units!==first.units||chunk.source_sha256!==first.source_sha256)))
      throw Error('Trace identity, sample rate, units or window does not match the request. No plot is shown.');
    if(!first)first={...chunk,values:undefined};
    for(const value of chunk.values)values.push(value);
  }
  return {...first,start:0,count:total,values};
}
