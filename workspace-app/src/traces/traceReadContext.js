// Candidate and imported reads retain exact authority; never fall back globally.
const snapshotFields=['kind','project_uuid','publication_revision','scope_data_revision','protocol_uuid','source_sha256','processing_version'];
const cellSnapshotFields=['kind','project_uuid','cell_uuid','publication_revision','processing_version','epoch_uuid','source_sha256'];
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function snapshot(context){
 if(!['imported_snapshot','imported_cell_snapshot'].includes(context?.kind))return null;
 const fields=context.kind==='imported_cell_snapshot'?cellSnapshotFields:snapshotFields;
 const identities=context.kind==='imported_cell_snapshot'?['project_uuid','cell_uuid','publication_revision','epoch_uuid']:['project_uuid','publication_revision','scope_data_revision','protocol_uuid'];
 if(Object.keys(context).length!==fields.length||fields.some(key=>!Object.hasOwn(context,key))||
    identities.some(key=>typeof context[key]!=='string'||!uuid.test(context[key]))||
    typeof context.source_sha256!=='string'||!/^[0-9a-f]{64}$/.test(context.source_sha256)||
    typeof context.processing_version!=='string'||!context.processing_version||new TextEncoder().encode(context.processing_version).length>128)
  throw Error('Imported snapshot authority is unavailable. Refresh the saved view.');
 return fields.map(key=>context[key]);
}
export function traceRequestPath(epochUuid,stream,window,readContext=null){
 const imported=snapshot(readContext);
 if(readContext&&!imported&&(typeof readContext.root!=='string'||!/^\/protocols\/[^/]+\/workbench\/candidates\/[^/?]+$/.test(readContext.root)||typeof readContext.candidate_scope_revision!=='string'||!readContext.candidate_scope_revision))throw Error('Frozen candidate context is unavailable. Refresh the candidate.');
 if(readContext?.kind==='imported_cell_snapshot'&&readContext.epoch_uuid!==epochUuid)throw Error('Imported cell epoch authority does not match the selected epoch.');
 if(!stream)return null;
 if(imported&&(!uuid.test(epochUuid)||!uuid.test(stream.uuid)||!Number.isSafeInteger(window.start)||window.start<0||!Number.isSafeInteger(window.count)||window.count<1||window.count>20000))throw Error('Invalid imported trace window identity.');
 const query=new URLSearchParams({stream_uuid:stream.uuid,start:String(window.start),count:String(window.count)});
 if(imported){
  const cell=readContext.kind==='imported_cell_snapshot',fields=cell?cellSnapshotFields:snapshotFields;
  for(const key of fields.filter(key=>!['kind','protocol_uuid','cell_uuid','epoch_uuid'].includes(key)))query.set(key,readContext[key]);
  return cell?`/snapshot/cells/${readContext.cell_uuid}/epochs/${epochUuid}/trace?${query}`:`/snapshot/protocols/${readContext.protocol_uuid}/epochs/${epochUuid}/trace?${query}`;
 }
 if(readContext)query.set('candidate_scope_revision',readContext.candidate_scope_revision);
 return `${readContext?.root||''}/epochs/${epochUuid}/trace?${query}`;
}
export function traceCacheRevision(revision,readContext=null){
 const imported=snapshot(readContext);
 return imported?JSON.stringify([revision,...imported]):readContext?JSON.stringify([revision,readContext.root,readContext.candidate_scope_revision]):revision;
}
export function traceResponseMatches(data,readContext=null){
 const imported=snapshot(readContext);
 if(!imported)return true;
 try{return JSON.stringify(snapshot(data?.read_context))===JSON.stringify(imported);}catch{return false;}
}
