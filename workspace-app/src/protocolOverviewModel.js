export function isTypingProtocol(protocol){
  const definition=protocol.definition||protocol;
  const name=protocol.acquisition_protocol||definition.name||'';
  return /^(SingleSpot|ExpandingSpots|SplitFieldCentering)$/i.test(name.split('.').pop().replace(/\s+/g,''));
}
export function recordingStorage(inventory,sourceIds){
  const ids=new Set(sourceIds||[]),sources=new Map((inventory||[]).filter(source=>ids.has(source.source_sha256)).map(source=>[source.source_sha256,source]));
  let bytes=0,unknown=0;
  for(const id of ids){const source=sources.get(id);if(source?.file_status==='available'&&Number.isFinite(source.size_bytes)&&source.size_bytes>=0)bytes+=source.size_bytes;else unknown++;}
  return {bytes:unknown?null:bytes,knownBytes:bytes,unknown,sources:ids.size};
}
export function sizeLabel(bytes){if(!Number.isFinite(bytes))return '—';if(bytes<1000)return `${bytes} B`;if(bytes<1e6)return `${(bytes/1000).toFixed(1)} KB`;if(bytes<1e9)return `${(bytes/1e6).toFixed(1)} MB`;return `${(bytes/1e9).toFixed(2)} GB`;}

// Count identities, not epoch totals or cell labels reused on different dates.
export function protocolCellTypes(cells=[]){
  const types=new Map(),seen=new Set();
  for(const cell of cells){
    const id=cell.cell_uuid||cell.uuid;
    if(id&&seen.has(id))continue;
    if(id)seen.add(id);
    const recordedType=String(cell.cell_type||cell.type||'').trim();
    const type=!recordedType||/^(unclassified|unknown|not recorded)$/i.test(recordedType)?'Unclassified':recordedType;
    const row=types.get(type)||{type,count:0,withExports:0};
    row.count++;
    if(cell.exported>0)row.withExports++;
    types.set(type,row);
  }
  return [...types.values()].sort((a,b)=>b.count-a.count||a.type.localeCompare(b.type));
}

export function protocolCellSummary(cells=[]){
  const types=protocolCellTypes(cells);
  return {types,matchingCells:types.reduce((sum,row)=>sum+row.count,0),cellTypes:types.filter(row=>row.type!=='Unclassified').length,unclassifiedCells:types.find(row=>row.type==='Unclassified')?.count||0};
}
