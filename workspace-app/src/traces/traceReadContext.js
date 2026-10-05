// Candidate trace reads retain their frozen authority; never fall back globally.
export function traceRequestPath(epochUuid,stream,window,readContext=null){
 if(readContext&&(typeof readContext.root!=='string'||!/^\/protocols\/[^/]+\/workbench\/candidates\/[^/?]+$/.test(readContext.root)||typeof readContext.candidate_scope_revision!=='string'||!readContext.candidate_scope_revision))throw Error('Frozen candidate context is unavailable. Refresh the candidate.');
 if(!stream)return null;
 const query=new URLSearchParams({stream_uuid:stream.uuid,start:String(window.start),count:String(window.count)});
 if(readContext)query.set('candidate_scope_revision',readContext.candidate_scope_revision);
 return `${readContext?.root||''}/epochs/${epochUuid}/trace?${query}`;
}
export function traceCacheRevision(revision,readContext=null){
 return readContext?JSON.stringify([revision,readContext.root,readContext.candidate_scope_revision]):revision;
}
