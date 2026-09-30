const changedMessage='Selection or dataset changed while loading. Review the current selection and save again.';
export function curationSelectionChanged(){return new Error(changedMessage);}

// One compact identity/revision read followed by one atomic save. The read is
// cancellable; a submitted mutation is never aborted or automatically retried.
export async function saveCurationSelection({request,protocolId,queryRevision,bindingVersion=0,epochUuids,selectionScope,changes,isCurrent=()=>true,signal}){
  if(!Array.isArray(epochUuids)||!epochUuids.length||epochUuids.length>1000||epochUuids.some(id=>typeof id!=='string'||!id)||new Set(epochUuids).size!==epochUuids.length)throw new Error('Select 1–1,000 unique epochs before saving.');
  if(typeof queryRevision!=='string'||!queryRevision||!Number.isSafeInteger(bindingVersion)||bindingVersion<0)throw new Error('Refresh this dataset before saving.');
  const ids=[...epochUuids];
  const body={epoch_uuids:ids,query_revision:queryRevision,expected_binding_version:bindingVersion,selection_scope:selectionScope};
  const assertCurrent=()=>{if(signal?.aborted||!isCurrent())throw curationSelectionChanged();};
  assertCurrent();
  let receipt;
  try{receipt=await request(`/protocols/${protocolId}/curation/read`,{method:'POST',signal,body});}
  catch(error){assertCurrent();throw error;}
  assertCurrent();
  if(receipt?.protocol_uuid!==protocolId||receipt.query_revision!==queryRevision||receipt.expected_binding_version!==bindingVersion||!Array.isArray(receipt.epochs)||receipt.epochs.length!==ids.length)throw new Error('The dataset identity or revision changed. Refresh before saving.');
  const expected_revisions={};
  for(let index=0;index<ids.length;index++){
    const row=receipt.epochs[index];
    if(row?.epoch_uuid!==ids[index]||typeof row.cell_uuid!=='string'||!row.cell_uuid||!Number.isSafeInteger(row.curation_revision)||row.curation_revision<0)throw new Error('The server returned an incomplete selection. Refresh before saving.');
    if(selectionScope?.cell_uuid&&row.cell_uuid!==selectionScope.cell_uuid)throw new Error('Cell focus changed. Clear the selection and select epochs in the current cell before saving.');
    expected_revisions[row.epoch_uuid]=row.curation_revision;
  }
  assertCurrent();
  return request(`/protocols/${protocolId}/curation`,{method:'POST',body:{...body,changes,expected_revisions}});
}
