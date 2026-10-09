import {workbenchCandidateRoot,requireWorkbenchContext,workbenchPreviewCounts,acceptanceFailureKind} from './workbenchAuthority.js';

// Hold consent belongs to one frozen source. The server resolves its complete
// membership; interactive selection and truncated public draft rows are not used.
export function createSourceMerge({projectId,request,persist=async()=>{},owner=()=>null,onState=()=>{}}){
 let state={phase:'idle',operation:null,message:''},running=false,alive=true;
 const publish=next=>{state=next;if(alive)onState(state);};
 const root=op=>workbenchCandidateRoot(op.protocolId,op.candidateId);
 const valid=op=>op?.projectId===projectId&&['protocolId','candidateId','sourceSha256','actor'].every(k=>typeof op[k]==='string'&&!!op[k])&&op.body?.mode==='source'&&op.body.source_sha256===op.sourceSha256&&['operation_uuid','preview_sha256','expected_candidate_scope_revision','expected_query_revision'].every(k=>typeof op.body[k]==='string'&&!!op.body[k])&&Number.isSafeInteger(op.body.expected_draft_version)&&Number.isSafeInteger(op.body.expected_binding_version);
 async function submit(op,recovering=false,receiptOnly=false){
  publish({phase:'accepting',operation:op,message:recovering?'Recovering merge receipt…':'Merging into Main…'});
  try{
   const receipt=receiptOnly?await request(`/protocols/${encodeURIComponent(op.protocolId)}/workbench/receipts/${encodeURIComponent(op.body.operation_uuid)}`):await request(`${root(op)}/accept`,{method:'POST',body:op.body});
   if(receipt.operation_uuid!==op.body.operation_uuid||receipt.protocol_uuid!==op.protocolId||receipt.candidate_revision_uuid!==op.candidateId||receipt.actor!==op.actor||receipt.mode!=='source'||receipt.source_sha256!==op.sourceSha256||receipt.preview_sha256!==op.body.preview_sha256||receipt.candidate_scope_revision!==op.body.expected_candidate_scope_revision||receipt.expected_draft_version!==op.body.expected_draft_version||!receipt.binding?.revision_uuid||!Number.isSafeInteger(receipt.binding.version)||!receipt.event_uuid)throw Error('The acceptance receipt is incomplete.');
   publish({phase:'idle',operation:null,message:''});
   return {protocolId:op.protocolId,receipt};
  }catch(error){
   const uncertain=recovering||acceptanceFailureKind(error)!=='rejected';
   publish({phase:uncertain?'unconfirmed':'error',operation:uncertain?op:null,message:uncertain?'Merge may have completed. Recover this same receipt before trying another merge.':`Merge was not accepted. ${error.message}`});
   throw Error(state.message);
  }
 }
 return {
  get state(){return state;},
  snapshot:()=>state.operation,
  restore(op){if(op==null)return;if(state.operation&&JSON.stringify(state.operation)===JSON.stringify(op))return;if(running||state.operation)throw Error('A merge operation is already active.');if(!valid(op))throw Error('Saved source-merge recovery identity is invalid.');publish({phase:'unconfirmed',operation:structuredClone(op),message:'A previous merge needs its receipt recovered. No new merge has been submitted.'});},
  async start(protocolId,{candidate_revision_uuid:candidateId,source_sha256:sourceSha256}){
   if(running||state.operation)throw Error('Finish or recover the current merge first.');
   if(!projectId||[protocolId,candidateId,sourceSha256].some(v=>typeof v!=='string'||!v))throw Error('The recording and frozen destination must be identified before merging.');
   running=true;const captured=owner(),op={projectId,protocolId,candidateId,sourceSha256};
   const current=()=>{if(!alive||owner()!==captured)throw Error('The workspace changed before submission. Hold to merge again from the current review.');};
   publish({phase:'preparing',operation:null,message:'Checking recording additions…'});
   try{
    const context=requireWorkbenchContext(await request(`${root(op)}/context`));current();
    if(context.candidate_revision_uuid!==candidateId||context.protocol?.definition?.protocol_uuid!==protocolId)throw Error('The frozen merge destination changed.');
    if(context.source_additive_accept!==true||typeof context.actor!=='string'||!context.actor)throw Error('Direct recording merge is unavailable. Update the review service before continuing.');
    op.actor=context.actor;
    const body={mode:'source',source_sha256:sourceSha256,expected_candidate_scope_revision:context.candidate_scope_revision,expected_draft_version:context.draft.draft_version};
    const preview=await request(`${root(op)}/preview`,{method:'POST',body});current();workbenchPreviewCounts(preview);
    if(preview.mode!=='source'||preview.source_sha256!==sourceSha256||preview.candidate_scope_revision!==body.expected_candidate_scope_revision||preview.expected_draft_version!==body.expected_draft_version||typeof preview.preview_sha256!=='string'||!Number.isSafeInteger(preview.expected_binding_version)||typeof preview.expected_query_revision!=='string')throw Error('The source preview did not preserve the requested recording and scope.');
    op.body={...body,preview_sha256:preview.preview_sha256,expected_binding_version:preview.expected_binding_version,expected_query_revision:preview.expected_query_revision,operation_uuid:crypto.randomUUID()};
    // Persist the exact replay request before submitting a possibly committing write.
    publish({phase:'preparing',operation:op,message:'Saving merge recovery identity…'});
    try{await persist();current();}catch(error){publish({phase:'error',operation:null,message:error.message});throw error;}
    return await submit(op);
   }catch(error){if(!state.operation)publish({phase:'error',operation:null,message:error.message});throw error;}
   finally{running=false;}
  },
  async recover({retry=false}={}){if(running||!valid(state.operation))throw Error('No recoverable merge is available.');running=true;const op=state.operation,captured=owner();try{const profiles=await request('/annotation-profiles');if((profiles.selected_profile_uuid||profiles.default_profile_uuid)!==op.actor){const name=profiles.profiles?.find(p=>p.profile_uuid===op.actor)?.display_name||op.actor;const message=`Choose tag author ${name} before recovering this merge receipt.`;publish({...state,phase:'unconfirmed',message});throw Error(message);}if(!alive||owner()!==captured)throw Error('The workspace changed before recovery submission. Recover again from the current view.');return await submit(op,true,!retry);}finally{running=false;}},
  open(){alive=true;},
  close(){alive=false;},
 };
}
