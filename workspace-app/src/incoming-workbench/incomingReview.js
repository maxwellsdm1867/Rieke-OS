import {activeProtocolSuggestions,sameSuggestionComparison} from "../protocol-overview/protocolSuggestions.js";

export const reviewKey = item => `${item.protocol_uuid}:${item.candidate_revision_uuid}`;
export const reviewSessionKey = (project,id) => `incoming-review:${project}:${id}`;
export function reviewWorklist(data,selected=[]){
  const ids=new Set(selected);
  return activeProtocolSuggestions(data).filter(item=>ids.has(reviewKey(item)));
}
export function acceptedBinding(comparison,item){
  const binding=comparison?.binding;
  return binding?.revision_uuid===item.candidate_revision_uuid&&Number.isInteger(binding.version)?binding:null;
}
// Receipt publication precedes export. A retry with this receipt cannot rebind.
// An ambiguous apply failure must be reconciled using a fresh comparison first.
export async function acceptIncoming(item,shown,request){
  const root=`/explore/revisions/${item.candidate_revision_uuid}`;
  const comparison=await request(`${root}/compare-to-protocol`,{method:'POST',body:{protocol_uuid:item.protocol_uuid}});
  const binding=acceptedBinding(comparison,item);
  if(binding)return {receipt:{binding},reconciled:true};
  if(!comparison.compatibility?.compatible)throw new Error('The saved candidate does not match this acquisition Protocol ID. Review the comparison.');
  if(!Number.isInteger(comparison.expected_binding_version)||typeof comparison.expected_query_revision!=='string')throw new Error('A complete dataset comparison is required before accepting.');
  if(!sameSuggestionComparison(shown,comparison))return {comparison};
  let receipt;
  try{
    receipt=await request(`${root}/apply-to-protocol`,{method:'POST',body:{protocol_uuid:item.protocol_uuid,expected_binding_version:comparison.expected_binding_version,expected_query_revision:comparison.expected_query_revision}});
    if(!acceptedBinding(receipt,item))throw new Error('Acceptance did not return a complete binding receipt.');
  }catch(error){error.acceptanceUnconfirmed=true;throw error;}
  return {receipt};
}
export async function exportIncoming(candidate,{format,name},request){
  const expected=candidate.recipe?.full_recipe_sha256||candidate.recipe?.content_sha256;
  if(!expected||!candidate.revision_uuid)throw new Error('Reload the immutable candidate before exporting.');
  const receipt=await request(`/explore/revisions/${candidate.revision_uuid}/exports`,{method:'POST',body:{format,expected_recipe_sha256:expected,...(name?.trim()?{name:name.trim()}:{})}});
  if(!receipt.dataset_uuid||!receipt.download_url)throw new Error('Export did not return a complete artifact receipt. Check export history before retrying.');
  return receipt;
}

// Each cell is assigned exactly one disjoint change group by the authority.
// Do not count truncated lists, epoch totals, or sum overlapping proposals.
export function currentProposalCellCount(item){
  const counts=item?.diff_summary?.cell_changes?.counts;
  if(!counts||!['added','removed','updated'].every(key=>Number.isInteger(counts[key])&&counts[key]>=0))return null;
  return counts.added+counts.removed+counts.updated;
}
export function currentProposalCellBadge(item){
  if(item.status==='stale')return 'Refresh';
  const count=currentProposalCellCount(item);
  return count===null?'Review':`${count} ${count===1?'cell':'cells'}`;
}

export function pendingReviewBadge(suggestion,summary){
  if(Number.isSafeInteger(summary?.pending_cell_count)&&summary.pending_cell_count>=0){
    const count=summary.pending_cell_count;
    return count?`${count} ${count===1?'cell':'cells'}`:'';
  }
  return suggestion?.status==='stale'?'Refresh':suggestion?'Review':'';
}
