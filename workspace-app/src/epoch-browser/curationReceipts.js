// This renderer's own confirmed main-protocol curation receipts (POST
// /protocols/<id>/curation, protocol-state contract with query_revision).
// A receipt proves two things only for the writer: the post-write curation of
// its epochs, and that its returned query revision is the sent revision plus
// that write. Pages already shown keep their rows and overlay the receipt; the
// next write sends the latest chained token. A page carrying any token outside
// the chain (another actor, a reload after other changes) clears the chain, so
// stale views still fail closed through the server's 409.
const text=value=>typeof value==='string'&&!!value;

export function validCurationReceipt(receipt,{protocolId,sentRevision,bindingVersion,epochUuids}){
  return !!receipt&&text(receipt.query_revision)&&Number.isSafeInteger(receipt.expected_binding_version)&&receipt.expected_binding_version===bindingVersion&&
    text(protocolId)&&text(sentRevision)&&receipt.curation&&typeof receipt.curation==='object'&&!Array.isArray(receipt.curation)&&
    Array.isArray(epochUuids)&&epochUuids.length>0&&epochUuids.every(uuid=>{const row=receipt.curation[uuid];
      return row&&typeof row==='object'&&typeof row.included==='boolean'&&Array.isArray(row.tags)&&text(row.review_state)&&Number.isSafeInteger(row.revision)&&row.revision>=0;});
}

export function createCurationReceipts({maxRows=4096}={}){
  const chains=new Map(),rows=new Map(),listeners=new Set();let version=0;
  const notify=()=>{version++;for(const listener of listeners)listener();};
  function clear(protocolId){
    if(!chains.delete(protocolId))return;
    for(const [uuid,row] of rows)if(row.protocolId===protocolId)rows.delete(uuid);
    notify();
  }
  return {
    // Returns false (and records nothing) when the receipt is not a complete,
    // matching receipt; callers then keep the reload path.
    record(protocolId,{sentRevision,bindingVersion,epochUuids,receipt}){
      if(!validCurationReceipt(receipt,{protocolId,sentRevision,bindingVersion,epochUuids}))return false;
      let chain=chains.get(protocolId);
      if(!chain||!chain.tokens.has(sentRevision)){clear(protocolId);chain={base:sentRevision,latest:sentRevision,tokens:new Set([sentRevision])};chains.set(protocolId,chain);}
      chain.tokens.add(receipt.query_revision);chain.latest=receipt.query_revision;
      for(const uuid of epochUuids){rows.delete(uuid);rows.set(uuid,{protocolId,curation:{...receipt.curation[uuid]}});}
      while(rows.size>maxRows)rows.delete(rows.keys().next().value);
      notify();return true;
    },
    // The token the next write must send for a page that showed `token`.
    latest(protocolId,token){const chain=chains.get(protocolId);return chain?.tokens.has(token)?chain.latest:token;},
    // Page tokens in one chain compare as the chain base; any other token is itself.
    canonical(protocolId,token){const chain=chains.get(protocolId);return chain?.tokens.has(token)?chain.base:token;},
    // A fresh page outside the chain retires it (and its row overlays).
    observe(protocolId,token){const chain=chains.get(protocolId);if(chain&&text(token)&&!chain.tokens.has(token))clear(protocolId);},
    apply(protocolId,epoch){
      const row=epoch?.epoch_uuid?rows.get(epoch.epoch_uuid):null;
      if(!row||row.protocolId!==protocolId)return epoch;
      return {...epoch,curation:{...(epoch.curation||{}),...row.curation}};
    },
    clear,
    subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
    version:()=>version,
  };
}
export const curationReceipts=createCurationReceipts();
