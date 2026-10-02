import {treePageRequest} from './pagedTreeRequest.js';
import {groupAnnotationRecovery,retainGroupOperation,runGroupOperation} from './groupAnnotationRecovery.js';

export function groupQueryScope(scope,path,revision){
  if(scope.readContext)throw Error('Shared group tags are not supported in Incoming Workbench yet.');
  const {offset,limit,...query}=treePageRequest(scope,{path,currentRevision:revision});
  return query;
}
export function confirmGroupReceipt(result,{operationUuid,profileUuid,count,tag,action='add',forward}){
  if(result?.format!=='rieke-group-annotation-receipt'||result.version!==1||result.action!==action||result.operation_uuid!==operationUuid||result.target_kind!=='epoch'||result.target_count!==count||result.profile_uuid!==profileUuid||!Number.isSafeInteger(result.changed)||result.changed<0||result.changed>count||result.unchanged!==count-result.changed||result.persistence&&result.persistence.database!=='committed'||action==='add'&&(result.tag!==tag||result.undo?.kind!=='annotation_group'||result.undo.operation_uuid!==operationUuid||result.undo.count!==result.changed)||action==='undo'&&result.forward_operation_uuid!==forward)throw Error('The complete group receipt was not confirmed. Retry the same operation before another tag.');
  return result;
}
export async function previewTreeGroup({scope,path,revision,count,profileUuid,request,signal}){
  const originalProject=groupAnnotationRecovery.currentProject();
  if(!profileUuid)throw Error('Choose a tag author profile, then reopen this group.');
  const result=await request('/annotations/group-preview',{method:'POST',signal,body:{scope:groupQueryScope(scope,path,revision),profile_uuid:profileUuid}});
  if(!result?.selection_uuid||result.target_kind!=='epoch'||result.count!==count||result.profile_uuid!==profileUuid||result.tree_revision!==revision)throw Error('The exact group changed or its preview was not confirmed. Reopen this group.');
  let operation=null,releaseRequested=false,released=false;
  const release=()=>{
    releaseRequested=true;
    if(released||operation&&['pending','unconfirmed','ready'].includes(operation.status))return;
    released=true;
    return request('/annotations/group-preview-release',{method:'POST',body:{selection_uuid:result.selection_uuid}}).catch(()=>{});
  };
  const mutation={selectionUuid:result.selection_uuid,profileUuid,count:result.count,release,canPublish:()=>originalProject===groupAnnotationRecovery.currentProject(),async save({tag,profileUuid:author}){
    if(originalProject!==groupAnnotationRecovery.currentProject())throw Error('Return to the original project before saving this group.');
    if(author!==profileUuid)throw Error('The author profile changed. Reopen this group.');
    if(operation&&operation.body.tag!==tag)throw Error('Retry the original unconfirmed tag or reopen after its refusal before saving another tag.');
    if(!operation){
      const body={selection_uuid:result.selection_uuid,profile_uuid:profileUuid,tag,operation_uuid:crypto.randomUUID()};
      operation=retainGroupOperation({body,count:result.count,request,confirm:receipt=>confirmGroupReceipt(receipt,{operationUuid:body.operation_uuid,profileUuid,count:result.count,tag}),onTerminal:()=>{if(releaseRequested)void release();}});
    }
    return runGroupOperation(operation);
  }};
  return Object.freeze({kind:'epoch',count:result.count,groupMutation:mutation,epoch:{epoch_uuid:result.selection_uuid,annotations:{epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}}});
}
export function releaseGroupPreview(target,request){
  return target?.groupMutation?.release();
}
