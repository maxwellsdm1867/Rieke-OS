import {incomingCellTypes} from './incomingCellTypes.js';

export function selectedSummaryIds(selected){
  if(!Array.isArray(selected)||selected.length>1000||selected.some(id=>typeof id!=='string'||!id)||new Set(selected).size!==selected.length)return null;
  return [...selected].sort();
}

export function validateSelectionSummary(value,ids,context){
  if(value?.candidate_scope_revision!==context.candidate_scope_revision||value.query_revision!==context.candidate_scope_revision||value.expected_binding_version!==context.expected_binding_version||
    !Array.isArray(value.epoch_uuids)||JSON.stringify(value.epoch_uuids)!==JSON.stringify(ids)||value.counts?.epochs!==ids.length||
    !Array.isArray(value.cells)||value.cells.length!==value.counts?.cells||value.cells.length>ids.length||ids.length>0&&!value.cells.length||
    value.cells.some(cell=>typeof cell?.cell_uuid!=='string'||!cell.cell_uuid||cell.cell_type!=null&&typeof cell.cell_type!=='string')||
    new Set(value.cells.map(cell=>cell.cell_uuid)).size!==value.cells.length||incomingCellTypes(value.cells,value.counts.cells)===null)
    throw Error('Selection details changed. Refresh the selection summary.');
  return value;
}
