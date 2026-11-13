import {tagStore} from '../annotations/tagStore.js';
import {markVocabularyStale} from '../annotations/tagVocabulary.js';
import {epochResourceCache} from "../resourceCache.js";
import {useEffect,useRef} from 'react';
import {api} from "../api.js";
import {mutationUndo,shouldUndoData,undoEnabled,expandUndoAction} from './mutationUndo.js';
import {groupAnnotationRecovery} from "../group-save/groupAnnotationRecovery.js";
import {confirmGroupReceipt} from "../annotations/treeGroupQueryTags.js";
import {desktopBridge} from "../desktopLifecycle.js";

export async function persistUndo(input,request=api){
 const action=expandUndoAction(input);
 const options={method:'POST',undoOperation:true};
 if(action.kind==='protocol-membership'){
  const result=await request(`/protocols/${action.protocol_uuid}/membership/undo-remove`,{...options,body:{
   removal_revision_uuid:action.removal_revision_uuid,expected_binding_version:action.expected_binding_version}});
  if(result?.protocol_uuid!==action.protocol_uuid||result.binding?.version!==action.expected_binding_version+1||
    !Array.isArray(result.restored_epoch_uuids)||result.restored_epoch_uuids.length!==action.count||new Set(result.restored_epoch_uuids).size!==action.count){
   const error=Error('The membership restore receipt is incomplete. Refresh this protocol.');error.saved=true;throw error;
  }
  if(result.next_undo!=null&&(typeof result.next_undo.removal_revision_uuid!=='string'||
    result.next_undo.expected_binding_version!==result.binding.version)){
   const error=Error('The membership Undo continuation is incomplete. Refresh this protocol.');error.saved=true;throw error;
  }
  return {revisions:{},kind:'membership',protocolId:action.protocol_uuid,nextMembershipUndo:result.next_undo};
 }
 if(action.kind==='annotation_group'){
  // Keep this UUID in session history for recovery-unconfirmed retries.
  action.inverse_operation_uuid ||= crypto.randomUUID();
  const result=confirmGroupReceipt(await request(`/annotations/group/${action.operation_uuid}/undo`,{...options,body:{operation_uuid:action.inverse_operation_uuid}}),{action:'undo',operationUuid:action.inverse_operation_uuid,profileUuid:action.profile_uuid,count:action.count,forward:action.operation_uuid});
  epochResourceCache.invalidate();
  return {revisions:{},kind:'annotations'};
 }
 if(action.kind==='annotations'){
  const operations=action.operations.map(({before_revision,...row})=>row);
  const result=await request('/annotations/undo',{...options,body:{operations}});
  if(result?.persistence&&result.persistence.database!=='committed')throw Error('The inverse save was not confirmed committed.');
  if(result?.changed!==operations.length||!Array.isArray(result.annotations)||result.annotations.length!==operations.length)throw Error('The server did not confirm every original annotation target.');
  for(const operation of operations){const row=result.annotations.find(value=>value.target_uuid===operation.target_uuid&&value.target_kind===operation.target_kind&&value.profile_uuid===operation.profile_uuid);if(!row||row.revision!==operation.expected_revision+1||!Array.isArray(row.tags)||typeof row.author_name!=='string'||operation.tags_add?.some(tag=>!row.tags.includes(tag))||operation.tags_remove?.some(tag=>row.tags.includes(tag)))throw Error('The original annotation target was not confirmed restored.');}
  const revisions={};for(const row of result.annotations)revisions[`a:${row.target_kind}:${row.target_uuid}:${row.profile_uuid}`]=row.revision;
  const confirmed={version:1,targets:result.annotations.map(row=>({target_kind:row.target_kind,target_uuid:row.target_uuid,revisions:{[row.profile_uuid]:row.revision},tags:row.tags.map(tag=>({target_kind:row.target_kind,target_uuid:row.target_uuid,profile_uuid:row.profile_uuid,author_name:row.author_name,revision:row.revision,tag}))}))};
  epochResourceCache.invalidateAnnotations(confirmed);tagStore.ingest(confirmed);markVocabularyStale();
  return {revisions,kind:'annotations',confirmed};
 }
 if(action.kind!=='curation')throw Error('Unknown undo action');
 const ids=action.operations.map(row=>row.epoch_uuid);
 // Read only original targets at Undo time. Ordinary edits have no extra reads.
 const read=await request(`/protocols/${action.protocol_uuid}/curation/read`,{...options,body:{epoch_uuids:ids,selection_scope:{filters:{},cell_uuid:null},query_revision:null,expected_binding_version:null,undo_read:true}});
 for(const row of action.operations)if(read.epochs?.find(current=>current.epoch_uuid===row.epoch_uuid)?.curation_revision!==row.expected_revision)throw Error('An original target has changed since this edit.');
 const result=await request(`/protocols/${action.protocol_uuid}/curation`,{...options,body:{epoch_uuids:ids,query_revision:read.query_revision,expected_binding_version:read.expected_binding_version,changes:{},per_epoch_changes:Object.fromEntries(action.operations.map(row=>[row.epoch_uuid,row.changes])),expected_revisions:Object.fromEntries(action.operations.map(row=>[row.epoch_uuid,row.expected_revision]))}});
 const revisions={};for(const row of action.operations){const revision=result.curation?.[row.epoch_uuid]?.revision;if(!Number.isSafeInteger(revision)||revision!==row.expected_revision+1||Object.hasOwn(row.changes,'included')&&result.curation[row.epoch_uuid].included!==row.changes.included||row.changes.tags_add?.some(tag=>!result.curation[row.epoch_uuid].tags?.includes(tag))||row.changes.tags_remove?.some(tag=>result.curation[row.epoch_uuid].tags?.includes(tag)))throw Error('The inverse curation receipt is incomplete.');revisions[`c:${action.protocol_uuid}:${row.epoch_uuid}`]=revision;}
 return {revisions,kind:'curation'};
}
export function useMutationUndo(projectId,onChanged){
 const changed=useRef(onChanged);changed.current=onChanged;
 useEffect(()=>{mutationUndo.project(projectId);groupAnnotationRecovery.project(projectId);return groupAnnotationRecovery.onChange(event=>{if(event.project===projectId&&groupAnnotationRecovery.currentProject()===projectId)changed.current?.({kind:'annotations'});});},[projectId]);
 const run=async()=>mutationUndo.undo(async action=>{try{const result=await persistUndo(action);changed.current?.({kind:result.kind,confirmed:result.confirmed,...(result.protocolId?{protocolId:result.protocolId}:{})});return result;}catch(error){if(error.saved||action.kind==='protocol-membership')changed.current?.({kind:action.kind==='annotation_group'?'annotations':action.kind==='protocol-membership'?'membership':action.kind,...(action.kind==='protocol-membership'?{protocolId:action.protocol_uuid}:{})});throw error;}});
 const current=useRef(run);current.current=run;
 useEffect(()=>installUndoShortcuts({documentObject:document,bridge:desktopBridge(),run:()=>current.current(),enabled:undoEnabled}),[]);
 return {...mutationUndo.view(),enabled:undoEnabled,undo:run};
}

export function installUndoShortcuts({documentObject,bridge,run,enabled}){
 const receive=event=>{
  if(!enabled||event.defaultPrevented||event.isComposing||event.shiftKey||event.altKey||!(event.metaKey||event.ctrlKey)||event.key.toLowerCase()!=='z'||!shouldUndoData(event.target))return;
  event.preventDefault();event.stopImmediatePropagation();void run();
 };
 const nativeMenu=typeof bridge?.onUndo==='function';
 // Electron's accelerator owns the physical gesture. A later DOM event from
 // that same shortcut must never reverse a second, earlier scientific edit.
 if(!nativeMenu)documentObject.addEventListener('keydown',receive,true);
 const stop=bridge?.onUndo?.(()=>{if(enabled&&shouldUndoData(documentObject.activeElement))void run();else void bridge.undoText();});
 return()=>{if(!nativeMenu)documentObject.removeEventListener('keydown',receive,true);stop?.();};
}
