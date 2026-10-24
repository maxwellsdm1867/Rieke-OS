// Read the explicit binding state. An omitted field is not a live-query protocol.
export function protocolDatasetStatus(data){
  const binding=data.binding,version=data.expected_binding_version;
  const saved=!!binding?.revision_uuid&&(version===undefined||version===binding.version);
  const live=binding===null&&(version===undefined||version===0);
  const state=saved?'saved':live?'live':'unknown';
  const query=saved?(data.effective_query??(binding.predicate?{version:2,kind:'source_predicate',predicate:binding.predicate}:null)):live?(data.effective_query??data.definition?.query):null;
  return {state,query,filtered:Object.keys(data.filters||{}).length>0};
}
