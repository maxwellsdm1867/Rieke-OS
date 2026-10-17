import {useCallback,useLayoutEffect,useRef,useState} from 'react';

// Tag/curation edits invalidate live scientific views immediately. Project
// registration, import discovery and metadata status have separate lifetimes.
// Confirmed epoch or cell receipts are applied in place by the tag store
// (cell tags overlay every epoch row of that cell).
const confirmedEpochReceipt=event=>event?.kind==='annotations'&&event.confirmed?.version===1&&
  Array.isArray(event.confirmed.targets)&&event.confirmed.targets.length>0&&event.confirmed.targets.every(target=>['epoch','cell'].includes(target.target_kind));

export function useWorkspaceChanges(){
  const [state,setState]=useState({revision:0,structureRevision:0});
  // Confirmed epoch-tag receipts travel on the tag channel (annotations/tagStore),
  // not this clock: the App does not re-render, and tag-dependent views renew
  // from the store's confirmed generation. Everything else still ticks here.
  const changed=useCallback(event=>setState(previous=>confirmedEpochReceipt(event)||event?.kind==='annotations'&&event.tagChannel===true?previous:({
    revision:previous.revision+1,
    structureRevision:['annotations','curation'].includes(event?.kind)?previous.structureRevision:previous.structureRevision+1,
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
