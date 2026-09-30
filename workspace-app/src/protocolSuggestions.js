import {IMPORT_TERMINAL,jobProgressView} from './importProgress.js';
export function pendingProtocolSuggestions(data){
  const rows=Array.isArray(data?.suggestions)?data.suggestions:[];
  return rows.filter(item=>item.status==='pending'&&typeof item.protocol_uuid==='string'&&typeof item.candidate_revision_uuid==='string');
}
export function activeProtocolSuggestions(data){
  const rows=Array.isArray(data?.suggestions)?data.suggestions:[];
  return rows.filter(item=>['pending','stale'].includes(item.status)&&typeof item.protocol_uuid==='string'&&typeof item.candidate_revision_uuid==='string');
}
export function suggestionBadge(suggestion){
  if(suggestion.status==='stale')return 'Refresh';
  const cells=suggestion.diff_summary?.delta?.cells;
  const added=suggestion.diff_counts?.added;
  if(Number.isInteger(cells)&&cells>0)return `+${cells} ${cells===1?'cell':'cells'}`;
  if(Number.isInteger(added)&&added>0)return `+${added} ${added===1?'epoch':'epochs'}`;
  return 'Update';
}
export function importCompletionKey(jobs=[]){
  return (Array.isArray(jobs)?jobs:[]).filter(job=>job&&IMPORT_TERMINAL.has(job.status))
    .map(job=>`${job.job_uuid}:${job.status}:${job.finished_at || ''}`).sort().join('|');
}
export function sameSuggestionComparison(left,right){
  const baseline=left.expected_binding_version ?? left.baseline_binding_version;
  if(!Number.isInteger(baseline)||baseline!==right.expected_binding_version)return false;
  if(left.expected_query_revision!==undefined&&left.expected_query_revision!==right.expected_query_revision)return false;
  for(const key of ['added','removed','changed'])if(left.diff_counts?.[key]!==right.diff_counts?.[key])return false;
  for(const key of ['cells','epochs','acquisition_protocols']){
    for(const scope of ['current','proposed'])if(left.diff_summary?.[scope]?.[key]!==right.diff_summary?.[scope]?.[key])return false;
  }
  return true;
}

export function importAttemptNotice(job){
  const state=jobProgressView(job);
  if(state.interrupted&&state.committed)return {pending:false,failed:false,message:'Recording imported; follow-up work was interrupted. Review diagnostics before retrying any work.'};
  if(state.failed===false&&state.warning&&job.status==='failed')return {pending:false,failed:false,message:'Recording imported; follow-up work failed. Review diagnostics before retrying any work.'};
  if(job.status==='interrupted')return {pending:false,failed:true,message:'Import was interrupted. Check the catalog and diagnostic record before submitting again; commit state may be unconfirmed.'};
  if(job.status==='complete_with_warnings')return {pending:false,failed:false,message:'Recording imported; follow-up checks need attention. Review the import diagnostics below.'};
  if(['complete','completed','success'].includes(job.status))return {pending:false,failed:false,message:'Recording imported into the main catalog. Add matched data to protocol datasets using the suggestions below.'};
  if(job.status==='duplicate')return {pending:false,failed:false,message:'This recording was already imported. No duplicate data was added.'};
  if(['failed','failure'].includes(job.status))return {pending:false,failed:true,message:'Import failed. See the diagnostic details in import history below.'};
  return {pending:true,failed:false,message:job.status==='queued'?'Import attempt queued. Duplicate checking and validation results appear below.':'Import is running. Its current checks and results appear in import history below.'};
}

// A bulk approval uses exactly the same compare/version gate as an individual
// approval. A changed comparison is returned for review, never silently applied.
export async function approveProtocolSuggestion(suggestion,shown,request){
  const root=`/explore/revisions/${suggestion.candidate_revision_uuid}`;
  const fresh=await request(`${root}/compare-to-protocol`,{method:'POST',body:{protocol_uuid:suggestion.protocol_uuid}});
  if(!Number.isInteger(fresh.expected_binding_version)||typeof fresh.expected_query_revision!=='string')throw new Error('The comparison did not include a valid dataset version. Refresh this protocol before retrying.');
  if(!sameSuggestionComparison(shown,fresh))return {comparison:fresh,applied:false};
  const receipt=await request(`${root}/apply-to-protocol`,{method:'POST',body:{protocol_uuid:suggestion.protocol_uuid,expected_binding_version:fresh.expected_binding_version,expected_query_revision:fresh.expected_query_revision}});
  if(receipt.binding?.revision_uuid!==suggestion.candidate_revision_uuid||!Number.isInteger(receipt.binding?.version))throw new Error('The update did not return a complete receipt. Check Activity & logs before retrying.');
  return {applied:true,receipt};
}
