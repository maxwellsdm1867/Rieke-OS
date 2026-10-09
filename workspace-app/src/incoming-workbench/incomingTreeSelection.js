import {resolveTreeGroup} from '../annotations/treeGroupTargets.js';

// A single guarded server response replaces client-side descendant paging.
// Older candidate contexts keep the complete verified traversal fallback.
export async function resolveIncomingTreeSelection({scope,path,revision,count,request,signal}){
 if(!Number.isSafeInteger(count)||count<1)throw Error('Select a branch with an exact positive epoch count.');
 if(count>1000&&scope.readContext?.selection_manifests!==true)throw Error('Update the Workbench service to select more than 1,000 epochs.');
 if(scope.readContext?.tree_selection!==true)return (await resolveTreeGroup({scope,path,revision,count,request,signal})).ids;
 const context=scope.readContext;
 const value=await request(`${context.root}/tree/selection`,{method:'POST',signal,body:{candidate_scope_revision:context.candidate_scope_revision,revision,path,expected_count:count,...(context.selection_token?{selection_token:context.selection_token}:{}),filters:scope.filters||{},splits:scope.splits||''}});
 if(value?.revision!==revision||value.candidate_scope_revision!==context.candidate_scope_revision||value.query_revision!==context.candidate_scope_revision||
  !Number.isSafeInteger(value.expected_binding_version)||value.expected_binding_version<0||
  context.expected_binding_version!==undefined&&value.expected_binding_version!==context.expected_binding_version||
  JSON.stringify(value.path)!==JSON.stringify(path)||value.count!==count||!Array.isArray(value.epoch_uuids)||value.epoch_uuids.length!==count||
  value.epoch_uuids.some(id=>typeof id!=='string'||!id)||new Set(value.epoch_uuids).size!==count)
  throw Error('The complete branch selection changed. Refresh and select again.');
 return value.epoch_uuids;
}
