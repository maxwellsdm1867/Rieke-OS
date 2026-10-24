// Visible tree demand may prepare its exact display scope once after a 202.
// Preparation does not renew query/review authority: the next read retains its
// expected revision, and frozen review contexts remain owned by their caller.
export async function prepareTree(scope,{request,signal,isCurrent=()=>true}){
 if(scope.readContext)throw Error('This tree must be refreshed by its review owner.');
 const body={...(scope.protocolId?{protocol_uuid:scope.protocolId}:{predicate:scope.predicate||{all:[]}}),filters:scope.filters||{},splits:scope.splits||''};
 await request('/tree-pages/prepare',{method:'POST',body,signal});
 if(signal?.aborted||!isCurrent())throw Object.assign(Error('Tree preparation superseded'),{name:'AbortError'});
}
