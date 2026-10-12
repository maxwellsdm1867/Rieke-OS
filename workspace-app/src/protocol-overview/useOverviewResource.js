import {useEffect,useLayoutEffect,useMemo,useRef,useSyncExternalStore} from 'react';
import {api,useResource} from '../api.js';
import {useWorkspaceRequestScope} from '../workspaceRequest.js';
import {createOverviewCache} from './overviewCache.js';

export function useOverviewCache(scope,revision,structureRevision=revision){
 const cache=useMemo(()=>createOverviewCache(),[scope]);
 const current=useRef(revision);current.current=revision;
 const structure=useRef(null);
 useLayoutEffect(()=>{
  const structural=structure.current?.cache!==cache||structure.current?.revision!==structureRevision;
  structure.current={cache,revision:structureRevision};
  // Imports/membership changes refresh visited summaries in the background.
  // During tag editing, invalidate hidden summaries without competing with the
  // active scientific page; its visible summary reads refresh themselves.
  cache.invalidate();
  if(structural){const timer=setTimeout(()=>{void cache.prefetch(revision);},200);return()=>clearTimeout(timer);}
 },[cache,revision,structureRevision]);
 useEffect(()=>{
  const refresh=()=>{void cache.refresh(current.current);};
  const visible=()=>{if(document.visibilityState==='visible')refresh();};
  window.addEventListener('focus',refresh);window.addEventListener('online',refresh);
  document.addEventListener('visibilitychange',visible);
  return()=>{window.removeEventListener('focus',refresh);window.removeEventListener('online',refresh);document.removeEventListener('visibilitychange',visible);cache.clear();};
 },[cache]);
 return cache;
}

const subscribeNothing=()=>()=>{},zero=()=>0;
export function useOverviewResource(path,revision,{cache,scope}={}){
 const owner=useWorkspaceRequestScope(),enabled=!!cache&&!owner;
 const fallback=useResource(enabled?null:path,revision);
 useSyncExternalStore(enabled?cache.subscribe:subscribeNothing,enabled?cache.snapshot:zero,zero);
 const descriptor=useMemo(()=>path?{path,scope,revision}:null,[path,scope,revision]);
 useEffect(()=>{
  if(!enabled||!descriptor)return;
  cache.acquire(descriptor);
  void cache.read(descriptor,{request:api}).catch(()=>{});
  return()=>cache.release(descriptor);
 },[enabled,cache,descriptor]);
 if(!enabled)return fallback;
 const entry=cache.peek(descriptor);
 return {data:entry?.data||null,error:entry?.error||null,
  loading:!!path&&(!entry||entry.loading||entry.invalidated||entry.revision!==revision),
  reload:()=>{if(descriptor)void cache.read(descriptor,{request:api,force:true}).catch(()=>{});}};
}
