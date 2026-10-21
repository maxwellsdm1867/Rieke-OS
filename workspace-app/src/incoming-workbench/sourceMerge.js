import {workbenchCandidateRoot,workbenchRoot,requireWorkbenchContext,requirePreparedWorkbench,previewWorkbench,workbenchPreviewCounts,acceptanceFailureKind,finishWorkbenchReview} from './workbenchAuthority.js';

// Hold consent belongs to one frozen source, or (mode 'all') to every mergeable
// pending epoch of one protocol at the queue revision the scientist saw. The
// server resolves complete membership; interactive selection is not used.
export function createSourceMerge({projectId,request,persist=async()=>{},owner=()=>null,onState=()=>{}}){
 let state={phase:'idle',operation:null,message:'',notice:''},running=false,alive=true;
 const publish=next=>{state=next;if(alive)onState(state);};
 const root=op=>workbenchCandidateRoot(op.protocolId,op.candidateId);
 const validAll=op=>op?.projectId===projectId&&op.mergeAll===true&&typeof op.protocolId==='string'&&!!op.protocolId&&op.body?.mode==='merge_all'&&['operation_uuid','expected_queue_revision'].every(k=>typeof op.body[k]==='string'&&!!op.body[k]);
 const validFinish=op=>op?.projectId===projectId&&op.finishReview===true&&!!op.protocolId&&!!op.candidateId&&!!op.actor&&op.context?.actor===op.actor&&typeof op.body?.operation_uuid==='string'&&!!op.context?.candidate_scope_revision&&Number.isSafeInteger(op.context?.draft?.draft_version);
 const valid=op=>validFinish(op)||validAll(op)||op?.projectId===projectId&&['protocolId','candidateId','actor'].every(k=>typeof op[k]==='string'&&!!op[k])&&(op.body?.mode==='source'?typeof op.sourceSha256==='string'&&!!op.sourceSha256&&op.body.source_sha256===op.sourceSha256:op.body?.mode==='all'&&op.sourceSha256===undefined&&op.body.source_sha256===undefined)&&['operation_uuid','preview_sha256','expected_candidate_scope_revision','expected_query_revision'].every(k=>typeof op.body[k]==='string'&&!!op.body[k])&&Number.isSafeInteger(op.body.expected_draft_version)&&Number.isSafeInteger(op.body.expected_binding_version);
 // Merge all is one idempotent request; its receipt names the candidate.
 async function submitAll(op,recovering=false,receiptOnly=false){
  publish({phase:'accepting',operation:op,message:recovering?'Recovering merge receipt…':'Merging into Main…',notice:state.notice||''});
  try{
   const receipt=receiptOnly?await request(`/protocols/${encodeURIComponent(op.protocolId)}/workbench/receipts/${encodeURIComponent(op.body.operation_uuid)}`)
     :await request(`${workbenchRoot(op.protocolId)}/merge-all`,{method:'POST',body:{expected_queue_revision:op.body.expected_queue_revision,operation_uuid:op.body.operation_uuid}});
   if(receipt.operation_uuid!==op.body.operation_uuid||receipt.protocol_uuid!==op.protocolId||receipt.mode!=='all'||!receipt.binding?.revision_uuid||!Number.isSafeInteger(receipt.binding.version)||!receipt.event_uuid)throw Error('The merge receipt is incomplete.');
   publish({phase:'idle',operation:null,message:'',notice:state.notice||''});
   return {protocolId:op.protocolId,receipt};
  }catch(error){
   const uncertain=recovering||acceptanceFailureKind(error)!=='rejected';
   publish({phase:uncertain?'unconfirmed':'error',operation:uncertain?op:null,message:uncertain?'Merge may have completed. Recover this same receipt before trying another merge.':`Merge was not accepted. ${error.message}`});
   throw Object.assign(Error(state.message),{reported:true});
  }
 }
 async function submit(op,recovering=false,receiptOnly=false){
  if(op.mergeAll)return submitAll(op,recovering,receiptOnly);
  publish({phase:'accepting',operation:op,message:recovering?'Recovering merge receipt…':'Merging into Main…',notice:state.notice||''});
  try{
   const receipt=receiptOnly?await request(`/protocols/${encodeURIComponent(op.protocolId)}/workbench/receipts/${encodeURIComponent(op.body.operation_uuid)}`):await request(`${root(op)}/accept`,{method:'POST',body:op.body});
   if(receipt.operation_uuid!==op.body.operation_uuid||receipt.protocol_uuid!==op.protocolId||receipt.candidate_revision_uuid!==op.candidateId||receipt.actor!==op.actor||receipt.mode!==op.body.mode||op.body.mode==='source'&&receipt.source_sha256!==op.sourceSha256||receipt.preview_sha256!==op.body.preview_sha256||receipt.candidate_scope_revision!==op.body.expected_candidate_scope_revision||receipt.expected_draft_version!==op.body.expected_draft_version||!receipt.binding?.revision_uuid||!Number.isSafeInteger(receipt.binding.version)||!receipt.event_uuid)throw Error('The acceptance receipt is incomplete.');
   publish({phase:'idle',operation:null,message:'',notice:state.notice||''});
   return {protocolId:op.protocolId,receipt};
  }catch(error){
   const uncertain=recovering||acceptanceFailureKind(error)!=='rejected';
   publish({phase:uncertain?'unconfirmed':'error',operation:uncertain?op:null,message:uncertain?'Merge may have completed. Recover this same receipt before trying another merge.':`Merge was not accepted. ${error.message}`});
   throw Object.assign(Error(state.message),{reported:true});
  }
 }
 async function submitFinish(op,recovering=false,receiptOnly=false){
  publish({phase:'accepting',operation:op,message:recovering?'Recovering review completion…':'Finishing review…'});
  try{
   const finished=await finishWorkbenchReview(root(op),op.context,request,{operationUuid:op.body.operation_uuid,receiptOnly});
   publish({phase:'idle',operation:null,message:''});
   return {protocolId:op.protocolId,reviewFinished:true,receipt:finished.review_completion};
  }catch(error){
   const uncertain=recovering||acceptanceFailureKind(error)!=='rejected';
   publish({phase:uncertain?'unconfirmed':'error',operation:uncertain?op:null,message:uncertain?'Review may have finished. Recover this same completion before continuing.':`Review was not finished. Refresh the pending review and confirm again. ${error.message}`});
   throw Object.assign(Error(state.message),{reported:true});
  }
 }
 // Best-effort recovery save: the replay body is idempotent per operation_uuid.
 // Only a failed accepted write (persist throws) refuses submission; a view
 // snapshot that could not be saved leaves a quiet notice.
 async function saveRecovery(op,current){
  try{const saved=await persist();current();publish({...state,notice:saved?.viewSaved===false?saved.notice||'The latest view could not be saved; the merge was still submitted.':''});}
  catch(error){publish({phase:'error',operation:null,message:error.message,notice:''});throw error;}
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
    await saveRecovery(op,current);
    return await submit(op);
   }catch(error){if(!state.operation)publish({phase:'error',operation:null,message:error.message});throw Object.assign(error,{reported:true});}
   finally{running=false;}
  },
  async startAll(protocolId,{queue_revision:queueRevision}={}){
   if(running||state.operation)throw Error('Finish or recover the current merge first.');
   if(!projectId||[protocolId,queueRevision].some(v=>typeof v!=='string'||!v))throw Error('The protocol and its current pending queue must be identified before merging.');
   running=true;const captured=owner();
   const current=()=>{if(!alive||owner()!==captured)throw Error('The workspace changed before submission. Hold to merge again from the current Overview.');};
   // The queue revision the scientist saw is the consent; the server merges
   // exactly that pending set or refuses if it changed.
   const op={projectId,protocolId,mergeAll:true,body:{mode:'merge_all',expected_queue_revision:queueRevision,operation_uuid:crypto.randomUUID()}};
   try{
    publish({phase:'preparing',operation:op,message:'Saving merge recovery identity…',notice:''});
    await saveRecovery(op,current);
    return await submit(op);
   }catch(error){if(!state.operation)publish({phase:'error',operation:null,message:error.message,notice:''});throw Object.assign(error,{reported:true});}
   finally{running=false;}
  },
  async finish(protocolId,{queue_revision:queueRevision}={}){
   if(running||state.operation)throw Error('Finish or recover the current merge first.');
   if(!projectId||!protocolId||!queueRevision)throw Error('The current pending queue must be identified before finishing review.');
   running=true;const captured=owner();
   const current=()=>{if(!alive||owner()!==captured)throw Error('The workspace changed. Confirm Finish reviewing again from the current Overview.');};
   publish({phase:'preparing',operation:null,message:'Finishing review…'});
   try{
    await persist();current();
    const prepared=requirePreparedWorkbench(protocolId,await request(`${workbenchRoot(protocolId)}/prepare`,{method:'POST',body:{expected_queue_revision:queueRevision}}),queueRevision);current();
    const profiles=await request('/annotation-profiles');current();
    if(!prepared.context.actor||(profiles.selected_profile_uuid||profiles.default_profile_uuid)!==prepared.context.actor)throw Error('The tag author changed. Confirm Finish reviewing again with the current author.');
    const op={projectId,protocolId,candidateId:prepared.candidate_revision_uuid,actor:prepared.context.actor,finishReview:true,context:{actor:prepared.context.actor,candidate_scope_revision:prepared.context.candidate_scope_revision,draft:{draft_version:prepared.context.draft.draft_version}},body:{operation_uuid:crypto.randomUUID()}};
    publish({phase:'preparing',operation:op,message:'Saving review recovery identity…'});
    await saveRecovery(op,current);
    return await submitFinish(op);
   }catch(error){if(!state.operation)publish({phase:'error',operation:null,message:error.message});throw Object.assign(error,{reported:true});}
   finally{running=false;}
  },
  async recover({retry=false}={}){if(running||!valid(state.operation))throw Error('No recoverable merge is available.');running=true;const op=state.operation,captured=owner();try{const profiles=op.mergeAll?null:await request('/annotation-profiles');if(!op.mergeAll&&(profiles.selected_profile_uuid||profiles.default_profile_uuid)!==op.actor){const name=profiles.profiles?.find(p=>p.profile_uuid===op.actor)?.display_name||op.actor;const message=`Choose tag author ${name} before recovering this merge receipt.`;publish({...state,phase:'unconfirmed',message});throw Error(message);}if(!alive||owner()!==captured)throw Error('The workspace changed before recovery submission. Recover again from the current view.');return await (op.finishReview?submitFinish(op,true,!retry):submit(op,true,!retry));}finally{running=false;}},
  dismiss(){if(!running&&!state.operation)publish({phase:'idle',operation:null,message:''});},
  open(){alive=true;},
  close(){alive=false;},
 };
}
