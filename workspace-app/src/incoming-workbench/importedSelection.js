import {loadIncomingSelection} from './incomingSelection.js';
import {selectedReview} from './selectedIncomingWorkflow.js';

// A suggestion can include older pending sources. Only the displayed recording
// receives this hold consent, even when the frozen proposal contains more data.
export async function loadImportedSelection({root,context,sourceSha256,request,signal,isCurrent=()=>true}){
  if(typeof sourceSha256!=='string'||!sourceSha256)throw Error('The imported recording identity is unavailable. Inspect it in Workbench.');
  if(!Array.isArray(context?.protocol?.cells)||!Number.isSafeInteger(context?.protocol?.counts?.epochs)||context.protocol.cells.reduce((sum,cell)=>sum+cell.epochs,0)!==context.protocol.counts.epochs)throw Error('Complete incoming counts are unavailable. Inspect this proposal in Workbench.');
  // Source filtering requires epoch DTOs. Deliberately omit list_selection from
  // this readContext: the optimized ID-only receipt carries no source hashes.
  const rows=new Map();
  const ids=await loadIncomingSelection({source:{kind:'protocol',protocolId:context.protocol?.definition?.protocol_uuid,query:'',queryRevision:context.candidate_scope_revision,readContext:{root,candidate_scope_revision:context.candidate_scope_revision}},cells:context.protocol?.cells||[],signal,isCurrent,request:async(path,options)=>{
    const page=await request(path,options);
    for(const row of page.epochs||[]){
      if(typeof row.source_sha256!=='string'||!row.source_sha256)throw Error('The incoming page lacks recording identity. Inspect it in Workbench.');
      rows.set(row.epoch_uuid,row);
    }
    return page;
  }});
  if(!ids.length)return [];
  const excluded=new Set(selectedReview(context,ids).excluded);
  return ids.filter(id=>rows.get(id).source_sha256===sourceSha256&&!excluded.has(id));
}
