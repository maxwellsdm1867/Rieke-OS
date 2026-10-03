import {createContext,useContext,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {api} from './api.js';
import {useAnnotationProfile} from './annotationProfile.js';
import {createPageReadCache,pageReadKey,searchReadDescriptor} from './pageReadCache.js';

const Context=createContext(null);
let owners=0;

// Lives in the App shell, above the search dialog's open/closed lifetime.
// Activation is a client fence, not a server generation or mutation receipt.
export function NavigationReadProvider({projectId,projectOpenIdentity='',actorId,children,cache:providedCache}){
  const [cache]=useState(()=>providedCache||createPageReadCache());
  const [ownerId]=useState(()=>`renderer-read-${++owners}`);
  const [activation,setActivation]=useState(0);
  const scope=useMemo(()=>projectId&&actorId?Object.freeze({projectUuid:projectId,actorId,activationId:JSON.stringify([ownerId,projectOpenIdentity,activation])}):null,[projectId,projectOpenIdentity,actorId,ownerId,activation]);
  useLayoutEffect(()=>{if(scope)cache.activate(scope);else cache.retire();return()=>cache.retire();},[cache,scope]);
  useEffect(()=>{
    const revoke=()=>{cache.retire();setActivation(value=>value+1);};
    const visible=()=>{if(globalThis.document?.visibilityState==='visible')revoke();};
    const events=['focus','online','pageshow'];
    for(const event of events)window.addEventListener(event,revoke);
    globalThis.document?.addEventListener('visibilitychange',visible);
    let previousStatus;
    const unsubscribe=window.riekeDesktop?.onStatus?.(status=>{if(status.state!==previousStatus){previousStatus=status.state;revoke();}});
    return()=>{for(const event of events)window.removeEventListener(event,revoke);globalThis.document?.removeEventListener('visibilitychange',visible);unsubscribe?.();};
  },[cache]);
  const value=useMemo(()=>({cache,scope}),[cache,scope]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function WorkspaceReadCacheOwner({projectId,projectOpenIdentity,children}){
  const profile=useAnnotationProfile();
  // Search remains available for browsing while optional author preferences
  // load/fail; transitions retire that provisional read namespace as well.
  const actorId=profile.loading?'profile-loading':profile.error?'profile-unavailable':profile.profileUuid?`profile:${profile.profileUuid}`:'browse-only';
  return <NavigationReadProvider projectId={projectId} projectOpenIdentity={projectOpenIdentity} actorId={actorId}>{children}</NavigationReadProvider>;
}

export function useSearchSnapshot({open,query,revision}){
  const owner=useContext(Context);
  if(!owner)throw Error('Search requires the App navigation read owner');
  const {cache,scope}=owner;
  const descriptor=useMemo(()=>scope&&query.trim()?searchReadDescriptor(scope,query,revision):null,[scope,query,revision]);
  const key=descriptor?pageReadKey(descriptor):null;
  const [state,setState]=useState({key:null,data:null,loading:false,error:''});
  const [nonce,setNonce]=useState(0);
  const generation=cache.stats().generation;
  const hit=open&&descriptor?cache.peek(descriptor):null;
  const current=state.key===key&&state.generation===generation&&state.nonce===nonce;
  const view=!open||!key?{data:null,loading:false,error:''}:current?state:{data:hit?.data||null,receivedAt:hit?.receivedAt,loading:!hit?.fresh,error:''};
  const fresh=!!view.data&&!view.loading&&!view.error&&cache.clock()-view.receivedAt<cache.freshMs;
  const latest=useRef(null);
  useLayoutEffect(()=>{latest.current={key,generation,open,data:view.data,fresh};});
  useEffect(()=>{
    if(!open||!descriptor){setState({key:null,data:null,loading:false,error:''});return;}
    const controller=new AbortController(),started=cache.stats().generation,cached=cache.peek(descriptor);
    setState({key,generation:started,nonce,data:cached?.data||null,receivedAt:cached?.receivedAt,loading:!cached?.fresh,error:''});
    const run=()=>cache.read(descriptor,{load:api,signal:controller.signal}).then(data=>{
      if(controller.signal.aborted||cache.stats().generation!==started)return;
      setState({key,generation:started,nonce,data,receivedAt:cache.peek(descriptor)?.receivedAt??cache.clock(),loading:false,error:''});
    }).catch(error=>{
      if(controller.signal.aborted)return;
      // Conflict clears the retained scope in the cache before this callback.
      const nowGeneration=cache.stats().generation;
      if(nowGeneration!==started&&error.status!==409)return;
      setState({key,generation:nowGeneration,nonce,data:error.status===409?null:cached?.data||null,receivedAt:cached?.receivedAt,loading:false,error:error.message});
    });
    const timer=cached?.fresh?(run(),null):setTimeout(run,cached?0:180);
    return()=>{controller.abort();clearTimeout(timer);};
  },[cache,descriptor,key,open,nonce]);
  useEffect(()=>{
    if(!open||!view.data||view.loading||view.error)return;
    const remaining=cache.freshMs-(cache.clock()-view.receivedAt);
    const timer=setTimeout(()=>setNonce(value=>value+1),Math.max(1,remaining));
    return()=>clearTimeout(timer);
  },[cache,key,open,view.data,view.receivedAt,view.loading,view.error]);
  return {...view,fresh,unavailable:open&&!!query.trim()&&!scope,retry:()=>setNonce(value=>value+1),canChoose(result){
    const live=latest.current;
    return !!live?.open&&live.key===key&&live.generation===cache.stats().generation&&live.data===view.data&&live.fresh&&cache.clock()-view.receivedAt<cache.freshMs&&view.data.results.includes(result);
  }};
}
