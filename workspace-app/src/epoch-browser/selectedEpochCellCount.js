import {selectedSummaryIds,validateSelectionSummary} from '../incoming-workbench/incomingSelectionSummary.js';
import {createWorkbenchSelection} from '../incoming-workbench/workbenchAuthority.js';
import {frozenReadQuery} from './frozenReadContext.js';

// Display-only identity read. This result never supplies membership or write consent.
export async function readSelectedEpochCellCount({selected,readContext=null,request,signal}){
  const ids=selectedSummaryIds(selected);
  if(!ids)throw Error('The selected epoch identities could not be verified.');
  if(!ids.length)return 0;
  if(signal?.aborted)throw new DOMException('Selection changed.','AbortError');
  if(readContext){
    frozenReadQuery(readContext);
    if(readContext.selection_summary!==true||!Number.isSafeInteger(readContext.expected_binding_version)||readContext.expected_binding_version<0)
      throw Error('Cell counts are unavailable for this incoming selection.');
    let token=null;
    if(ids.length>1000){
      if(readContext.selection_manifests!==true)throw Error('This incoming selection cannot be summarized completely.');
      token=(await createWorkbenchSelection({root:readContext.root,context:{...readContext,draft:{draft_version:0}},ids,signal},request)).selection_token;
    }
    const result=await request(`${readContext.root}/selection-summary`,{method:'POST',background:true,signal,body:{candidate_scope_revision:readContext.candidate_scope_revision,...(token?{selection_token:token}:{epoch_uuids:ids})}});
    return validateSelectionSummary(result,ids,readContext).counts.cells;
  }
  if(ids.length>1000)throw Error('Cell counts require at most 1,000 selected epochs.');
  const result=await request('/annotations/read',{method:'POST',background:true,signal,body:{target_kind:'epoch',target_uuids:ids}});
  const rows=result?.annotations;
  if(!rows||typeof rows!=='object'||Array.isArray(rows)||Object.keys(rows).length!==ids.length||
      ids.some(id=>rows[id]?.epoch_uuid!==id||typeof rows[id]?.cell_uuid!=='string'||!rows[id].cell_uuid))
    throw Error('The selected cell identities could not be verified.');
  return new Set(ids.map(id=>rows[id].cell_uuid)).size;
}
