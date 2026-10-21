// "Merged N epochs into <Protocol>. [Undo]" after any verified merge receipt.
// Undo is a separate explicit request bound to that receipt's operation and the
// binding version it produced; the server refuses (409) once Main has changed.
// One toast at a time: a newer merge replaces it, and a late reply to an older
// toast's undo can never overwrite the newer one.
const text=value=>typeof value==='string'&&!!value;
const count=value=>Number.isSafeInteger(value)&&value>=0;

export function mergeUndoTarget(receipt,{projectId,protocolName}={}){
  if(!text(projectId)||!text(receipt?.protocol_uuid)||!text(receipt.operation_uuid)||!text(receipt.event_uuid)||!Number.isSafeInteger(receipt.binding?.version)||!count(receipt.accepted_epoch_count))return null;
  return {projectId,protocolId:receipt.protocol_uuid,protocolName:text(protocolName)?protocolName:'this protocol',count:receipt.accepted_epoch_count,
    operationUuid:receipt.operation_uuid,bindingVersion:receipt.binding.version};
}

// The same Undo notice reverses review completion without changing Main.
function reviewUndoTarget(receipt,{projectId,protocolName}={}){
  if(receipt?.kind!=='workbench_review_completion'||!text(projectId)||!text(receipt.protocol_uuid)||!text(receipt.operation_uuid)||!text(receipt.candidate_revision_uuid)||!text(receipt.actor)||!Number.isSafeInteger(receipt.expected_draft_version)||!count(receipt.left_out_epoch_count))return null;
  return {kind:'review',projectId,protocolId:receipt.protocol_uuid,protocolName:text(protocolName)?protocolName:'this protocol',count:receipt.left_out_epoch_count,operationUuid:receipt.operation_uuid,draftVersion:receipt.expected_draft_version};
}

// Operations undone in this session; earlier-merge offers for them are stale.
// This is session memory only: after a reload the server refuses (409) an
// accepted export of an undone merge, and that refusal stays visible.
const undoneOperations=new Set(),undoneListeners=new Set(),protocolUndos=new Map();
const changes=new Map(),changeListeners=new Set(),publishedChanges=new Set();
export const protocolWorkbenchVersion=(projectId,protocolId)=>changes.get(JSON.stringify([projectId,protocolId]))?.version||0;
export function subscribeWorkbenchChanges(listener){changeListeners.add(listener);return()=>changeListeners.delete(listener);}
function changed({projectId,protocolId,operationUuid},binding,kind){
  const event=JSON.stringify([projectId,protocolId,operationUuid,kind]);
  if(publishedChanges.has(event))return;
  publishedChanges.add(event);
  const key=JSON.stringify([projectId,protocolId]),version=(changes.get(key)?.version||0)+1;
  changes.set(key,{version,binding,kind,operationUuid});
  for(const listener of [...changeListeners])listener();
}
export const mergeWasUndone=operationUuid=>undoneOperations.has(operationUuid);
export const mergeUndoneVersion=()=>undoneOperations.size;
export const protocolMergeUndoVersion=(projectId,protocolId)=>protocolUndos.get(JSON.stringify([projectId,protocolId]))||0;
/** Subscribe to undo completions (for example useSyncExternalStore). */
export function subscribeMergeUndone(listener){undoneListeners.add(listener);return()=>undoneListeners.delete(listener);}
function markUndone({operationUuid,projectId,protocolId}){
  if(undoneOperations.has(operationUuid))return;
  undoneOperations.add(operationUuid);
  const key=JSON.stringify([projectId,protocolId]);protocolUndos.set(key,(protocolUndos.get(key)||0)+1);
  for(const listener of [...undoneListeners])listener();
}

export function createMergeUndo({request,onState=()=>{},refresh=()=>{}}){
  let state=null,token=0;const listeners=new Set();
  const publish=next=>{state=next;onState(state);for(const listener of listeners)listener(state);};
  return {
    get state(){return state;},
    subscribe(listener){listeners.add(listener);listener(state);return()=>listeners.delete(listener);},
    setRefresh(next){refresh=next;},
    // Returns false when the receipt cannot identify an undoable merge.
    show(receipt,details){
      const target=reviewUndoTarget(receipt,details)||mergeUndoTarget(receipt,details);
      if(!target)return false;
      changed(target,receipt.binding,target.kind==='review'?'finish':'merge');
      token++;publish({...target,phase:'merged',message:'',canUndo:target.count>0});return true;
    },
    dismiss(){if(state?.phase==='undoing')return;token++;publish(null);},
    async undo(){
      if(!state||state.phase!=='merged'||!state.canUndo)return false;
      const current=state,mine=++token;
      publish({...current,phase:'undoing',message:current.kind==='review'?'Restoring pending review…':'Undoing merge…',canUndo:false});
      try{
        const review=current.kind==='review';
        const value=await request(`/protocols/${encodeURIComponent(current.protocolId)}/workbench/${review?'undo-review':'undo'}`,{method:'POST',body:review?{operation_uuid:current.operationUuid,expected_draft_version:current.draftVersion}:{operation_uuid:current.operationUuid,expected_binding_version:current.bindingVersion}});
        if(review?value?.kind!=='workbench_review_undo'||value.undone_operation_uuid!==current.operationUuid||value.protocol_uuid!==current.protocolId||!count(value.restored_epoch_count):!text(value?.binding?.revision_uuid)||!Number.isSafeInteger(value.binding.version)||!text(value.restored_revision_uuid))throw Object.assign(Error('The undo reply was incomplete. Check Activity & logs before trying again.'),{uncertain:true});
        markUndone(current);
        changed(current,value.binding,'undo');
        // Read reconciliation cannot turn a verified Undo into a failed write.
        try{await refresh(current.protocolId);}catch{}
        if(mine===token)publish({...current,phase:'undone',message:current.kind==='review'?'Review reopened':'Merge undone',canUndo:false,removed:count(value.removed_epoch_count)?value.removed_epoch_count:null});
        return true;
      }catch(error){
        // 409: Main changed since this merge; nothing was undone. Any other
        // failure may or may not have committed, so refresh and never retry.
        const refused=error?.status===409;
        if(!refused)refresh(current.protocolId);
        if(mine===token)publish({...current,phase:'error',canUndo:false,message:refused?error.message:`Undo may not have completed. ${error.message}`});
        return false;
      }
    },
  };
}
