// Launch intent is ephemeral consent to PREVIEW, never authority to accept.
// History / desktop restoration cannot issue a new request through this ledger.
export function mergeIntentMatches(intent,projectId,protocolId){
  return intent?.kind==='preview_all'&&typeof intent.request_uuid==='string'&&!!intent.request_uuid&&typeof projectId==='string'&&!!projectId&&typeof protocolId==='string'&&!!protocolId&&intent.project_uuid===projectId&&intent.protocol_uuid===protocolId;
}
export function createIncomingMergeIntents(){
  const issued=new Map();
  return {
    issue(projectId,protocolId){
      if(typeof projectId!=='string'||!projectId||typeof protocolId!=='string'||!protocolId)return null;
      for(const intent of issued.values())if(mergeIntentMatches(intent,projectId,protocolId))return intent;
      const intent={kind:'preview_all',request_uuid:crypto.randomUUID(),project_uuid:projectId,protocol_uuid:protocolId};
      issued.set(intent.request_uuid,intent);return intent;
    },
    claim(intent,projectId,protocolId){
      const original=issued.get(intent?.request_uuid);issued.delete(intent?.request_uuid);
      return !!original&&mergeIntentMatches(intent,projectId,protocolId)&&mergeIntentMatches(original,projectId,protocolId);
    },
  };
}
