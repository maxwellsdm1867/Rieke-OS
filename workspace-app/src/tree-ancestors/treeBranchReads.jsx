import {QueryClientProvider} from '@tanstack/react-query';
import {createContext,useContext,useEffect,useLayoutEffect,useMemo,useState} from 'react';
import {useAnnotationProfile} from "../annotations/annotationProfile.js";
import {createTreeBranchReadCache} from './treeBranchReadCache.js';

const Context=createContext(null);let nextOwner=0;
// The owner survives within-project routes; it retains JSON, never route DOM.
export function TreeBranchReadOwner({projectId,projectPath,revision,children,cache:providedCache}){
 const profile=useAnnotationProfile();
 const [cache]=useState(()=>providedCache||createTreeBranchReadCache());
 const [owner]=useState(()=>++nextOwner),[activation,setActivation]=useState(0);
 const actorId=profile.loading||profile.error?null:profile.profileUuid||'browse-only';
 const scope=useMemo(()=>projectId&&projectPath&&actorId?{projectUuid:projectId,projectPath,actorId,revision,activation:JSON.stringify([owner,activation])}:null,[projectId,projectPath,actorId,revision,owner,activation]);
 useLayoutEffect(()=>{if(scope)cache.activate(scope);else cache.retire();return()=>cache.retire();},[cache,scope]);
 useEffect(()=>{
  const revoke=()=>{cache.retire();setActivation(value=>value+1);};
  const events=['focus','online','pageshow','pagehide'];
  for(const name of events)window.addEventListener(name,revoke);
  document.addEventListener('visibilitychange',revoke);
  let previous;const unsubscribe=window.riekeDesktop?.onStatus?.(status=>{if(previous!==status.state){previous=status.state;revoke();}});
  return()=>{for(const name of events)window.removeEventListener(name,revoke);document.removeEventListener('visibilitychange',revoke);unsubscribe?.();};
 },[cache]);
 const value=useMemo(()=>({identity:JSON.stringify(scope),available:!!scope,active:()=>!scope||cache.isActive(scope),
  attest:(body,page)=>scope?cache.attest(scope,body,page):null,
  read:(...args)=>cache.read(...args),current:lease=>cache.assertCurrent(lease)}),[cache,scope]);
 return <QueryClientProvider client={cache.client}><Context.Provider value={value}>{children}</Context.Provider></QueryClientProvider>;
}
export function useTreeBranchReads(){return useContext(Context);}
