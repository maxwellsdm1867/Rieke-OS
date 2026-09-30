export const MAX_SELECTED_EPOCHS=1000;

export function toggleEpochSelection(selected,uuid){
  if(selected.includes(uuid))return selected.filter(key=>key!==uuid);
  if(selected.length>=MAX_SELECTED_EPOCHS)throw new Error('Select at most 1,000 epochs for one tag operation.');
  return [...selected,uuid];
}

export function mergeEpochSelection(selected,ids){
  const result=[...new Set([...selected,...ids])];
  if(result.length>MAX_SELECTED_EPOCHS)throw new Error('Select at most 1,000 epochs for one tag operation.');
  return result;
}

// Range order is the displayed date/cell order, then each cell's epoch order.
// Fetch intervening pages before publishing any selection, never a partial range.
export async function epochSelectionRange({cells,anchor,target,loadPage,pageRevision=page=>page.query_revision}){
  if(typeof anchor.revision!=='string'||!anchor.revision||target.revision!==anchor.revision)throw new Error('Epoch query changed. Refresh and select the range again.');
  const startCell=cells.findIndex(cell=>cell.cell_uuid===anchor.cellUuid);
  const endCell=cells.findIndex(cell=>cell.cell_uuid===target.cellUuid);
  if(startCell<0||endCell<0)throw new Error('The selection anchor is no longer in this view. Select an epoch again.');
  const reverse=startCell>endCell||(startCell===endCell&&anchor.index>target.index);
  const [first,last]=reverse?[target,anchor]:[anchor,target];
  const lo=Math.min(startCell,endCell),hi=Math.max(startCell,endCell);
  const spans=cells.slice(lo,hi+1).map(cell=>({cell,
    from:cell.cell_uuid===first.cellUuid?first.index:0,
    to:cell.cell_uuid===last.cellUuid?last.index:cell.epochs-1}));
  if(spans.some(({cell,from,to})=>!Number.isInteger(cell.epochs)||from<0||to>=cell.epochs||to<from))throw new Error('Epoch order changed. Select the range again.');
  if(spans.reduce((sum,span)=>sum+span.to-span.from+1,0)>MAX_SELECTED_EPOCHS)throw new Error('Select at most 1,000 epochs for one tag operation.');
  const ids=[];
  for(const {cell,from,to} of spans){
    for(let offset=Math.floor(from/60)*60;offset<=to;offset+=60){
      const page=await loadPage(cell.cell_uuid,offset);
      if(pageRevision(page)!==anchor.revision)throw new Error('Epoch query changed. Refresh and select the range again.');
      if(page.total!==cell.epochs||page.offset!==offset)throw new Error('Epoch order changed. Refresh and select the range again.');
      for(let index=Math.max(from,offset);index<=Math.min(to,offset+59);index++){
        const row=page.epochs[index-offset];
        if(!row?.epoch_uuid||row.cell_uuid!==cell.cell_uuid)throw new Error('The complete epoch range could not be loaded.');
        if((cell.cell_uuid===anchor.cellUuid&&index===anchor.index&&row.epoch_uuid!==anchor.uuid)||
           (cell.cell_uuid===target.cellUuid&&index===target.index&&row.epoch_uuid!==target.uuid))throw new Error('Epoch order changed. Select the range again.');
        ids.push(row.epoch_uuid);
      }
    }
  }
  if(new Set(ids).size!==ids.length)throw new Error('Duplicate epoch identities in selection range.');
  return ids;
}
