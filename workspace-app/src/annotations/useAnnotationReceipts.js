import {useCallback,useEffect,useState} from 'react';
import {annotationFilterNeedsRefresh} from './annotationReceipts.js';
import {tagStore} from './tagStore.js';
import {useDeferredTagVersion,useTagGeneration} from './useTagStore.js';

export const ANNOTATION_AUTHORITY_IDLE_MS=75;

// Page authority for epoch-browser views, separated from tag display.
// Tags arrive on the tag channel and are overlaid in place (apply). Page/tree
// authority renews from confirmed tags only when the result depends on them:
// tag filters, or legacy pages whose revision still covers shared tags
// (protocol-state-v4 tokens do not). A burst renews once, after it is idle;
// pending (unconfirmed) tags never renew authority.
export function useAnnotationReceipts({revision,filters,stableAuthority=false}){
  const tagVersion=useDeferredTagVersion(),tagGeneration=useTagGeneration();
  const tagDependent=annotationFilterNeedsRefresh(filters)||!stableAuthority;
  const [settled,setSettled]=useState(tagGeneration);
  const dirty=tagDependent&&settled!==tagGeneration;
  useEffect(()=>{
    if(settled===tagGeneration)return;
    if(!tagDependent){setSettled(tagGeneration);return;}
    const timer=setTimeout(()=>setSettled(tagGeneration),ANNOTATION_AUTHORITY_IDLE_MS);return()=>clearTimeout(timer);
  },[tagGeneration,settled,tagDependent]);
  const flushAuthority=useCallback(()=>setSettled(tagStore.getConfirmedGeneration()),[]);
  const authorityRevision=tagDependent?JSON.stringify([revision,settled]):revision;
  const apply=useCallback(epoch=>tagStore.apply(epoch),[tagVersion]);
  return {epochRevision:revision,authorityRevision,dirty,kept:false,flushAuthority,apply};
}

// Frozen Workbench trees show shared-tag coverage and leaf tag markers from their
// pages, while their read token omits shared tags. Re-read loaded pages once per
// confirmed tag burst (after it is idle); 0 when disabled, so other trees never
// re-read for a tag.
export function useTagCoverageRevision(enabled){
  const tagGeneration=useTagGeneration();
  const [settled,setSettled]=useState(tagGeneration);
  useEffect(()=>{
    if(!enabled||settled===tagGeneration)return;
    const timer=setTimeout(()=>setSettled(tagGeneration),ANNOTATION_AUTHORITY_IDLE_MS);return()=>clearTimeout(timer);
  },[enabled,tagGeneration,settled]);
  return enabled?settled:0;
}
