import {epochPageRequest,epochPageRevision} from './epochBrowserSource.js';
import {MAX_SELECTED_EPOCHS} from './epochSelection.js';

// Use the same scoped cells as loadIncomingSelection; never use Main cell totals.
export function incomingSelectionCount({targets=[],cells=[],cell=null,epoch=null}){
  if(targets.length)return targets.every(id=>typeof id==='string'&&id)?new Set(targets).size:null;
  if(cell){
    const matching=cells.filter(item=>item.cell_uuid===cell.cell_uuid),count=matching[0]?.epochs;
    return matching.length===1&&Number.isSafeInteger(count)&&count>=0?count:null;
  }
  return epoch?(typeof epoch.epoch_uuid==='string'&&epoch.epoch_uuid?1:null):0;
}

// Capture the complete filtered frozen view before publishing any selection.
// Neither a loaded page nor a global cell query is a complete candidate set.
export async function loadIncomingSelection({source,cells,cellUuid=null,request,signal,isCurrent=()=>true}){
  if(!source?.readContext?.root||typeof source.queryRevision!=='string'||!source.queryRevision)throw new Error('Refresh the incoming view before selecting epochs.');
  const chosen=cellUuid?cells.filter(cell=>cell.cell_uuid===cellUuid):cells;
  if(cellUuid&&chosen.length!==1)throw new Error('This cell is no longer in the incoming view.');
  if(chosen.some(cell=>typeof cell.cell_uuid!=='string'||!Number.isSafeInteger(cell.epochs)||cell.epochs<0)||new Set(chosen.map(cell=>cell.cell_uuid)).size!==chosen.length)throw new Error('Complete incoming cell counts are unavailable. Refresh this view.');
  const count=chosen.reduce((total,cell)=>total+cell.epochs,0);
  if(count>MAX_SELECTED_EPOCHS)throw new Error('Select at most 1,000 epochs at a time. Filter this incoming view or choose a smaller cell.');
  const check=()=>{if(signal?.aborted||!isCurrent())throw new DOMException('Incoming selection changed. Select again.','AbortError');};
  const ids=[];
  for(const cell of chosen){
    for(let offset=0;offset<cell.epochs;offset+=60){
      check();const {path,options}=epochPageRequest(source,{cellUuid:cell.cell_uuid,offset});
      const page=await request(path,{...options,signal});check();epochPageRevision(source,page);
      if(page.total!==cell.epochs||page.offset!==offset||!Array.isArray(page.epochs)||page.epochs.length!==Math.min(60,cell.epochs-offset))throw new Error('The incoming cell changed while selecting. Refresh and select again.');
      for(const row of page.epochs){
        if(typeof row.epoch_uuid!=='string'||!row.epoch_uuid||row.cell_uuid!==cell.cell_uuid)throw new Error('The complete incoming selection could not be verified.');
        ids.push(row.epoch_uuid);
      }
    }
  }
  check();if(new Set(ids).size!==ids.length||ids.length!==count)throw new Error('The incoming selection contains duplicate or missing identities.');
  return ids;
}
