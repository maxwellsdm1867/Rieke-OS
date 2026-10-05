import {mutationUndo,undoEnabled} from "../undo/mutationUndo.js";
import {epochResourceCache} from '../resourceCache.js';

// Session-only, at most four compact original requests. Never evict an
// unconfirmed operation or retain the server's target list/annotation graphs.
const MAX_PENDING=4,MAX_RECORD_BYTES=16*1024;
const records=new Map(),listeners=new Set(),changes=new Set();
let project=null,version=0;
const emit=()=>{version++;for(const listener of listeners)listener();};
const notify=record=>{epochResourceCache.invalidate();for(const listener of changes)listener({project:record.project,kind:'annotations'});};
/**
 * Renderer-session recovery singleton. Project changes select publication authority;
 * they do not clear retained operations. Views expose compact copies, never records.
 * Retry preserves the original request; only terminal rejected rows may be dismissed.
 * See AGENTS.md and the colocated executable public example for caller obligations.
 */
export const groupAnnotationRecovery={
 subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},version:()=>version,
 project(value){project=value;emit();},currentProject:()=>project,
 view:()=>[...records.values()].map(row=>({operation_uuid:row.body.operation_uuid,project:row.project,profile_uuid:row.body.profile_uuid,tag:row.body.tag,count:row.count,status:row.status,error:row.error||''})),
 dismiss(operation){const record=records.get(operation);if(record?.status!=='rejected')throw Error('Confirm the original operation before dismissing it.');records.delete(operation);emit();},
 onChange(listener){changes.add(listener);return()=>changes.delete(listener);},
 async retry(operation){const record=records.get(operation);if(!record)throw Error('The original operation is no longer pending.');return run(record,true);},
};
/**
 * Return the same complete receipt or throw when its identity/arithmetic is unconfirmed.
 * Missing persistence is accepted; a supplied database state must be committed.
 * This check does not establish backend transaction or recovery-copy durability.
 */
export function confirmGroupReceipt(result,{operationUuid,profileUuid,count,tag,action='add',forward}){
  if(result?.format!=='rieke-group-annotation-receipt'||result.version!==1||result.action!==action||result.operation_uuid!==operationUuid||result.target_kind!=='epoch'||result.target_count!==count||result.profile_uuid!==profileUuid||!Number.isSafeInteger(result.changed)||result.changed<0||result.changed>count||result.unchanged!==count-result.changed||result.persistence&&result.persistence.database!=='committed'||action==='add'&&(result.tag!==tag||result.undo?.kind!=='annotation_group'||result.undo.operation_uuid!==operationUuid||result.undo.count!==result.changed)||action==='undo'&&result.forward_operation_uuid!==forward)throw Error('The complete group receipt was not confirmed. Retry the same operation before another tag.');
  return result;
}

/**
 * Create a frozen save/release/canPublish handle from an already verified preview.
 * The caller supplies the project captured before the preview request began and its
 * existing request adapter. First save reserves one of four compact recovery slots;
 * the conservative per-request admission limit is 16 KiB, not total heap usage.
 * Uncertain saves must retry the original tag/profile. Release is best effort and
 * deferred while ready/pending/unconfirmed; it never cancels a submitted write.
 * A retained handle survives editor dismissal. Check canPublish before publishing.
 * @param {{project: *, selectionUuid: string, profileUuid: string, count: number,
 *   request: function(string, Object): Promise<*>}} options
 * @returns {Readonly<{selectionUuid: string, profileUuid: string, count: number,
 *   save: function(Object): Promise<*>, release: function(): *, canPublish: function(): boolean}>}
 */
export function createGroupSaveSession({project:originalProject,selectionUuid,profileUuid,count,request}){
  let operation=null,releaseRequested=false,released=false;
  const release=()=>{
    releaseRequested=true;
    if(released||operation&&['pending','unconfirmed','ready'].includes(operation.status))return;
    released=true;
    return request('/annotations/group-preview-release',{method:'POST',body:{selection_uuid:selectionUuid}}).catch(()=>{});
  };
  const mutation={selectionUuid,profileUuid,count,release,canPublish:()=>originalProject===groupAnnotationRecovery.currentProject(),async save({tag,profileUuid:author}){
    if(originalProject!==groupAnnotationRecovery.currentProject())throw Error('Return to the original project before saving this group.');
    if(author!==profileUuid)throw Error('The author profile changed. Reopen this group.');
    if(operation&&operation.body.tag!==tag)throw Error('Retry the original unconfirmed tag or reopen after its refusal before saving another tag.');
    if(!operation){
      const body={selection_uuid:selectionUuid,profile_uuid:profileUuid,tag,operation_uuid:crypto.randomUUID()};
      operation=retainGroupOperation({body,count,request,confirm:receipt=>confirmGroupReceipt(receipt,{operationUuid:body.operation_uuid,profileUuid,count,tag}),onTerminal:()=>{if(releaseRequested)void release();}});
    }
    return run(operation,false);
  }};
  return Object.freeze(mutation);
}

function retainGroupOperation({body,count,request,confirm,onTerminal}){
 if(records.size>=MAX_PENDING)throw Error('Resolve an earlier group save before starting another; four unconfirmed operations are retained.');
 const exact=Object.freeze({...body});
 if(JSON.stringify(exact).length*4+4096>MAX_RECORD_BYTES)throw Error('The original group request exceeds recovery memory admission.');
 const record={body:exact,count,project,request,confirm,onTerminal,status:'ready',error:'',pending:null,result:null};
 records.set(exact.operation_uuid,record);emit();
 return record;
}
async function run(record,recovery){
 if(record.result)return record.result;
 if(record.status==='rejected'||records.get(record.body.operation_uuid)!==record)throw Error('This refused operation is terminal. Reopen the group for a new preview.');
 if(record.project!==project)throw Error('Return to the original project to retry this group operation.');
 if(record.pending)return record.pending;
 const token=undoEnabled?mutationUndo.begin():null;
 record.status='pending';record.error='';emit();
 const pending=(async()=>{
  try{
   const receipt=record.confirm(await Promise.resolve().then(()=>record.request('/annotations/group',{method:'POST',body:record.body})));
   record.result=receipt;record.status='confirmed';records.delete(record.body.operation_uuid);
   epochResourceCache.invalidate();
   if(token)mutationUndo.complete(token,{...receipt.undo,profile_uuid:record.body.profile_uuid});
   if(recovery)notify(record);
   record.onTerminal?.();return receipt;
  }catch(error){
   if(token)mutationUndo.complete(token,null);
   record.error=String(error.message).slice(0,1024);
   if(!error.saved&&[400,409].includes(error.status)){
    record.status='rejected';record.onTerminal?.();
   }else record.status='unconfirmed';
   if(error.saved)notify(record);
   throw error;
  }finally{record.pending=null;emit();}
 })();
 record.pending=pending;return pending;
}
