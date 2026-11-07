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

// Select all or one cell in the current filtered pinned view. Collect every
// bounded page before publishing; a partial cell list is never the whole set.
export async function loadProtocolSelection({source,request,cellUuid=null,signal,isCurrent=()=>true}){
  if(source?.kind!=='protocol'||source.readContext||!source.queryRevision||!Number.isSafeInteger(source.bindingVersion))throw Error('Refresh the protocol before selecting epochs.');
  const query=new URLSearchParams(source.query);query.set('selection_receipt','true');
  const scoped={...source,query:query.toString(),pageSize:60},ids=[];let total=null,selectionRevision=null;
  const check=()=>{if(signal?.aborted||!isCurrent())throw new DOMException('Selection or dataset changed. Select again.','AbortError');};
  for(let offset=0;total===null||offset<total;offset+=60){
    check();const {path,options}=epochPageRequest(scoped,{cellUuid,offset});
    const page=await request(path,{...options,signal});check();epochPageRevision(scoped,page);
    if(typeof page.selection_revision!=='string'||!page.selection_revision||
      (selectionRevision!==null&&page.selection_revision!==selectionRevision))throw Error('The filtered selection changed. Refresh and select again.');
    selectionRevision=page.selection_revision;
    if(!Number.isSafeInteger(page.total)||page.total<0||page.expected_binding_version!==source.bindingVersion||page.offset!==offset||
      (total!==null&&page.total!==total)||!Array.isArray(page.epochs)||page.epochs.length!==Math.min(60,Math.max(0,page.total-offset)))throw Error('The complete selection could not be verified. Refresh and select again.');
    if(page.total>1000)throw Error('Select at most 1,000 epochs at a time. Choose a cell or narrow the filters.');
    total=page.total;
    for(const row of page.epochs){
      if(typeof row.epoch_uuid!=='string'||!row.epoch_uuid||(cellUuid&&row.cell_uuid!==cellUuid))throw Error('The complete selection could not be verified.');
      ids.push(row.epoch_uuid);
    }
  }
  check();if(ids.length!==total||new Set(ids).size!==total)throw Error('The selection contains duplicate or missing epochs.');
  return ids;
}
