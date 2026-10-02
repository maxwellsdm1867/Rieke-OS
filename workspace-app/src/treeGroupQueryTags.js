import {treePageRequest} from './pagedTreeRequest.js';
import {mutationUndo,undoEnabled} from './mutationUndo.js';
import {epochResourceCache} from './resourceCache.js';

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
  if(!profileUuid)throw Error('Choose a tag author profile, then reopen this group.');
  const result=await request('/annotations/group-preview',{method:'POST',signal,body:{scope:groupQueryScope(scope,path,revision),profile_uuid:profileUuid}});
  if(!result?.selection_uuid||result.target_kind!=='epoch'||result.count!==count||result.profile_uuid!==profileUuid||result.tree_revision!==revision)throw Error('The exact group changed or its preview was not confirmed. Reopen this group.');
  const attempts=new Map();let unresolved=null;
  const mutation={selectionUuid:result.selection_uuid,profileUuid,count:result.count,async save({tag,profileUuid:author}){
    if(author!==profileUuid)throw Error('The author profile changed. Reopen this group.');
    if(unresolved&&unresolved!==tag)throw Error('Retry the unconfirmed tag with the same operation before saving another tag.');
    if(!attempts.has(tag))attempts.set(tag,{selection_uuid:result.selection_uuid,profile_uuid:profileUuid,tag,operation_uuid:crypto.randomUUID()});
    const body=attempts.get(tag),token=undoEnabled?mutationUndo.begin():null;
    unresolved=tag;
    try{
      const receipt=confirmGroupReceipt(await request('/annotations/group',{method:'POST',body}),{operationUuid:body.operation_uuid,profileUuid,count:result.count,tag});
      unresolved=null;epochResourceCache.invalidate();
      if(token)mutationUndo.complete(token,{...receipt.undo,profile_uuid:profileUuid});
      return receipt;
    }catch(error){if(token)mutationUndo.complete(token,null);throw error;}
  }};
  return Object.freeze({kind:'epoch',count:result.count,groupMutation:mutation,epoch:{epoch_uuid:result.selection_uuid,annotations:{epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}}});
}
export function releaseGroupPreview(target,request){
  if(target?.groupMutation)return request('/annotations/group-preview-release',{method:'POST',body:{selection_uuid:target.groupMutation.selectionUuid}}).catch(()=>{});
}
