// Launch consent is ephemeral: preview by default, or exact source merge after a hold.
// History / desktop restoration cannot issue a new request through this ledger.
export function mergeIntentMatches(intent,projectId,protocolId){
  return (intent?.kind==='preview_all'||intent?.kind==='merge_source'&&typeof intent.candidate_revision_uuid==='string'&&!!intent.candidate_revision_uuid&&typeof intent.source_sha256==='string'&&!!intent.source_sha256)&&typeof intent.request_uuid==='string'&&!!intent.request_uuid&&typeof projectId==='string'&&!!projectId&&typeof protocolId==='string'&&!!protocolId&&intent.project_uuid===projectId&&intent.protocol_uuid===protocolId;
}
export function createIncomingMergeIntents(){
  const issued=new Map();
  return {
    issue(projectId,protocolId,options={}){
      if(typeof projectId!=='string'||!projectId||typeof protocolId!=='string'||!protocolId)return null;
      for(const intent of issued.values())if(mergeIntentMatches(intent,projectId,protocolId)&&intent.kind===(options.kind||'preview_all')&&intent.candidate_revision_uuid===options.candidate_revision_uuid&&intent.source_sha256===options.source_sha256)return intent;
      const intent={kind:options.kind==='merge_source'?'merge_source':'preview_all',...(options.kind==='merge_source'?{candidate_revision_uuid:options.candidate_revision_uuid,source_sha256:options.source_sha256}:{}),request_uuid:crypto.randomUUID(),project_uuid:projectId,protocol_uuid:protocolId};
      if(!mergeIntentMatches(intent,projectId,protocolId))return null;
      issued.set(intent.request_uuid,intent);return intent;
    },
    claim(intent,projectId,protocolId){
      const original=issued.get(intent?.request_uuid);issued.delete(intent?.request_uuid);
      return !!original&&JSON.stringify(original)===JSON.stringify(intent)&&mergeIntentMatches(intent,projectId,protocolId)&&mergeIntentMatches(original,projectId,protocolId);
    },
  };
}
