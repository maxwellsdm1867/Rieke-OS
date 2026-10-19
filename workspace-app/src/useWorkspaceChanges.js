import {useCallback,useLayoutEffect,useRef,useState} from 'react';

// Tag/curation edits invalidate live scientific views immediately. Project
// registration, import discovery and metadata status have separate lifetimes.
// Confirmed epoch or cell receipts are applied in place by the tag store
// (cell tags overlay every epoch row of that cell).
const confirmedReceipt=event=>event?.kind==='annotations'&&event.confirmed?.version===1&&
  Array.isArray(event.confirmed.targets)&&event.confirmed.targets.length>0;
const confirmedEpochReceipt=event=>confirmedReceipt(event)&&event.confirmed.targets.every(target=>['epoch','cell'].includes(target.target_kind));
const protocolOf=event=>typeof event?.protocolId==='string'&&event.protocolId?event.protocolId:null;

export const INITIAL_WORKSPACE_CHANGES=Object.freeze({revision:0,structureRevision:0,reviewRevision:0,contentRevision:0,membershipRevision:0,protocols:Object.freeze({}),members:Object.freeze({}),summaries:Object.freeze({}),last:null});

// Typed change kinds (additive; untyped events keep the original clocks):
//  {kind:'membership', protocolId}  merge-all/undo/finish/accept/apply for one
//    protocol: advances only that protocol's clock plus the content and
//    membership counters. Global display, structure and review clocks stay.
//  {kind:'curation', protocolId}    curation receipts for one protocol: that
//    protocol's clock and the content counter only.
//    With receipt:true (applied in place) it advances only that protocol's
//    summary counter and the content counter.
//  {kind:'structure'}               imports, sources, bindings: every clock.
// Confirmed tag receipts and tag-channel events stay off these clocks. These are
// local integer clocks, never receipts, scientific readiness or write authority;
// writes keep their own expected revisions.
export function applyWorkspaceChange(previous,event){
  const tagChannel=event?.kind==='annotations'&&event.tagChannel===true;
  if(confirmedEpochReceipt(event)||tagChannel)return previous;
  const protocolId=protocolOf(event),seq=(previous.last?.seq||0)+1;
  // A curation receipt applied in place re-keys no page or tree: only that
  // protocol's summaries (and project summaries via contentRevision) refresh.
  if(event?.kind==='curation'&&event.receipt===true&&protocolId)
    return {...previous,summaries:{...previous.summaries,[protocolId]:(previous.summaries[protocolId]||0)+1},
      contentRevision:previous.contentRevision+1,last:{seq,kind:'curation-receipt',protocolId}};
  if((event?.kind==='membership'||event?.kind==='curation')&&protocolId){
    const membership=event.kind==='membership';
    return {...previous,protocols:{...previous.protocols,[protocolId]:(previous.protocols[protocolId]||0)+1},
      members:membership?{...previous.members,[protocolId]:(previous.members[protocolId]||0)+1}:previous.members,
      contentRevision:previous.contentRevision+1,membershipRevision:previous.membershipRevision+(membership?1:0),
      last:{seq,kind:event.kind,protocolId}};
  }
  const structural=event?.kind==='structure'||!['annotations','curation'].includes(event?.kind);
  return {...previous,
    revision:previous.revision+1,
    structureRevision:structural?previous.structureRevision+1:previous.structureRevision,
    reviewRevision:confirmedReceipt(event)?previous.reviewRevision:previous.reviewRevision+1,
    last:{seq,kind:structural?'structure':event?.kind,protocolId:null}};
}
// One protocol's display/review clocks: the global clock plus that protocol's
// typed counter, so a change to protocol A never re-keys protocol B's reads.
// Sums of monotonic counters: any change yields a new, larger number, so the
// clocks stay valid equality keys and numeric comparisons.
export function protocolClock(base,state,protocolId){return base+(state.protocols[protocolId]||0);}

export function useWorkspaceChanges(){
  const [state,setState]=useState(INITIAL_WORKSPACE_CHANGES);
  const changed=useCallback(event=>setState(previous=>applyWorkspaceChange(previous,event)),[]);
  const protocolRevision=useCallback(protocolId=>protocolClock(state.revision,state,protocolId),[state]);
  const protocolReviewRevision=useCallback(protocolId=>protocolClock(state.reviewRevision,state,protocolId),[state]);
  // Membership of one protocol (binding/query descriptor), never curation.
  const protocolMembershipRevision=useCallback(protocolId=>state.members[protocolId]||0,[state]);
  const protocolSummaryRevision=useCallback(protocolId=>state.summaries[protocolId]||0,[state]);
  return {...state,
    // Project-wide readers whose content follows protocol membership/curation.
    dataRevision:state.revision+state.contentRevision,
    protocolRevision,protocolReviewRevision,protocolMembershipRevision,protocolSummaryRevision,changed};
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
