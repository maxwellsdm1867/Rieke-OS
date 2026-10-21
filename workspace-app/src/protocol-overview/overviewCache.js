// Read-only overview snapshots live above route mounts. A local change or a
// return to the app invalidates them; simply navigating does not. Export/edit
// requests never consume this cache as authority.
export function createOverviewCache({maxEntries=12,maxBytes=8*1024*1024}={}){
 const entries=new Map(),listeners=new Set(),users=new Map();let version=0,bytes=0,queue=0;
 const keyOf=({scope,path})=>JSON.stringify([scope,path]);
 const notify=()=>{version++;for(const listener of listeners)listener();};
 const remove=key=>{const entry=entries.get(key);if(!entry)return;entry.operation?.controller.abort();bytes-=entry.bytes||0;entries.delete(key);};
 function peek(descriptor){return descriptor?entries.get(keyOf(descriptor))||null:null;}
 function read(descriptor,{request,force=false,background=false}={}){
  const key=keyOf(descriptor);let entry=entries.get(key);
  if(entry&&!force&&!entry.invalidated&&entry.revision===descriptor.revision){
   if(entry.operation)return entry.operation.promise;
   if(entry.data&&!entry.error)return Promise.resolve(entry.data);
  }
  if(!entry){entry={...descriptor,data:null,etag:null,bytes:0,loading:false,error:null};entries.set(key,entry);}
  entry.operation?.controller.abort();
  const operation={controller:new AbortController()};
  entry.operation=operation;entry.loading=true;entry.error=null;entry.preparation=null;entry.invalidated=false;
  entry.revision=descriptor.revision;entry.request=request;
  const previous=entry.data,etag=entry.etag;
  let nextEtag=null;
  operation.promise=Promise.resolve().then(()=>request(descriptor.path,{
   signal:operation.controller.signal,background,
   ...(etag&&previous?{headers:{'If-None-Match':etag},notModified:previous}:{}),
   onResponse:response=>{nextEtag=response.headers?.get?.('ETag')||null;},
  })).then(data=>{
   if(operation.controller.signal.aborted||entries.get(key)!==entry||entry.operation!==operation)return data;
   const size=JSON.stringify(data).length*2;
   bytes-=entry.bytes;entry.data=data;entry.etag=nextEtag;entry.bytes=size;bytes+=size;
   entry.loading=false;entry.error=null;entry.operation=null;
   entries.delete(key);entries.set(key,entry);
   // A currently visible oversized response may render, but cannot be retained
   // across navigation; releasing its last mounted consumer evicts it.
   while((entries.size>maxEntries||bytes>maxBytes)&&entries.size>1){
    const disposable=[...entries.keys()].find(candidate=>candidate!==key&&!users.has(candidate));
    if(disposable===undefined)break;
    remove(disposable);
   }
   if(size>maxBytes){entry.retain=false;}else entry.retain=true;
   notify();return data;
  },error=>{
   if(operation.controller.signal.aborted||entries.get(key)!==entry||entry.operation!==operation)return;
   bytes-=entry.bytes;entry.bytes=0;entry.data=null;entry.etag=null;
   entry.loading=false;entry.error=error.message;entry.preparation=error.preparation||null;entry.operation=null;notify();
   throw error;
  });
  notify();return operation.promise;
 }
 function invalidate(matches=null){
  queue++;const targets=[...entries.values()].filter(entry=>!matches||matches(entry));
  for(const entry of targets){entry.invalidated=true;entry.operation?.controller.abort();entry.operation=null;entry.loading=true;}
  notify();
  return targets;
 }
 async function prefetch(revision){
  const targets=[...entries.values()].reverse(),ownQueue=queue;
  // Refresh only summaries previously visited, serially. The visible page can
  // promote its own read immediately and share the same pending request.
  for(const entry of targets){
   if(ownQueue!==queue)return;
   if(entries.get(keyOf(entry))!==entry||!entry.request)continue;
   // A foreground owner may already have refreshed this entry using its own
   // revision clock. A delayed project-wide prefetch must not replace that
   // fresh (or pending) read just because the two clocks have different shapes.
   if(!entry.invalidated)continue;
   try{await read({...entry,revision},{request:entry.request,background:true});}catch{}
  }
 }
 async function refresh(revision){invalidate();await prefetch(revision);}
 return {peek,read,refresh,prefetch,invalidate,keyOf,
  subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
  snapshot:()=>version,
  acquire(descriptor){const key=keyOf(descriptor);users.set(key,(users.get(key)||0)+1);},
  release(descriptor){const key=keyOf(descriptor),remaining=(users.get(key)||1)-1;if(remaining)users.set(key,remaining);else users.delete(key);const entry=peek(descriptor);if(!remaining&&entry?.retain===false){remove(key);notify();}},
  clear(){queue++;for(const key of [...entries.keys()])remove(key);notify();},
  stats:()=>({entries:entries.size,bytes}),
 };
}
