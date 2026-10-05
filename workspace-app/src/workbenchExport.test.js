import test from 'node:test';
import assert from 'node:assert/strict';
import {acceptedExportRequest,candidateExportRequest,submitWorkbenchExport,nextWorkbenchWorkflow} from "./exports/workbenchExport.js";
const preview={expected_candidate_scope_revision:'frozen',expected_draft_version:4,mode:'selected',preview_sha256:'preview',expected_binding_version:7,expected_query_revision:'main',accepted_epoch_count:2};
test('new-only export uses exact preview fences and independent export identity',()=>{
 const prepared=candidateExportRequest('/candidate',preview,{format:'reference-json',name:'New only',operationUuid:'export-op'});
 assert.equal(prepared.path,'/candidate/exports');assert.deepEqual(prepared.body,{expected_candidate_scope_revision:'frozen',expected_draft_version:4,mode:'selected',preview_sha256:'preview',expected_binding_version:7,expected_query_revision:'main',format:'reference-json',name:'New only',operation_uuid:'export-op'});
});
test('accepted export uses acceptance receipt context, with no accept or binding request',async()=>{
 const calls=[];
 const prepared=await acceptedExportRequest('protocol',{operation_uuid:'accept-op'},{format:'matlab-mat',operationUuid:'export-op'},async path=>{calls.push(path);return {export_scope_revision:'accepted-frozen',accepted_epoch_count:2,accept_operation_uuid:'accept-op'};});
 assert.deepEqual(calls,['/protocols/protocol/workbench/receipts/accept-op/export-context']);
 assert.equal(prepared.path,'/protocols/protocol/workbench/receipts/accept-op/exports');
 assert.deepEqual(prepared.body,{expected_export_scope_revision:'accepted-frozen',format:'matlab-mat',operation_uuid:'export-op'});
 await assert.rejects(()=>acceptedExportRequest('protocol',{operation_uuid:'accept-op'},{},async()=>({export_scope_revision:'x',accepted_epoch_count:0,accept_operation_uuid:'accept-op'})),/no complete export context/);
 await assert.rejects(()=>acceptedExportRequest('protocol',{operation_uuid:'accept-op'},{format:'matlab-mat'},async()=>({export_scope_revision:'x',accepted_epoch_count:2,accept_operation_uuid:'accept-op',formats:['reference-json','wheeler-sqlite']})),/does not support the chosen/);
});
test('lost export response retries identical request and requires complete authoritative artifact receipt',async()=>{
 const prepared=candidateExportRequest('/candidate',preview,{format:'wheeler-sqlite',operationUuid:'export-op'}),calls=[];let attempts=0;
 const request=async(path,options)=>{calls.push({path,...options});if(attempts++===0)throw Error('reply lost');return {dataset_uuid:'dataset',event_uuid:'event',artifact_sha256:'sha',epoch_count:2,download_url:'/download',format:'wheeler-sqlite',operation_uuid:'export-op',export_scope:{kind:'workbench_incoming'}};};
 await assert.rejects(()=>submitWorkbenchExport(prepared,request),/reply lost/);
 assert.equal((await submitWorkbenchExport(prepared,request)).dataset_uuid,'dataset');assert.deepEqual(calls[0],calls[1]);
 await assert.rejects(()=>submitWorkbenchExport(prepared,async()=>({})),/receipt is incomplete/);
});

test('fresh workflow preserves completed receipts without carrying old operation identities',()=>{
 const previous={receipt:{event_uuid:'accept'},exported:{dataset_uuid:'artifact'},prepared:{body:{}},acceptOperation:'old-accept',exportOperation:'old-export',workflow:'export'};
 const next=nextWorkbenchWorkflow(previous);
 assert.deepEqual(next,{completed:[{receipt:previous.receipt,exported:previous.exported}]});
});
