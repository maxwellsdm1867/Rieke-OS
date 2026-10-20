import {clampWindow,MAX_TRACE_SAMPLES} from './traces/ui/traceGeometry.js';
import {createSharedReads} from './resourceRequest.js';

export const EPOCH_CACHE_LIMITS={entries:128,bytes:32*1024*1024,ttlMs:30000};
// Complete decoded canonical streams, separate from JSON response snapshots.
// Bytes count the binary64 samples (8 per value); arrays are never copied in.
export const WHOLE_TRACE_LIMITS={entries:6,bytes:24*1024*1024};
export function cacheableEpochPath(path){return typeof path==='string'&&/^\/epochs\/[^/?]+(?:\/trace)?(?:\?[^#]*)?$/.test(path);}
const tracePath=path=>path.split('?')[0].endsWith('/trace');
const metadataEpoch=path=>{const match=/^\/epochs\/([^/?]+)(?:\?|$)/.exec(path);if(!match)return null;try{return decodeURIComponent(match[1]);}catch{return null;}};
const PREFETCH_RESERVATION_BYTES=1024*1024;
const abortError=()=>Object.assign(new Error('Request cancelled'),{name:'AbortError'});
// A cache hit is a short-lived response snapshot, keyed by exact scope and data revision.
export function createResourceCache({entries=EPOCH_CACHE_LIMITS.entries,bytes=EPOCH_CACHE_LIMITS.bytes,ttlMs=EPOCH_CACHE_LIMITS.ttlMs,now=()=>Date.now(),wholeTraces:wholeLimits=WHOLE_TRACE_LIMITS}={}){
  const values=new Map(),reads=new WeakMap(),whole=new Map(),wholeReads=createSharedReads((_key,{run,signal})=>run(signal),{deferAbort:true});
  // generation retires every in-flight put; metadataGeneration only retires
  // metadata (epoch detail carries annotations), so a tag receipt never drops
  // unrelated trace samples or in-flight trace prefetch.
  let used=0,generation=0,metadataGeneration=0,reserved=0,reservations=0,demand=0,wholeUsed=0;
  const key=(path,revision)=>JSON.stringify([path,revision]);
  function remove(id){const value=values.get(id);if(value){used-=value.size;values.delete(id);}}
  function peek(path,revision){const value=values.get(key(path,revision));return value&&now()-value.at<ttlMs?value.data:undefined;}
  function get(path,revision){const id=key(path,revision),value=values.get(id);if(!value)return undefined;if(now()-value.at>=ttlMs){remove(id);return undefined;}value.speculative=false;values.delete(id);values.set(id,value);return value.data;}
  // One admission token for every caller; trace samples and decoded streams
  // compare only its first (global) part, metadata compares both parts.
  function token(){return `${generation}:${metadataGeneration}`;}
  const globalPart=admission=>String(admission).split(':')[0];
  function admits(path,admission){return path&&tracePath(path)?globalPart(admission)===String(generation):String(admission)===token();}
  function put(path,revision,data,admission=token(),{speculative=false}={}){
    if(!cacheableEpochPath(path)||!admits(path,admission))return false;
    let size;try{size=JSON.stringify(data).length*2;}catch{return false;}
    if(size>bytes)return false;
    if(speculative&&(size>PREFETCH_RESERVATION_BYTES||used+size>bytes*.75||values.size+1>Math.floor(entries*.75)))return false;
    const id=key(path,revision);remove(id);values.set(id,{path,revision,data,size,speculative,at:now()});used+=size;
    while(values.size>entries||used>bytes)remove(values.keys().next().value);
    return true;
  }
  function removeWhole(id){const value=whole.get(id);if(value){wholeUsed-=value.size;whole.delete(id);}}
  function invalidate(path,{related=false}={}){
    // A single scalar generation avoids an unbounded per-URL tombstone map.
    generation++;
    const base=path?.split('?')[0];
    for(const [id,value] of values)if(!path||value.path===path||related&&(value.path.split('?')[0]===base||value.path.startsWith(`${base}/`)))remove(id);
    const epochUuid=path?metadataEpoch(path):null;
    for(const [id,value] of whole)if(!path||related&&epochUuid!==null&&value.epochUuid===epochUuid)removeWhole(id);
  }
  // Tags live in epoch detail only: evict those metadata snapshots and refuse
  // their late puts. Trace samples and trace prefetch are unaffected.
  function invalidateAnnotations(receipt){
    metadataGeneration++;
    const all=receipt.targets.some(target=>target.target_kind==='cell');
    const ids=new Set(receipt.targets.filter(target=>target.target_kind==='epoch').map(target=>target.target_uuid));
    for(const [id,value] of values){
      const epochUuid=metadataEpoch(value.path);
      if(epochUuid!==null&&(all||ids.has(epochUuid)))remove(id);
    }
  }
  // Whole decoded streams: exact identity key, byte-bounded LRU, no TTL (the
  // identity includes source hash, rate, units, count and the trace revision).
  function getWholeTrace(id){const value=whole.get(id);if(!value)return undefined;whole.delete(id);whole.set(id,value);return value.data;}
  function peekWholeTrace(id){return whole.get(id)?.data;}
  function putWholeTrace(id,epochUuid,data,admission=token()){
    if(globalPart(admission)!==String(generation)||!data||typeof data.values?.length!=='number')return false;
    const size=data.values.length*8;
    if(size>Math.floor(wholeLimits.bytes/2))return false;
    removeWhole(id);whole.set(id,{data,epochUuid,size});wholeUsed+=size;
    while(whole.size>wholeLimits.entries||wholeUsed>wholeLimits.bytes)removeWhole(whole.keys().next().value);
    return true;
  }
  function pendingWholeTrace(id,run,{signal}={}){return wholeReads.load(JSON.stringify([id,generation]),id,{signal,run});}
  function reservePrefetch(protectedPaths=new Set(),revision=0){
    for(const [id,value] of values)if(now()-value.at>=ttlMs)remove(id);
    const fits=()=>used+reserved+PREFETCH_RESERVATION_BYTES<=bytes*.75&&values.size+reservations+1<=Math.floor(entries*.75);
    // A new page can replace unused speculative windows, never visited demand.
    for(const [id,value] of values){if(fits())break;if(value.speculative&&!(value.revision===revision&&protectedPaths.has(value.path)))remove(id);}
    if(!fits())return null;
    reserved+=PREFETCH_RESERVATION_BYTES;reservations++;let released=false;
    return()=>{if(!released){released=true;reserved-=PREFETCH_RESERVATION_BYTES;reservations--;}};
  }
  function beginDemand(){demand++;let done=false;return()=>{if(!done){done=true;demand--;}};}
  function pendingRequest(path,{request,revision,signal,token:admission=token(),speculative=false}){
    let pool=reads.get(request);if(!pool){pool=createSharedReads(request,{deferAbort:true});reads.set(request,pool);}
    // Trace reads join across tag receipts; metadata reads never do.
    return pool.load(JSON.stringify([path,revision,tracePath(path)?globalPart(admission):String(admission)]),path,{signal,background:speculative});
  }
  return {get,peek,put,reservePrefetch,prefetchPending:()=>reservations>0,beginDemand,hasDemand:()=>demand>0,invalidate,invalidateAnnotations,pendingRequest,token,traceToken:()=>generation,
    getWholeTrace,peekWholeTrace,putWholeTrace,pendingWholeTrace,stats:()=>({entries:values.size,bytes:used,wholeTraces:whole.size,wholeTraceBytes:wholeUsed})};
}
export const epochResourceCache=createResourceCache(EPOCH_CACHE_LIMITS);
export async function cachedResourceRequest(path,{request,revision=0,signal,cache=epochResourceCache,speculative=false}={}){
  if(signal?.aborted)throw abortError();
  if(!cacheableEpochPath(path))return request(path,{signal});
  const hit=(speculative?cache.peek:cache.get)(path,revision);if(hit!==undefined)return hit;
  const end=speculative?()=>{}:cache.beginDemand();
  try{
    const token=cache.token(),data=await cache.pendingRequest(path,{request,revision,signal,token,speculative});
    if(signal?.aborted)throw abortError();
    if(cache.peek(path,revision)!==data)cache.put(path,revision,data,token,{speculative});
    if(!speculative)cache.get(path,revision);return data;
  }finally{end();}
}
export function initialEpochTracePath(epoch){
  const stream=epoch?.streams?.find(stream=>stream.kind==='responses'&&Number.isSafeInteger(stream.sample_count)&&stream.sample_count>0);
  if(!epoch?.epoch_uuid||!stream?.uuid)return null;
  const {count}=clampWindow(0,MAX_TRACE_SAMPLES,stream.sample_count);
  return `/epochs/${epoch.epoch_uuid}/trace?stream_uuid=${stream.uuid}&start=0&count=${count}`;
}
// The viewer reuses the initial window only when it is the whole stream: longer
// whole-epoch streams use one batch read, and Sample reads its own window.
export function wholeTracePrefetchPath(epoch){
  const stream=epoch?.streams?.find(stream=>stream.kind==='responses'&&Number.isSafeInteger(stream.sample_count)&&stream.sample_count>0);
  return stream&&stream.sample_count<=MAX_TRACE_SAMPLES?initialEpochTracePath(epoch):null;
}
// Only a complete global snapshot can publish synchronously.
// Adjacent metadata prefetch alone must still fetch its initial trace.
export function peekEpochWithTrace(path,revision=0,cache=epochResourceCache){
  const match=typeof path==='string'&&/^\/epochs\/([^/?#]+)(?:\?[^#]*)?$/.exec(path);
  if(!match)return undefined;
  let epochUuid;try{epochUuid=decodeURIComponent(match[1]);}catch{return undefined;}
  const epoch=cache.peek(path,revision);
  if(epoch?.epoch_uuid!==epochUuid||!Array.isArray(epoch.streams)||epoch.streams.some(stream=>!stream||typeof stream!=='object'))return undefined;
  const responses=epoch.streams.filter(stream=>stream.kind==='responses');
  if(responses.some(stream=>!Number.isSafeInteger(stream.sample_count)||stream.sample_count<0))return undefined;
  const stream=responses.find(stream=>stream.sample_count>0);
  if(!stream)return epoch;
  if(typeof stream.uuid!=='string'||!stream.uuid)return undefined;
  const {count}=clampWindow(0,MAX_TRACE_SAMPLES,stream.sample_count);
  const trace=cache.peek(initialEpochTracePath(epoch),revision);
  return trace?.epoch_uuid===epochUuid&&trace.stream_uuid===stream.uuid&&trace.start===0&&trace.count===count&&
    Number.isFinite(trace.sample_rate)&&trace.sample_rate>0&&Array.isArray(trace.values)&&trace.values.length===count?epoch:undefined;
}
export async function requestEpochWithTrace(path,options){
  const epoch=await cachedResourceRequest(path,options);
  // Scoped candidate metadata must not prewarm a trace through global authority.
  const tracePath=cacheableEpochPath(path)?initialEpochTracePath(epoch):null;
  if(tracePath)try{await cachedResourceRequest(tracePath,options);}catch(error){if(options.signal?.aborted)throw error;/* Trace owns its error and retry; metadata remains usable. */}
  if(options.signal?.aborted)throw abortError();
  return epoch;
}
// Warm four following epochs and retain the immediately preceding trace.
export function epochPrefetchPaths(rows,index,pathFor,{progressive=false,activeCellOnly=false}={}){
  if(index<0||index>=rows.length)return [];
  const nearby=[...rows.slice(index+1,index+5),...(index?[rows[index-1]]:[])];
  const rest=[...rows.slice(index+5),...rows.slice(0,Math.max(0,index-1)).reverse()];
  const distant=activeCellOnly&&rows[index]?.cell_uuid?rest.filter(row=>row.cell_uuid===rows[index].cell_uuid):rest;
  return (progressive?[...nearby,...distant]:nearby).slice(0,60).map(pathFor);
}
// A finite admitted-page queue. Concurrent workers are supported for transports
// that benefit, but the current serialized native backend is faster for demand
// with one background worker. Reserve cache capacity before every network read.
function prefetchWindows(paths,{request,revision=0,delayMs=180,cache=epochResourceCache,progressive=false,concurrency=1}={},traceOnly){
  const selected=[...new Set(paths||[])].filter(path=>{
    if(!cacheableEpochPath(path)||path.split('?')[0].endsWith('/trace')!==traceOnly)return false;
    if(!traceOnly)return true;
    const query=new URLSearchParams(path.split('?')[1]),count=Number(query.get('count'));
    return query.get('start')==='0'&&!!query.get('stream_uuid')&&Number.isSafeInteger(count)&&count>0&&count<=MAX_TRACE_SAMPLES;
  }).slice(0,progressive?60:5);
  // Only global invalidation retires warming; tag receipts evict metadata alone.
  const protectedPaths=new Set(selected),controller=new AbortController(),token=cache.traceToken();let cursor=0,full=false;
  const current=()=>!controller.signal.aborted&&cache.traceToken()===token&&!full;
  const wait=()=>new Promise(resolve=>{const finish=()=>{clearTimeout(timer);controller.signal.removeEventListener('abort',finish);resolve();};const timer=setTimeout(finish,8);controller.signal.addEventListener('abort',finish,{once:true});});
  async function read(path){
    while(current()){
      if(cache.hasDemand()){await wait();continue;}
      const hit=cache.peek(path,revision);if(hit!==undefined)return hit;
      const release=cache.reservePrefetch(protectedPaths,revision);
      if(!release){if(cache.prefetchPending()){await wait();continue;}full=true;return null;}
      try{return await cachedResourceRequest(path,{request,revision,signal:controller.signal,cache,speculative:true});}finally{release();}
    }
    return null;
  }
  async function worker(){
    while(current()&&cursor<selected.length){
      const path=selected[cursor++];
      try{
        const data=await read(path);
        if(!current()||traceOnly)continue;
        const uuid=decodeURIComponent(path.split('?')[0].split('/')[2]);
        if(data?.epoch_uuid!==uuid)continue;
        const tracePath=initialEpochTracePath(data);
        if(tracePath){protectedPaths.add(tracePath);await read(tracePath);}
      }catch{if(!current())return;}
    }
  }
  const timer=setTimeout(()=>{const count=[1,2,4].includes(concurrency)?concurrency:1;for(let i=0;i<count;i++)void worker();},Math.max(0,delayMs));
  return()=>{clearTimeout(timer);controller.abort();};
}
// Trace-only browsing already has admitted locators; warming never fetches values.
export function prefetchTraceWindows(paths,options){return prefetchWindows(paths,options,true);}
export function prefetchEpochTraces(paths,options){return prefetchWindows(paths,options,false);}
// Only adjacent metadata is prefetched: browsing must not fan out H5 reads.
export function prefetchEpochMetadata(paths,{request,revision=0,delayMs=180,cache=epochResourceCache}={}){
  const selected=[...new Set(paths||[])].filter(path=>cacheableEpochPath(path)&&!path.split('?')[0].endsWith('/trace')).slice(0,2);
  const controller=new AbortController();let timer=setTimeout(async()=>{
    for(const path of selected){if(controller.signal.aborted)return;try{await cachedResourceRequest(path,{request,revision,signal:controller.signal,cache});}catch{if(controller.signal.aborted)return;}}
  },Math.max(0,delayMs));
  return ()=>{clearTimeout(timer);controller.abort();};
}
