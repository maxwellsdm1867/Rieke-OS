import {useCallback,useLayoutEffect,useRef,useState} from 'react';

// Tag/curation edits invalidate live scientific views immediately. Project
// registration, import discovery and metadata status have separate lifetimes.
const confirmedReceipt=event=>event?.kind==='annotations'&&event.confirmed?.version===1&&
  Array.isArray(event.confirmed.targets)&&event.confirmed.targets.length>0;
const confirmedEpochReceipt=event=>confirmedReceipt(event)&&event.confirmed.targets.every(target=>target.target_kind==='epoch');

export function useWorkspaceChanges(){
  const [state,setState]=useState({revision:0,structureRevision:0,reviewRevision:0});
  // Confirmed epoch-tag receipts travel on the tag channel (annotations/tagStore),
  // not this clock: the App does not re-render, and tag-dependent views renew
  // from the store's confirmed generation. Everything else still ticks here.
  // reviewRevision drives the frozen Workbench: its candidate scope omits shared
  // tags, so no confirmed tag receipt (epoch or cell) reloads it; frozen rows
  // overlay the receipt from the tag store. Receipt-less tag events still tick.
  const changed=useCallback(event=>setState(previous=>{
    const tagChannel=event?.kind==='annotations'&&event.tagChannel===true;
    if(confirmedEpochReceipt(event)||tagChannel)return previous;
    return {
      revision:previous.revision+1,
      structureRevision:['annotations','curation'].includes(event?.kind)?previous.structureRevision:previous.structureRevision+1,
      reviewRevision:confirmedReceipt(event)?previous.reviewRevision:previous.reviewRevision+1,
    };
  }),[]);
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
