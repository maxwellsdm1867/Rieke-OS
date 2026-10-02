export const workbenchRoot=protocol=>`/protocols/${encodeURIComponent(protocol)}/workbench`;
export const workbenchCandidateRoot=(protocol,revision)=>`${workbenchRoot(protocol)}/candidates/${encodeURIComponent(revision)}`;
export function requireWorkbenchQueue(value){
  if(value?.contract_version!==1||!Array.isArray(value.candidates)||typeof value.queue_revision!=='string')throw new Error('The cumulative review service is unavailable or has an unsupported contract.');
  if(!value.capabilities||!['frozen_browse','drafts','additive_accept','incoming_export'].every(key=>typeof value.capabilities[key]==='boolean'))throw new Error('The queue did not declare its supported review capabilities.');
  for(const key of ['pending_cell_count','pending_epoch_count'])if(!Number.isSafeInteger(value[key])||value[key]<0)throw new Error('The queue did not return authoritative pending counts.');
  if(value.candidates.some(item=>typeof item.candidate_revision_uuid!=='string'))throw new Error('The queue contains an invalid immutable candidate identity.');
  return value;
}
export function requireWorkbenchContext(value){
  if(typeof value?.candidate_scope_revision!=='string'||!value.candidate_scope_revision||!Number.isSafeInteger(value.draft?.draft_version))throw new Error('A complete frozen scope and draft receipt is required. Refresh this proposal.');
  return value;
}
export async function saveWorkbenchDecisions({root,context,decisions=[],deferred,selectionMode},request,onCommitted=()=>{}){
  requireWorkbenchContext(context);
  if(decisions.some(item=>typeof item.epoch_uuid!=='string'))throw new Error('Review decisions require exact epoch UUIDs.');
  let current=context;
  const batches=[];
  for(let offset=0;offset<decisions.length;offset+=250)batches.push(decisions.slice(offset,offset+250));
  if(!batches.length)batches.push([]);
  for(const batch of batches){
    const body={expected_version:current.draft.draft_version,expected_candidate_scope_revision:current.candidate_scope_revision,decisions:batch,...(typeof deferred==='boolean'?{deferred}:{}),...(selectionMode?{selection_mode:selectionMode}:{})};
    current=requireWorkbenchContext(await request(`${root}/draft`,{method:'PATCH',body}));
    onCommitted(current);
  }
  return current;
}
export async function previewWorkbench(root,context,mode,request){
  requireWorkbenchContext(context);
  if(!['selected','all'].includes(mode))throw new Error('Choose selected additions or all eligible additions.');
  const value=await request(`${root}/preview`,{method:'POST',body:{expected_candidate_scope_revision:context.candidate_scope_revision,expected_draft_version:context.draft.draft_version,mode}});
  if(typeof value.preview_sha256!=='string'||!Number.isSafeInteger(value.expected_binding_version)||typeof value.expected_query_revision!=='string')throw new Error('The additive preview did not return complete acceptance fences.');
  return {...value,mode,expected_candidate_scope_revision:context.candidate_scope_revision,expected_draft_version:context.draft.draft_version};
}
export async function acceptWorkbench(root,preview,operationUuid,request){
  if(typeof operationUuid!=='string'||!operationUuid)throw new Error('A stable operation identity is required for acceptance.');
  const receipt=await request(`${root}/accept`,{method:'POST',body:{expected_candidate_scope_revision:preview.expected_candidate_scope_revision,expected_draft_version:preview.expected_draft_version,mode:preview.mode,preview_sha256:preview.preview_sha256,expected_binding_version:preview.expected_binding_version,expected_query_revision:preview.expected_query_revision,operation_uuid:operationUuid}});
  if(!receipt.binding?.revision_uuid||!Number.isSafeInteger(receipt.binding.version)||!receipt.event_uuid)throw new Error('Acceptance receipt is incomplete. Check this operation before retrying.');
  return receipt;
}
export function selectionDecisions(previous,next){
  const selected=new Set(next);
  return [...new Set([...previous,...next])].map(epoch_uuid=>({epoch_uuid,selected:selected.has(epoch_uuid)}));
}
export function acceptanceFailureKind(error){
  return [400,404,409,422].includes(error?.status)&&error?.saved!==true?'rejected':'unconfirmed';
}
