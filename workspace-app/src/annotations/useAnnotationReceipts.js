import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {annotationFilterNeedsRefresh,mergeAnnotationReceipts,applyAnnotationReceipts} from './annotationReceipts.js';

export const ANNOTATION_AUTHORITY_IDLE_MS=75;
export function useAnnotationReceipts({revision,structureRevision,change,origin,scope,filters}){
  const committed=useRef({revision,structureRevision,epochRevision:revision,authorityRevision:revision,scope,store:new Map()});
  const [flushed,setFlushed]=useState(revision);
  const owned=change?.revision===revision&&change.origin===origin&&change.confirmed?.version===1;
  const snapshot=useMemo(()=>{
    const before=committed.current;
    if(before.revision===revision&&before.structureRevision===structureRevision)return before;
    if(owned&&before.structureRevision===structureRevision){
      const store=mergeAnnotationReceipts(before.store,change.confirmed);
      // An evicted receipt may be the only fresh copy of the focused target.
      // Reload its metadata before permitting another edit on that old base.
      const evicted=[...before.store.keys()].some(key=>!store.has(key));
      return {...before,revision,epochRevision:evicted?revision:before.epochRevision,store};
    }
    return {revision,structureRevision,epochRevision:revision,authorityRevision:revision,scope,store:new Map()};
  },[revision,structureRevision,owned,change,scope]);
  const immediate=!owned||annotationFilterNeedsRefresh(filters)||committed.current.scope!==scope||flushed===revision;
  const prior=committed.current.revision===revision?committed.current.authorityRevision:snapshot.authorityRevision;
  const authorityRevision=immediate?revision:prior,dirty=authorityRevision!==revision;
  useLayoutEffect(()=>{committed.current={...snapshot,authorityRevision,scope};},[snapshot,authorityRevision,scope]);
  useEffect(()=>{if(dirty){const timer=setTimeout(()=>setFlushed(revision),ANNOTATION_AUTHORITY_IDLE_MS);return()=>clearTimeout(timer);}},[dirty,revision]);
  const flushAuthority=useCallback(()=>setFlushed(revision),[revision]);
  const apply=useCallback(epoch=>applyAnnotationReceipts(epoch,snapshot.store),[snapshot.store]);
  return {epochRevision:snapshot.epochRevision,authorityRevision,dirty,flushAuthority,apply};
}
