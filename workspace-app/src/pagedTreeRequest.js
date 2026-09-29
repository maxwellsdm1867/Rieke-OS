export function treePageRequest(scope,{path=[],offset=0,anchor=null,reset=false,currentRevision=null}={}){
  const body={...(scope.protocolId?{protocol_uuid:scope.protocolId}:{predicate:scope.predicate||{all:[]}}),filters:scope.filters||{},splits:scope.splits||'',path:anchor?[]:path,offset:anchor?0:offset,limit:60};
  const revision=scope.expectedRevision||(!reset?currentRevision:null);
  if(revision)body.revision=revision;
  if(anchor)body.anchor_uuid=anchor;
  return body;
}
export function treeNavigationSnapshot(page,scrollTop=0){
  return {path:[...page.path],offset:page.offset,revision:page.revision,split_order:[...page.split_order],scrollTop:Number.isFinite(scrollTop)?Math.max(0,scrollTop):0};
}
export function treeNavigationStart(saved,splits){
  if(!saved||!Array.isArray(saved.path)||saved.path.length>8||!saved.path.every(key=>typeof key==='string'&&/^[0-9a-f]{64}$/.test(key))||!Number.isSafeInteger(saved.offset)||saved.offset<0||typeof saved.revision!=='string'||!/^[0-9a-f]{64}$/.test(saved.revision)||saved.split_order?.join(',')!==splits)return null;
  return {path:saved.path,offset:saved.offset,revisionOverride:saved.revision,scrollTop:Number.isFinite(saved.scrollTop)?Math.max(0,saved.scrollTop):0};
}
