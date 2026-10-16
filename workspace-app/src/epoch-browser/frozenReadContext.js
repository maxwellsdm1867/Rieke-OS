import {predicateIdentity} from '../typed-query/predicateIdentity.js';
import {annotationFilterNeedsRefresh} from '../annotations/annotationReceipts.js';
// Frozen candidate reads never fall back to a current protocol/global endpoint.
export function frozenReadQuery(context,query=''){
 const params=new URLSearchParams(query);
 if(context){
  if(typeof context.root!=='string'||!/^\/protocols\/[^/]+\/workbench\/candidates\/[^/?]+$/.test(context.root)||typeof context.candidate_scope_revision!=='string'||!context.candidate_scope_revision)throw Error('Frozen candidate context is unavailable. Refresh the candidate.');
  params.set('candidate_scope_revision',context.candidate_scope_revision);
  if(context.selection_token)params.set('selection_token',context.selection_token);
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
 const selectedView=cohort&&typeof context?.selection_view_key==='string'&&context.selection_view_key?context.selection_view_key:null;
 if(selectedView)params.delete('selection_token');
 return JSON.stringify([context?.root||`/protocols/${protocolId}`,protocolId,params.toString(),cohort,...(selectedView?[selectedView]:[])]);
}

// A stable cohort can retain navigation through tag/draft authority refreshes.
// Annotation-dependent membership or grouping still needs fresh navigation.
// This key is never sent to a read or command endpoint as authority.
export function frozenTreePresentationScope({projectId,protocolId,readContext,filters={},splits='',predicate,expectedRevision}){
 if(!readContext?.cohort_key||predicate||annotationFilterNeedsRefresh(filters)||typeof splits!=='string'
   ||splits.split(',').some(field=>/^(annotations\/|curation\/|tag$|tags$)/.test(field)))return null;
 return JSON.stringify([projectId??null,readContext.actor??null,
   frozenPresentationScope(readContext,protocolId,new URLSearchParams(filters).toString()),splits,expectedRevision??null]);
}
