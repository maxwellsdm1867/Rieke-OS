import {validExportReceipt} from './exportFormats.js';
import {workbenchRoot} from './workbenchAuthority.js';

export function nextWorkbenchWorkflow(state={}){
  return {completed:[...(state.completed||[]),...(state.receipt||state.exported?[{receipt:state.receipt,exported:state.exported}]:[])]};
}

export const acceptanceBody=(preview,operation_uuid)=>({expected_candidate_scope_revision:preview.expected_candidate_scope_revision,expected_draft_version:preview.expected_draft_version,mode:preview.mode,preview_sha256:preview.preview_sha256,expected_binding_version:preview.expected_binding_version,expected_query_revision:preview.expected_query_revision,operation_uuid});
export function candidateExportRequest(root,preview,{format,name,operationUuid}){
  return {path:`${root}/exports`,expectedEpochCount:preview.accepted_epoch_count,body:{...acceptanceBody(preview,operationUuid),format,...(name?{name}:{})}};
}
export async function acceptedExportRequest(protocol,receipt,{format,name,operationUuid},request){
  if(!receipt?.operation_uuid)throw new Error('A committed acceptance operation is required for export.');
  const root=`${workbenchRoot(protocol)}/receipts/${encodeURIComponent(receipt.operation_uuid)}`;
  const context=await request(`${root}/export-context`);
  if(typeof context.export_scope_revision!=='string'||!context.export_scope_revision||context.accept_operation_uuid!==receipt.operation_uuid||!Number.isSafeInteger(context.accepted_epoch_count)||context.accepted_epoch_count<=0)throw new Error('The accepted additions have no complete export context. Main acceptance remains saved.');
  return {path:`${root}/exports`,expectedEpochCount:context.accepted_epoch_count,body:{expected_export_scope_revision:context.export_scope_revision,format,...(name?{name}:{}),operation_uuid:operationUuid}};
}
export async function submitWorkbenchExport(prepared,request){
  const receipt=await request(prepared.path,{method:'POST',body:prepared.body});
  if(!validExportReceipt(receipt,prepared.body.format)||receipt.operation_uuid!==prepared.body.operation_uuid||typeof receipt.artifact_sha256!=='string'||!receipt.artifact_sha256||receipt.export_scope?.kind!=='workbench_incoming'||receipt.epoch_count!==prepared.expectedEpochCount)throw new Error('The export receipt is incomplete. Retry the same export operation to recover its artifact.');
  return receipt;
}
