// Candidate and imported reads retain exact authority; never fall back globally.
const snapshotFields=['kind','project_uuid','publication_revision','scope_data_revision','protocol_uuid','source_sha256','processing_version'];
const cellSnapshotFields=['kind','project_uuid','cell_uuid','publication_revision','processing_version','epoch_uuid','source_sha256'];
const preparedFields=['kind','token','project_uuid','publication_revision','view_kind','protocol_uuid','candidate_revision_uuid','membership_sha256'];
const unavailablePrepared=()=>{throw Error('Prepared trace display is unavailable. Refresh the captured view.');};
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
function prepared(context){
 if(context?.kind!=='prepared_display')return null;
 if(Object.keys(context).length!==preparedFields.length||preparedFields.some(key=>!Object.hasOwn(context,key))||
    ['token','project_uuid','publication_revision','protocol_uuid','candidate_revision_uuid'].some(key=>typeof context[key]!=='string'||!uuid.test(context[key]))||
    !['workbench_pending','workbench_selected'].includes(context.view_kind)||typeof context.membership_sha256!=='string'||!/^[0-9a-f]{64}$/.test(context.membership_sha256))unavailablePrepared();
 return preparedFields.map(key=>context[key]);
}

// Display selection only. Never put the returned capability in tree queries or
// mutation receipts. Undefined means a legacy backend; null means wait for an
// advertised selected view's own page capability, never borrow its parent view.
export function selectPreparedTraceContext({page,context,selected=false,projectUuid,protocolUuid,candidateUuid}){
 const offered=!!page&&Object.hasOwn(page,'trace_read_context');
 if(!offered&&context===undefined)return undefined;
 const validate=value=>{
  if(!prepared(value)||value.project_uuid!==projectUuid||value.protocol_uuid!==protocolUuid||value.candidate_revision_uuid!==candidateUuid)unavailablePrepared();
  return value;
 };
 if(context!==undefined)validate(context);
 const chosen=offered?validate(page.trace_read_context):selected?null:context===undefined?null:context;
 if(chosen&&chosen.view_kind!==(selected?'workbench_selected':'workbench_pending'))unavailablePrepared();
 if(chosen&&context!==undefined&&(chosen.publication_revision!==context.publication_revision||!selected&&chosen.token!==context.token))return null;
 return chosen;
}

export function traceRequestPath(epochUuid,stream,window,readContext=null){
 const imported=snapshot(readContext),display=prepared(readContext);
 if(readContext&&!imported&&!display&&(typeof readContext.root!=='string'||!/^\/protocols\/[^/]+\/workbench\/candidates\/[^/?]+$/.test(readContext.root)||typeof readContext.candidate_scope_revision!=='string'||!readContext.candidate_scope_revision))throw Error('Frozen candidate context is unavailable. Refresh the candidate.');
 if(readContext?.kind==='imported_cell_snapshot'&&readContext.epoch_uuid!==epochUuid)throw Error('Imported cell epoch authority does not match the selected epoch.');
 if(!stream)return null;
 if(display&&(!uuid.test(epochUuid)||!uuid.test(stream.uuid)||!Number.isSafeInteger(window.start)||window.start<0||!Number.isSafeInteger(window.count)||window.count<1||window.count>100000))throw Error('Invalid prepared trace window identity.');
 if(imported&&(!uuid.test(epochUuid)||!uuid.test(stream.uuid)||!Number.isSafeInteger(window.start)||window.start<0||!Number.isSafeInteger(window.count)||window.count<1||window.count>20000))throw Error('Invalid imported trace window identity.');
 const query=new URLSearchParams({stream_uuid:stream.uuid,start:String(window.start),count:String(window.count)});
 if(display)return `/trace-views/${readContext.token}/epochs/${epochUuid}/trace?${query}`;
 if(imported){
  const cell=readContext.kind==='imported_cell_snapshot',fields=cell?cellSnapshotFields:snapshotFields;
  for(const key of fields.filter(key=>!['kind','protocol_uuid','cell_uuid','epoch_uuid'].includes(key)))query.set(key,readContext[key]);
  return cell?`/snapshot/cells/${readContext.cell_uuid}/epochs/${epochUuid}/trace?${query}`:`/snapshot/protocols/${readContext.protocol_uuid}/epochs/${epochUuid}/trace?${query}`;
 }
 if(readContext)query.set('candidate_scope_revision',readContext.candidate_scope_revision);
 return `${readContext?.root||''}/epochs/${epochUuid}/trace?${query}`;
}
export function traceCacheRevision(revision,readContext=null){
 const imported=snapshot(readContext),display=prepared(readContext);
 if(display)return JSON.stringify(display);
 return imported?JSON.stringify([revision,...imported]):readContext?JSON.stringify([revision,readContext.root,readContext.candidate_scope_revision]):revision;
}
export function traceResponseMatches(data,readContext=null){
 const imported=snapshot(readContext),display=prepared(readContext);
 if(display){try{return !Object.hasOwn(data??{},'candidate_scope_revision')&&JSON.stringify(prepared(data?.read_context))===JSON.stringify(display);}catch{return false;}}
 if(!imported)return data?.read_context?.kind!=='prepared_display';
 try{return JSON.stringify(snapshot(data?.read_context))===JSON.stringify(imported);}catch{return false;}
}
