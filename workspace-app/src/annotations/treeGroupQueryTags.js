import {treePageRequest} from "../pagedTreeRequest.js";
import {groupAnnotationRecovery,createGroupSaveSession} from "../group-save/groupAnnotationRecovery.js";
export {confirmGroupReceipt} from "../group-save/groupAnnotationRecovery.js";

export function groupQueryScope(scope,path,revision){
  if(scope.readContext)throw Error('Shared group tags are not supported in Incoming Workbench yet.');
  const {offset,limit,...query}=treePageRequest(scope,{path,currentRevision:revision});
  return query;
}
export async function previewTreeGroup({scope,path,revision,count,profileUuid,request,signal}){
  const originalProject=groupAnnotationRecovery.currentProject();
  if(!profileUuid)throw Error('Choose a tag author profile, then reopen this group.');
  const result=await request('/annotations/group-preview',{method:'POST',signal,body:{scope:groupQueryScope(scope,path,revision),profile_uuid:profileUuid}});
  if(!result?.selection_uuid||result.target_kind!=='epoch'||result.count!==count||result.profile_uuid!==profileUuid||result.tree_revision!==revision)throw Error('The exact group changed or its preview was not confirmed. Reopen this group.');
  const mutation=createGroupSaveSession({project:originalProject,selectionUuid:result.selection_uuid,profileUuid,count:result.count,request});
  return Object.freeze({kind:'epoch',count:result.count,groupMutation:mutation,epoch:{epoch_uuid:result.selection_uuid,annotations:{epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}}});
}
export function releaseGroupPreview(target,request){
  return target?.groupMutation?.release();
}
