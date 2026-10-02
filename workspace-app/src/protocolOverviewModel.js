import {distinctCells,recordedCellType,isUnclassifiedType} from './cellTypes.js';
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

export const validCellCount=value=>Number.isSafeInteger(value)&&value>=0;
export const validRecordedDuration=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;

// The summary DTO partitions current epoch UUIDs by cell UUID. Its `exported`
// field intersects that membership with a SET of saved-export epoch UUIDs;
// summing it here never sums export receipts or counts an epoch twice.
// A missing field poisons only that metric, rather than presenting a partial sum.
export function aggregateCellTypes(cells=[]){
  const groups=new Map();
  for(const cell of distinctCells(cells)){
    if(!(cell.cell_uuid||cell.uuid))continue;
    const type=recordedCellType(cell);
    const group=groups.get(type)||{type,count:0,cells:[],epochs:0,duration_seconds:0,exported:0,included:0,reviewed:0,withExports:0};
    group.cells.push(cell);group.count++;
    for(const field of ['epochs','duration_seconds','exported','included','reviewed']){
      const valid=field==='duration_seconds'?validRecordedDuration:validCellCount;
      group[field]=group[field]!==null&&valid(cell[field])&&valid(group[field]+cell[field])?group[field]+cell[field]:null;
    }
    group.withExports=group.withExports!==null&&validCellCount(cell.exported)?group.withExports+(cell.exported>0?1:0):null;
    groups.set(type,group);
  }
  return [...groups.values()].sort((a,b)=>b.count-a.count||a.type.localeCompare(b.type));
}

// Count identities, not epoch totals or cell labels reused on different dates.
export function protocolCellTypes(cells=[]){
  const types=new Map();
  for(const cell of distinctCells(cells)){
    const type=recordedCellType(cell);
    const row=types.get(type)||{type,count:0,withExports:0};
    row.count++;
    if(cell.exported>0)row.withExports++;
    types.set(type,row);
  }
  return [...types.values()].sort((a,b)=>b.count-a.count||a.type.localeCompare(b.type));
}

export function protocolCellSummary(cells=[]){
  const types=protocolCellTypes(cells);
  return {types,matchingCells:types.reduce((sum,row)=>sum+row.count,0),cellTypes:types.filter(row=>!isUnclassifiedType(row.type)).length,unclassifiedCells:types.filter(row=>isUnclassifiedType(row.type)).reduce((sum,row)=>sum+row.count,0)};
}
