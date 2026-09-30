import {clampWindow,MAX_TRACE_SAMPLES} from './components/traceGeometry.js';

export const EPOCH_CACHE_LIMITS={entries:64,bytes:12*1024*1024,ttlMs:30000};
export function cacheableEpochPath(path){return typeof path==='string'&&/^\/epochs\/[^/?]+(?:\/trace)?(?:\?[^#]*)?$/.test(path);}
const abortError=()=>Object.assign(new Error('Request cancelled'),{name:'AbortError'});
// A cache hit is a short-lived response snapshot, keyed by exact scope and data revision.
export function createResourceCache({entries=64,bytes=12*1024*1024,ttlMs=30000,now=()=>Date.now()}={}){
  const values=new Map();let used=0,generation=0;
  const key=(path,revision)=>JSON.stringify([path,revision]);
  function remove(id){const value=values.get(id);if(value){used-=value.size;values.delete(id);}}
  function peek(path,revision){const value=values.get(key(path,revision));return value&&now()-value.at<ttlMs?value.data:undefined;}
  function get(path,revision){const id=key(path,revision),value=values.get(id);if(!value)return undefined;if(now()-value.at>=ttlMs){remove(id);return undefined;}values.delete(id);values.set(id,value);return value.data;}
  function put(path,revision,data,token=generation){
    if(token!==generation||!cacheableEpochPath(path))return false;
    let size;try{size=JSON.stringify(data).length*2;}catch{return false;}
    if(size>bytes)return false;
    const id=key(path,revision);remove(id);values.set(id,{path,data,size,at:now()});used+=size;
    while(values.size>entries||used>bytes)remove(values.keys().next().value);
    return true;
  }
  function invalidate(path,{related=false}={}){
    // A single scalar generation avoids an unbounded per-URL tombstone map.
    generation++;
    const base=path?.split('?')[0];
    for(const [id,value] of values)if(!path||value.path===path||related&&(value.path.split('?')[0]===base||value.path.startsWith(`${base}/`)))remove(id);
  }
  function invalidateAnnotations(receipt){
    generation++;
    const all=receipt.targets.some(target=>target.target_kind==='cell');
    const ids=new Set(receipt.targets.filter(target=>target.target_kind==='epoch').map(target=>target.target_uuid));
    for(const [id,value] of values){
      const match=/^\/epochs\/([^/?]+)(?:\?|$)/.exec(value.path);
      if(match&&(all||ids.has(decodeURIComponent(match[1]))))remove(id);
    }
  }
  return {get,peek,put,invalidate,invalidateAnnotations,token:()=>generation,stats:()=>({entries:values.size,bytes:used})};
}
export const epochResourceCache=createResourceCache(EPOCH_CACHE_LIMITS);
export async function cachedResourceRequest(path,{request,revision=0,signal,cache=epochResourceCache}={}){
  if(signal?.aborted)throw abortError();
  if(!cacheableEpochPath(path))return request(path,{signal});
  const hit=cache.get(path,revision);if(hit!==undefined)return hit;
  const token=cache.token(),data=await request(path,{signal});
  if(signal?.aborted)throw abortError();
  cache.put(path,revision,data,token);return data;
}
export function initialEpochTracePath(epoch){
  const stream=epoch?.streams?.find(stream=>stream.kind==='responses'&&Number.isSafeInteger(stream.sample_count)&&stream.sample_count>0);
  if(!epoch?.epoch_uuid||!stream?.uuid)return null;
  const {count}=clampWindow(0,MAX_TRACE_SAMPLES,stream.sample_count);
  return `/epochs/${epoch.epoch_uuid}/trace?stream_uuid=${stream.uuid}&start=0&count=${count}`;
}
export async function requestEpochWithTrace(path,options){
  const epoch=await cachedResourceRequest(path,options);
  const tracePath=initialEpochTracePath(epoch);
  if(tracePath)try{await cachedResourceRequest(tracePath,options);}catch(error){if(options.signal?.aborted)throw error;/* Trace owns its error and retry; metadata remains usable. */}
  if(options.signal?.aborted)throw abortError();
  return epoch;
}
// Only adjacent metadata is prefetched: browsing must not fan out H5 reads.
export function prefetchEpochMetadata(paths,{request,revision=0,delayMs=180,cache=epochResourceCache}={}){
  const selected=[...new Set(paths||[])].filter(path=>cacheableEpochPath(path)&&!path.split('?')[0].endsWith('/trace')).slice(0,2);
  const controller=new AbortController();let timer=setTimeout(async()=>{
    for(const path of selected){if(controller.signal.aborted)return;try{await cachedResourceRequest(path,{request,revision,signal:controller.signal,cache});}catch{if(controller.signal.aborted)return;}}
  },Math.max(0,delayMs));
  return ()=>{clearTimeout(timer);controller.abort();};
}
