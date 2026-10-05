/**
 * Public search-activation entry; see ./AGENTS.md for the complete interface,
 * identity, cancellation and authority contract and executable consumer examples.
 */
// Disposable navigation reads only. A snapshot is never a mutation receipt.
export const PAGE_READ_CACHE_VERSION=1;
export const PAGE_READ_CACHE_LIMITS=Object.freeze({entries:16,bytes:32*1024*1024,freshMs:30000,retainMs:300000,inflight:4});
const cancelled=message=>Object.assign(new Error(message||'Read cancelled'),{name:'AbortError'});

// Undefined/non-JSON inputs fail closed; missing keys and explicit null differ.
export function canonicalReadIdentity(value){
  if(value===null)return 'null';
  if(typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
  if(typeof value==='number'&&Number.isFinite(value))return Object.is(value,-0)?'-0':JSON.stringify(value);
  if(Array.isArray(value)){
    if(Object.keys(value).length!==value.length)throw Error('Sparse read identity');
    return `[${value.map(canonicalReadIdentity).join(',')}]`;
  }
  if(value&&Object.getPrototypeOf(value)===Object.prototype)return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${canonicalReadIdentity(value[key])}`).join(',')}}`;
  throw Error('Read identity must be typed JSON');
}
export function pageReadKey(descriptor){
  const {schemaVersion,scope,resource,request,dependencies}=descriptor||{};
  if(schemaVersion!==PAGE_READ_CACHE_VERSION||!scope||!['projectUuid','activationId','actorId'].every(key=>typeof scope[key]==='string'&&scope[key]))throw Error('Exact project, activation and actor scope required');
  if(typeof resource!=='string'||!request||request.method!=='GET'||typeof request.path!=='string'||!dependencies)throw Error('Read request and dependency witnesses required');
  return canonicalReadIdentity({schemaVersion,scope,resource,request,dependencies});
}
function allowedSearchRead(descriptor){
  if(descriptor.resource!=='global-search'||descriptor.request.method!=='GET'||Object.hasOwn(descriptor.request,'body'))return false;
  if(!descriptor.request.path.startsWith('/search?'))return false;
  const params=new URLSearchParams(descriptor.request.path.slice(8));
  return params.size===2&&params.getAll('q').length===1&&params.get('q')?.trim().length>0&&params.get('q').length<=512&&params.get('limit')==='20';
}
function immutableJson(value){
  canonicalReadIdentity(value); // Also rejects lossy JSON values before copying.
  const encoded=JSON.stringify(value);
  const clone=item=>Array.isArray(item)?item.map(clone):item&&typeof item==='object'?Object.fromEntries(Object.entries(item).map(([key,child])=>[key,clone(child)])):item;
  const data=clone(value); // JSON.parse(JSON.stringify()) would turn -0 into 0.
  const pending=[data];while(pending.length){const item=pending.pop();if(item&&typeof item==='object'){Object.freeze(item);pending.push(...Object.values(item));}}
  return {data,bytes:new TextEncoder().encode(encoded).length};
}
export function validSearchResponse(data){
  return data&&Array.isArray(data.results)&&data.results.length<=20&&Number.isSafeInteger(data.total)&&data.total>=data.results.length&&data.results.every(row=>row&&['cell','epoch','field','value'].includes(row.kind)&&typeof row.id==='string'&&row.id&&typeof row.label==='string'&&(!['field','value'].includes(row.kind)||row.predicate&&typeof row.predicate==='object'));
}

export function createPageReadCache(options={}){
  const limits={...PAGE_READ_CACHE_LIMITS,...options},now=options.now||(()=>performance.now());
  for(const name of ['entries','bytes','inflight'])if(!Number.isSafeInteger(limits[name])||limits[name]<1)throw Error('Finite positive cache limits required');
  if(!Number.isFinite(limits.freshMs)||limits.freshMs<0||!Number.isFinite(limits.retainMs)||limits.retainMs<limits.freshMs)throw Error('Finite freshness and retention required');
  const values=new Map(),pending=new Map(),dispatched=new Set();let bytes=0,generation=0,scopeKey=null;
  const counters={hits:0,misses:0,networkReads:0,coalesced:0,cancelled:0,invalidations:0,evicted:0,oversized:0,errors:0};
  const remove=key=>{const value=values.get(key);if(value){bytes-=value.bytes;values.delete(key);}};
  const prune=()=>{for(const [key,value] of values)if(now()-value.receivedAt>=limits.retainMs)remove(key);};
  function finish(slot,error,data){
    if(pending.get(slot.key)===slot)pending.delete(slot.key);
    for(const subscriber of slot.subscribers){subscriber.signal?.removeEventListener('abort',subscriber.abort);error?subscriber.reject(error):subscriber.resolve(data);}
    slot.subscribers.clear();
  }
  function cancelPending(message){
    for(const slot of [...pending.values()]){slot.controller.abort();finish(slot,cancelled(message));counters.cancelled++;}
  }
  function invalidate(){generation++;counters.invalidations++;values.clear();bytes=0;cancelPending('Read scope changed');}
  function activate(scope){const next=canonicalReadIdentity(scope);if(scopeKey!==next){invalidate();scopeKey=next;}}
  function retire(){invalidate();scopeKey=null;}
  function checked(descriptor){const key=pageReadKey(descriptor);if(!allowedSearchRead(descriptor))throw Error('Resource is not allowlisted for navigation reuse');return {key,current:canonicalReadIdentity(descriptor.scope)===scopeKey};}
  function peek(descriptor){
    const {key,current}=checked(descriptor);if(!current)return undefined;prune();const value=values.get(key);
    return value?{data:value.data,receivedAt:value.receivedAt,fresh:now()-value.receivedAt<limits.freshMs}:undefined;
  }
  function put(slot,data){
    const copy=immutableJson(data);
    // Charge key and envelope as well as UTF-8 payload. This is not total heap.
    copy.bytes+=new TextEncoder().encode(slot.key).length+128;
    remove(slot.key); // A successful replacement revokes its predecessor even if oversized.
    if(copy.bytes>limits.bytes){counters.oversized++;return copy.data;}
    values.set(slot.key,{...copy,receivedAt:now()});bytes+=copy.bytes;
    while(values.size>limits.entries||bytes>limits.bytes){remove(values.keys().next().value);counters.evicted++;}
    return copy.data;
  }
  function read(descriptor,{load,signal,force=false}={}){
    if(signal?.aborted)return Promise.reject(cancelled());
    let identity;try{identity=checked(descriptor);}catch(error){return Promise.reject(error);}
    if(!identity.current)return Promise.reject(cancelled('Read activation retired'));
    const {key}=identity,hit=peek(descriptor);
    if(!force&&hit?.fresh){counters.hits++;const entry=values.get(key);values.delete(key);values.set(key,entry);return Promise.resolve(hit.data);}
    counters.misses++;
    let slot=pending.get(key);
    if(slot)counters.coalesced++;
    else{
      if(typeof load!=='function')return Promise.reject(Error('Read loader required'));
      if(dispatched.size>=limits.inflight)return Promise.reject(Error('Navigation read limit reached'));
      slot={key,generation,path:descriptor.request.path,controller:new AbortController(),subscribers:new Set()};pending.set(key,slot);dispatched.add(slot);
      const owned=slot;counters.networkReads++;
      Promise.resolve().then(()=>{if(owned.controller.signal.aborted)throw cancelled();return load(owned.path,{signal:owned.controller.signal});}).then(data=>{
        dispatched.delete(owned);
        if(pending.get(key)!==owned||owned.generation!==generation||owned.controller.signal.aborted)return;
        if(!validSearchResponse(data))throw Error('Incomplete navigation search response');
        finish(owned,null,put(owned,data));
      }).catch(error=>{
        dispatched.delete(owned);
        if(pending.get(key)!==owned)return;
        counters.errors++;finish(owned,error);
        if(error.status===409)invalidate(); // Scope conflict revokes all retained reads.
      }).finally(()=>dispatched.delete(owned));
    }
    return new Promise((resolve,reject)=>{
      const subscriber={resolve,reject,signal,abort:null};
      subscriber.abort=()=>{if(!slot.subscribers.delete(subscriber))return;signal?.removeEventListener('abort',subscriber.abort);reject(cancelled());
        if(!slot.subscribers.size){slot.controller.abort();if(pending.get(key)===slot)pending.delete(key);counters.cancelled++;}};
      slot.subscribers.add(subscriber);signal?.addEventListener('abort',subscriber.abort,{once:true});
    });
  }
  // Aggregate, query-free diagnostics: no persistent telemetry or scientific IDs.
  return {activate,retire,invalidate,peek,read,clock:now,freshMs:limits.freshMs,stats(){prune();return {...counters,entries:values.size,bytes,inflight:dispatched.size,generation};}};
}

export function searchReadDescriptor(scope,query,revision){
  return {schemaVersion:PAGE_READ_CACHE_VERSION,scope,resource:'global-search',request:{method:'GET',path:`/search?q=${encodeURIComponent(query.trim())}&limit=20`},dependencies:{workspaceRevision:revision}};
}
