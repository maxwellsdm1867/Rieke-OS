import {curationReceipts} from './curationReceipts.js';
import {frozenReadPath,frozenReadQuery} from './frozenReadContext.js';
// Membership stays source-specific; the browser above this adapter is shared.
// Predicate pages may bound the cell list: cellsLimit cells per window, starting
// after cellsAfter cells already received (the previous response's cells_next).
export function epochPageRequest(source,{offset=0,cellUuid=null,anchorUuid=null,includeCells=false,cellsLimit=null,cellsAfter=null}={}){
  if(source.kind==='protocol'){
    const query=new URLSearchParams(source.query);
    if(cellUuid)query.set('cell_uuid',cellUuid);
    query.set('limit',source.pageSize??60);
    if(includeCells){query.set('include_cells','true');if(cellsLimit&&!source.readContext){query.set('cells_limit',cellsLimit);if(cellsAfter)query.set('cells_after',cellsAfter);}}
    if(anchorUuid)query.set('anchor_uuid',anchorUuid);else query.set('offset',offset);
    return {path:frozenReadPath(source.readContext,source.protocolId,'/epochs',query.toString()),options:{}};
  }
  if(source.kind!=='predicate')throw new Error('Unknown epoch browser source');
  return {path:'/explore/epochs',options:{method:'POST',body:{predicate:source.predicate,splits:source.splits,
    revision:source.treeRevision,limit:source.pageSize??60,...(anchorUuid?{anchor_uuid:anchorUuid}:{offset}),
    ...(cellUuid?{cell_uuid:cellUuid}:{}),...(includeCells?{include_cells:true}:{}),
    ...(includeCells&&cellsLimit?{cells_limit:cellsLimit,...(cellsAfter?{cells_after:cellsAfter}:{})}:{})}}};
}

// Protocol pages carry the authoritative query/curation receipt; predicate
// pages carry the frozen explorer membership receipt. These are distinct APIs.
export function epochPageRevision(source,page){
  const protocol=source.kind==='protocol';
  if(!protocol&&source.kind!=='predicate')throw new Error('Unknown epoch browser source');
  // Main protocol pages compare through this renderer's own curation receipt
  // chain (curationReceipts): a page read after our write equals the shown one.
  const chained=protocol&&!source.readContext,same=value=>chained?curationReceipts.canonical(source.protocolId,value):value;
  const actual=protocol?page?.query_revision:page?.revision;
  const expected=protocol?source.queryRevision:source.treeRevision;
  if(typeof actual!=='string'||!actual)throw new Error('The epoch list could not be verified. Reload the list.');
  if(expected!==undefined&&expected!==null&&same(actual)!==same(expected))throw Object.assign(new Error('The epoch list is out of date. Reload the list.'),{code:'epoch_list_stale'});
  return same(actual);
}
