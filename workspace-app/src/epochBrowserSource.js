// Membership stays source-specific; the browser above this adapter is shared.
export function epochPageRequest(source,{offset=0,cellUuid=null,anchorUuid=null,includeCells=false}={}){
  if(source.kind==='protocol'){
    const query=new URLSearchParams(source.query);
    if(cellUuid)query.set('cell_uuid',cellUuid);
    query.set('limit',60);
    if(anchorUuid)query.set('anchor_uuid',anchorUuid);else query.set('offset',offset);
    return {path:`/protocols/${source.protocolId}/epochs?${query}`,options:{}};
  }
  if(source.kind!=='predicate')throw new Error('Unknown epoch browser source');
  return {path:'/explore/epochs',options:{method:'POST',body:{predicate:source.predicate,splits:source.splits,
    revision:source.treeRevision,limit:60,...(anchorUuid?{anchor_uuid:anchorUuid}:{offset}),
    ...(cellUuid?{cell_uuid:cellUuid}:{}),...(includeCells?{include_cells:true}:{})}}};
}
