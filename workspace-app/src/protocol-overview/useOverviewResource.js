import {useRetainedView} from '../retainedWorkspaceViews.js';
import {useEffect,useLayoutEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import {api,useResource} from '../api.js';
import {useWorkspaceRequestScope} from '../workspaceRequest.js';
import {createOverviewCache} from './overviewCache.js';

export function useOverviewCache(scope,revision,structureRevision=revision,change=null){
 const cache=useMemo(()=>createOverviewCache(),[scope]);
 const current=useRef(revision);current.current=revision;
 const structure=useRef(null),typed=useRef(null);
 useLayoutEffect(()=>{
  const structural=structure.current?.cache!==cache||structure.current?.revision!==structureRevision;
  structure.current={cache,revision:structureRevision};
  // A typed membership/curation change for one protocol invalidates only that
  // protocol's summaries and the project summary. Mounted entries re-read via
  // their changed descriptor; other visited summaries stay until visited.
  const protocolId=['membership','curation','curation-receipt'].includes(change?.kind)&&change.seq!==typed.current?change.protocolId:null;
  typed.current=change?.seq??null;
  if(protocolId&&!structural){cache.invalidate(entry=>entry.path==='/overview'||entry.path.startsWith(`/protocols/${protocolId}/`)||entry.path.startsWith(`/protocols/${protocolId}?`));return;}
  // Imports/structure changes refresh visited summaries in the background.
  // During tag editing, invalidate hidden summaries without competing with the
  // active scientific page; its visible summary reads refresh themselves.
  cache.invalidate();
  if(structural){const timer=setTimeout(()=>{void cache.prefetch(revision);},200);return()=>clearTimeout(timer);}
 },[cache,revision,structureRevision,change?.seq]);
 useEffect(()=>{
  let pendingFocus,internalUntil=0,projectVisible=true;
  const bridge=window.riekeDesktop;
  const stopVisibility=bridge?.onProjectVisibility?.(event=>{
   projectVisible=event.visible!==false;
   // Native view selection is not an external data change. Batch DOM focus
   // with its native visibility message; scientific witness owners still
   // revoke independently, and known revision changes still invalidate above.
   if(projectVisible){internalUntil=Date.now()+250;clearTimeout(pendingFocus);}
  });
  const refresh=()=>{if(projectVisible)void cache.refresh(current.current);};
  const focus=()=>{
   if(!stopVisibility){refresh();return;}
   clearTimeout(pendingFocus);
   pendingFocus=setTimeout(()=>{if(Date.now()>internalUntil)refresh();},50);
  };
  const visible=()=>{if(document.visibilityState==='visible')focus();};
  window.addEventListener('focus',focus);window.addEventListener('online',refresh);
  document.addEventListener('visibilitychange',visible);
  return()=>{clearTimeout(pendingFocus);stopVisibility?.();window.removeEventListener('focus',focus);window.removeEventListener('online',refresh);document.removeEventListener('visibilitychange',visible);cache.clear();};
 },[cache]);
 return cache;
}

const subscribeNothing=()=>()=>{},zero=()=>0;
export function useOverviewResource(path,revision,{cache,scope,active:requestedActive=true}={}){
 const owner=useWorkspaceRequestScope(),view=useRetainedView(),enabled=!!cache&&!owner,active=requestedActive&&view?.active!==false;
 const [reloadNonce,setReloadNonce]=useState(0),pendingReload=useRef(null),visible=useRef(false);
 useLayoutEffect(()=>{visible.current=active;return()=>{visible.current=false;};},[active]);
 const fallback=useResource(enabled||!active?null:path,revision);
 useSyncExternalStore(enabled?cache.subscribe:subscribeNothing,enabled?cache.snapshot:zero,zero);
 const descriptor=useMemo(()=>path?{path,scope,revision}:null,[path,scope,revision]);
 const entry=enabled?cache.peek(descriptor):null;
 const preparationIdentity=useMemo(()=>({}),[descriptor,active,owner]),committedPreparation=useRef(null);
 const preparationOwner=useRef(null),[preparing,setPreparing]=useState(false),[prepareError,setPrepareError]=useState(null);
 useLayoutEffect(()=>{committedPreparation.current=preparationIdentity;setPreparing(false);setPrepareError(null);return()=>{committedPreparation.current=null;preparationOwner.current?.abort();preparationOwner.current=null;};},[preparationIdentity]);
 const prepare=async()=>{
  if(!active||!visible.current||owner||committedPreparation.current!==preparationIdentity||preparationOwner.current)return;
  const controller=new AbortController();preparationOwner.current=controller;setPreparing(true);setPrepareError(null);
  try{
   await api('/overview/prepare',{method:'POST',body:{},signal:controller.signal});
   if(controller.signal.aborted||preparationOwner.current!==controller)return;
   if(enabled)await cache.read(descriptor,{request:api,force:true});else fallback.reload();
  }catch(error){if(!controller.signal.aborted&&preparationOwner.current===controller)setPrepareError(error.message);}
  finally{if(preparationOwner.current===controller){preparationOwner.current=null;setPreparing(false);}}
 };
 const durationData=enabled?entry?.data:fallback.data;
 const durationPending=durationData?.duration_status==='pending'||durationData?.counts?.duration_status==='pending'||
  durationData?.cells?.some(cell=>cell.duration_status==='pending')||durationData?.protocols?.some(protocol=>protocol.counts?.duration_status==='pending');
 useEffect(()=>{
  if(!active||!durationPending)return;
  let cancelled=false,timer,attempts=0;
  const poll=async()=>{
   if(cancelled||++attempts>15)return;
   if(enabled)await cache.read(descriptor,{request:api,force:true}).catch(()=>{});else fallback.reload();
   if(!cancelled)timer=setTimeout(poll,2000);
  };
  timer=setTimeout(poll,2000);return()=>{cancelled=true;clearTimeout(timer);};
 },[active,durationPending,enabled,cache,descriptor]);
 // A root summary may still be required by the shell after navigation hides
 // its page. Invalidating an unfinished read must not strand that demand just
 // because its deferred display revision did not change.
 const missingInvalidated=!!entry?.invalidated&&!entry.data;
 const display=useRef(null);
 if(entry?.data&&!entry.error)display.current={cache,path,scope,data:entry.data};
 if(!enabled&&active&&fallback.data&&!fallback.error)display.current={cache,path,scope,data:fallback.data};
 useEffect(()=>{
  if(!enabled||!active||!descriptor)return;
  cache.acquire(descriptor);
  const force=pendingReload.current===descriptor;pendingReload.current=null;
  void cache.read(descriptor,{request:api,...(force?{force:true}:{})}).catch(()=>{});
  return()=>cache.release(descriptor);
 },[enabled,active,cache,descriptor,missingInvalidated,reloadNonce]);
 const displayData=display.current&&display.current.cache===cache&&display.current.path===path&&display.current.scope===scope?display.current.data:null;
 if(!enabled)return {...fallback,displayData,prepare,preparing,prepareError};
 return {data:entry?.data||null,displayData,prepare,preparing,prepareError,preparation:entry?.preparation||null,error:entry?.error||null,
  loading:!!path&&(pendingReload.current===descriptor||!entry||entry.loading||entry.invalidated||entry.revision!==revision),
  reload:()=>{if(!descriptor)return;if(!visible.current){pendingReload.current=descriptor;setReloadNonce(value=>value+1);return;}void cache.read(descriptor,{request:api,force:true}).catch(()=>{});}};
}
