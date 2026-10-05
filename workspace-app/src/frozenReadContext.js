import {predicateIdentity} from './typed-query/predicateIdentity.js';
// Frozen candidate reads never fall back to a current protocol/global endpoint.
export function frozenReadQuery(context,query=''){
 const params=new URLSearchParams(query);
 if(context){
  if(typeof context.root!=='string'||!/^\/protocols\/[^/]+\/workbench\/candidates\/[^/?]+$/.test(context.root)||typeof context.candidate_scope_revision!=='string'||!context.candidate_scope_revision)throw Error('Frozen candidate context is unavailable. Refresh the candidate.');
  params.set('candidate_scope_revision',context.candidate_scope_revision);
 }
 return params.toString();
}
export function frozenReadPath(context,protocolId,suffix,query=''){
 const params=frozenReadQuery(context,query);
 return `${context?.root||`/protocols/${protocolId}`}${suffix}${params?'?'+params:''}`;
}

export function candidatePreviewReceipt(result,request){
 const normalized=filters=>Object.fromEntries(Object.entries(filters||{}).map(([key,value])=>[key,['metadata_predicate','tag_predicate'].includes(key)?JSON.parse(value):value]));
 if(result?.candidate_scope_revision!==request.candidate_scope_revision||predicateIdentity(normalized(result?.filters))!==predicateIdentity(normalized(request.filters)))throw Error('Candidate preview authority changed. Refresh before previewing again.');
 const count=result.matched_count??result.counts?.epochs;
 if(!Number.isSafeInteger(count)||count<0)throw Error('Candidate counts unavailable.');
 return count;
}

// Presentation continuity is never a read or write receipt. Without an explicit
// frozen-cohort key, a token change resets the view as before.
export function frozenPresentationScope(context,protocolId,query=''){
 const params=new URLSearchParams(query);
 const cohort=typeof context?.cohort_key==='string'&&context.cohort_key?context.cohort_key:null;
 if(cohort)params.delete('candidate_scope_revision');
 return JSON.stringify([context?.root||`/protocols/${protocolId}`,protocolId,params.toString(),cohort]);
}
