import {epochPageRequest,epochPageRevision} from '../epoch-browser/epochBrowserSource.js';

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
  if(!Number.isSafeInteger(count))throw new Error('Complete incoming counts are unavailable.');
  if(count>1000&&source.readContext.selection_manifests!==true)throw new Error('Update the Workbench service to select more than 1,000 epochs.');
  const check=()=>{if(signal?.aborted||!isCurrent())throw new DOMException('Incoming selection changed. Select again.','AbortError');};
  if(source.readContext.list_selection===true){
    check();
    const filters=new URLSearchParams(source.query);filters.delete('candidate_scope_revision');filters.delete('selection_token');
    const allIds=[];
    for(let start=0;start<chosen.length;start+=250){
    const batch=chosen.slice(start,start+250),batchCount=batch.reduce((sum,cell)=>sum+cell.epochs,0);
    const result=await request(`${source.readContext.root}/list-selection`,{method:'POST',signal,body:{
      candidate_scope_revision:source.readContext.candidate_scope_revision,
      ...(source.readContext.selection_token?{selection_token:source.readContext.selection_token}:{}),
      cells:batch.map(({cell_uuid,epochs})=>({cell_uuid,epochs})),filters:Object.fromEntries(filters)}});
    check();epochPageRevision(source,result);
    if(result?.candidate_scope_revision!==source.readContext.candidate_scope_revision||
      result.expected_binding_version!==source.readContext.expected_binding_version||result.count!==batchCount||
      !Array.isArray(result.cells)||result.cells.length!==batch.length||!Array.isArray(result.epoch_uuids))throw new Error('The incoming selection changed. Refresh and select again.');
    const ids=[];
    for(let index=0;index<batch.length;index++){
      const expected=batch[index],cell=result.cells[index];
      if(cell?.cell_uuid!==expected.cell_uuid||cell.epochs!==expected.epochs||!Array.isArray(cell.epoch_uuids)||cell.epoch_uuids.length!==expected.epochs||
        cell.epoch_uuids.some(id=>typeof id!=='string'||!id))throw new Error('The complete incoming cell selection could not be verified.');
      for(const id of cell.epoch_uuids)ids.push(id);
    }
    if(ids.length!==batchCount||new Set(ids).size!==batchCount||result.epoch_uuids.length!==batchCount||ids.some((id,index)=>id!==result.epoch_uuids[index]))throw new Error('The incoming selection contains duplicate or missing identities.');
    for(const id of ids)allIds.push(id);
    check();
    }
    if(allIds.length!==count||new Set(allIds).size!==count)throw new Error('The incoming selection contains duplicate or missing identities.');
    return allIds;
  }
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

// Branch switches remember the user's command, not an aggregate of child UUIDs.
// They are ephemeral presentation state; flat selected UUIDs remain authoritative.
export function incomingTreeSelectionScope(props){
  return JSON.stringify([props.projectId??null,props.protocolId??null,props.readContext??null,
    props.filters||{},props.splits||'',props.revision??0]);
}
export function incomingBranchOn(intent,scope,revision,path=[]){
  if(!intent||intent.scope!==scope||intent.revision!==revision)return false;
  let nearest=null;
  for(const marker of intent.markers||[]){
    if(marker.path.length<=path.length&&marker.path.every((key,index)=>path[index]===key)&&
      (!nearest||marker.path.length>nearest.path.length))nearest=marker;
  }
  return nearest?.on===true;
}
export function incomingBranchCommand(intent,scope,revision,path,on){
  const markers=intent?.scope===scope&&intent.revision===revision?intent.markers||[]:[];
  return {scope,revision,markers:[...markers.filter(marker=>!(path.length<=marker.path.length&&path.every((key,index)=>marker.path[index]===key))),{path:[...path],on}]};
}
