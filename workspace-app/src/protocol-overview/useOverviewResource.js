import {useRetainedView} from '../retainedWorkspaceViews.js';
import {useEffect,useLayoutEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import {api,useResource} from '../api.js';
import {useWorkspaceRequestScope} from '../workspaceRequest.js';
import {createOverviewCache} from './overviewCache.js';
import {prepareView} from './prepareView.js';

export function useOverviewCache(scope,revision,structureRevision=revision,change=null){
 const cache=useMemo(()=>createOverviewCache(),[scope]);
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
 // Display snapshots refresh from known workspace changes, not app focus,
 // reconnect, or a timer. Commands still acquire their own current authority.
 useEffect(()=>()=>cache.clear(),[cache]);
 return cache;
}

const subscribeNothing=()=>()=>{},zero=()=>0;
export function useOverviewResource(path,revision,{cache,scope,active:requestedActive=true,renewRetained=true}={}){
 const owner=useWorkspaceRequestScope(),view=useRetainedView(),enabled=!!cache&&!owner,active=requestedActive&&view?.active!==false;
 const [reloadNonce,setReloadNonce]=useState(0),pendingReload=useRef(null),visible=useRef(false);
 useLayoutEffect(()=>{visible.current=active;return()=>{visible.current=false;};},[active]);
 const fallback=useResource(enabled||!active?null:path,revision);
 useSyncExternalStore(enabled?cache.subscribe:subscribeNothing,enabled?cache.snapshot:zero,zero);
 const descriptor=useMemo(()=>path?{path,scope,revision}:null,[path,scope,revision]);
 const entry=enabled?cache.peek(descriptor):null;
 const preparationDemand=useMemo(()=>({}),[descriptor,owner]),attemptedPreparation=useRef(null);
 const preparationIdentity=useMemo(()=>({}),[preparationDemand,active]),committedPreparation=useRef(null);
 const preparationOwner=useRef(null),[preparing,setPreparing]=useState(false),[prepareError,setPrepareError]=useState(null);
 useLayoutEffect(()=>{committedPreparation.current=preparationIdentity;setPreparing(false);setPrepareError(null);return()=>{committedPreparation.current=null;if(preparationOwner.current){attemptedPreparation.current=null;preparationOwner.current.abort();preparationOwner.current=null;}};},[preparationIdentity]);
 const prepare=async()=>{
  if(!active||!visible.current||owner||committedPreparation.current!==preparationIdentity||preparationOwner.current)return;
  attemptedPreparation.current=preparationDemand;
  const controller=new AbortController();preparationOwner.current=controller;setPreparing(true);setPrepareError(null);
  try{
   await prepareView(cache||preparationDemand,'/overview/prepare',{signal:controller.signal,request:async(path,options)=>{
    const result=await api(path,options);
    if(enabled&&!options.signal.aborted)cache.prepared();
    return result;
   }});
   if(controller.signal.aborted||preparationOwner.current!==controller)return;
   if(enabled)await cache.read(descriptor,{request:api});else fallback.reload();
  }catch(error){if(!controller.signal.aborted&&preparationOwner.current===controller)setPrepareError(error.message);}
  finally{if(preparationOwner.current===controller){preparationOwner.current=null;setPreparing(false);}}
 };
 const preparation=enabled?entry?.preparation:fallback.preparation;
 const preparationLoading=enabled?entry?.loading:fallback.loading;
 const automaticPending=active&&!owner&&!!path&&!preparationLoading&&preparation?.status==='pending'&&attemptedPreparation.current!==preparationDemand;
 useEffect(()=>{
  if(!active||owner||!path||preparationLoading||preparing)return;
  if(preparation?.status==='pending'&&attemptedPreparation.current!==preparationDemand)void prepare();
  else if(!preparation&&(enabled?entry?.data&&!entry.error:fallback.data&&!fallback.error))attemptedPreparation.current=null;
 },[active,owner,path,preparationLoading,preparing,preparation,preparationDemand,entry,fallback.data,fallback.error]);
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
 // Active demand must renew invalidation even when retained display data and
 // the descriptor revision are unchanged. Hidden consumers still wait for
 // activation; retained data never substitutes for a fresh read. The App shell
 // can keep initial root demand active while deferring its populated summary.
 const invalidatedDemand=!!entry?.invalidated&&(!entry.data||renewRetained);
 const display=useRef(null);
 if(entry?.data&&!entry.error)display.current={cache,path,scope,data:entry.data};
 if(!enabled&&active&&fallback.data&&!fallback.error)display.current={cache,path,scope,data:fallback.data};
 useEffect(()=>{
  if(!enabled||!active||!descriptor)return;
  cache.acquire(descriptor);
  const force=pendingReload.current===descriptor;pendingReload.current=null;
  void cache.read(descriptor,{request:api,...(force?{force:true}:{})}).catch(()=>{});
  return()=>cache.release(descriptor);
 },[enabled,active,cache,descriptor,invalidatedDemand,reloadNonce]);
 const displayData=display.current&&display.current.cache===cache&&display.current.path===path&&display.current.scope===scope?display.current.data:null;
 if(!enabled)return {...fallback,displayData,prepare,preparing:preparing||automaticPending,prepareError};
 return {data:entry?.data||null,displayData,prepare,preparing:preparing||automaticPending,prepareError,preparation:entry?.preparation||null,error:entry?.error||null,
  loading:!!path&&(pendingReload.current===descriptor||!entry||entry.loading||entry.invalidated||entry.revision!==revision),
  reload:()=>{if(!descriptor)return;if(!visible.current){pendingReload.current=descriptor;setReloadNonce(value=>value+1);return;}void cache.read(descriptor,{request:api,force:true}).catch(()=>{});}};
}
