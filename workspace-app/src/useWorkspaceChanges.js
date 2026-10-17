import {useCallback,useLayoutEffect,useRef,useState} from 'react';

// Tag/curation edits invalidate live scientific views immediately. Project
// registration, import discovery and metadata status have separate lifetimes.
const confirmedEpochReceipt=event=>event?.kind==='annotations'&&event.confirmed?.version===1&&
  Array.isArray(event.confirmed.targets)&&event.confirmed.targets.length>0&&event.confirmed.targets.every(target=>target.target_kind==='epoch');

export function useWorkspaceChanges(){
  const [state,setState]=useState({revision:0,structureRevision:0,readOwnerRevision:0,annotationChange:null});
  const changed=useCallback(event=>setState(previous=>({
    revision:previous.revision+1,
    structureRevision:['annotations','curation'].includes(event?.kind)?previous.structureRevision:previous.structureRevision+1,
    // Shared read owners are self-validated by server revisions. A confirmed
    // epoch-tag receipt is applied in place; views whose data depends on tags
    // renew through their own authority instead of retiring every read.
    readOwnerRevision:confirmedEpochReceipt(event)?previous.readOwnerRevision:previous.readOwnerRevision+1,
    annotationChange:event?.kind==='annotations'&&event.confirmed?.version===1?{...event,revision:previous.revision+1}:null,
  })),[]);
  return {...state,changed};
}

// A hidden summary keeps its last successful display revision until it is
// shown. Structural changes still refresh it so navigation and source ownership
// remain current. Live pages and edit authority never use this deferred clock.
export function useSummaryRevision(revision,visible,structureRevision=revision){
  const committed=useRef({revision,structureRevision});
  const next=visible||committed.current.structureRevision!==structureRevision?{revision,structureRevision}:committed.current;
  useLayoutEffect(()=>{committed.current=next;},[next.revision,next.structureRevision]);
  return next.revision;
}
