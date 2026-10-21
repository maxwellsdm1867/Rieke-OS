import {useCallback,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {useRetainedView} from '../retainedWorkspaceViews.js';

// Read recovery is bounded by semantic owner, not the receipt it replaces.
// Presentation/selection remain with the caller; no gesture or write is replayed.
export function useEpochListRecovery(scope,{automatic=true,blocked=false,onRefresh}){
  const active=useRetainedView()?.active!==false;
  const identity=useMemo(()=>({scope,attempted:false}),[scope]);
  const [revision,setRevision]=useState(0),owner=useRef(null),latest=useRef(null);
  useLayoutEffect(()=>{latest.current={automatic,blocked,active,onRefresh};});
  useLayoutEffect(()=>{
    const lifetime=identity;owner.current=lifetime;
    return()=>{if(owner.current===lifetime)owner.current=null;};
  },[identity]);
  const request=useCallback((manual=false)=>{
    const current=owner.current,options=latest.current;
    if(!current||current!==identity||!options?.active||options.blocked||(!manual&&(!options.automatic||current.attempted)))return false;
    if(options.onRefresh(manual)===false)return false;
    current.attempted=true;setRevision(value=>value+1);return true;
  },[identity,active,automatic,blocked]);
  return {revision,request};
}
