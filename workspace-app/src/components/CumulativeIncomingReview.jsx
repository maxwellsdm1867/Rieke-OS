import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from '../api.js';
import {requireWorkbenchContext,workbenchCandidateRoot,workbenchRoot} from '../workbenchAuthority.js';
import FrozenIncomingReview from './FrozenIncomingReview.jsx';
import WorkbenchExportDialog from './WorkbenchExportDialog.jsx';

export function requirePreparedWorkbench(protocol,value,queueRevision){
  if(value?.contract_version!==1||value.kind!=='workbench_pending_union'||typeof value.prepare_operation_uuid!=='string'||typeof value.candidate_revision_uuid!=='string'||value.root!==workbenchCandidateRoot(protocol,value.candidate_revision_uuid))throw new Error('The cumulative Workbench did not return an authoritative frozen destination.');
  requireWorkbenchContext(value.context);
  const contextProtocol=value.context.protocol?.definition?.protocol_uuid||value.context.protocol?.protocol_uuid;
  if(value.context.candidate_revision_uuid!==value.candidate_revision_uuid||contextProtocol!==protocol||value.context.protocol?.protocol_uuid&&value.context.protocol.protocol_uuid!==protocol)throw new Error('The cumulative Workbench context belongs to another candidate or protocol.');
  if(value.candidate_scope_revision!==value.context.candidate_scope_revision||value.queue_revision!==queueRevision)throw new Error('The cumulative Workbench scope changed while preparing. Refresh the queue.');
  return {...value,queue_revision:queueRevision};
}
export default function CumulativeIncomingReview({queue,protocolId,session={},onSession,onHistory,...reviewProps}){
  const [prepared,setPrepared]=useState(session.prepared||null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[nonce,setNonce]=useState(0);
  const [receiptExport,setReceiptExport]=useState(null),[,setDraftVersion]=useState(0);
  const drafts=useRef(session.drafts||{}),scopes=useRef(session.scopes||(session.prepared?{[session.prepared.candidate_revision_uuid]:session.prepared}:{})),attempted=useRef(null),snapshot=useRef(null);
  const draft=prepared?drafts.current[prepared.candidate_revision_uuid]:null;
  const recovering=(!draft?.receipt&&(!!draft?.acceptPending||!!draft?.unconfirmed))||!!draft?.exportState?.pending||!!draft?.exportState&&!draft.exportState.exported&&!!(draft.exportState.prepared||draft.exportState.acceptOperation);
  snapshot.current={prepared,drafts:drafts.current,scopes:scopes.current};
  useEffect(()=>{onSession?.(snapshot.current);},[prepared,onSession]);
  useEffect(()=>{
    const token=queue.data?.queue_revision;
    const hasHistory=(queue.data?.total_candidate_count||queue.data?.candidates?.length||0)>0;
    if(!token||queue.data.pending_epoch_count===0&&!hasHistory||queue.loading||queue.error||recovering||prepared?.queue_revision===token||attempted.current===`${token}:${nonce}`)return;
    attempted.current=`${token}:${nonce}`;
    const controller=new AbortController();let settled=false;setBusy(true);setError('');
    api(`${workbenchRoot(protocolId)}/prepare`,{method:'POST',body:{expected_queue_revision:token},signal:controller.signal}).then(value=>{
      if(!controller.signal.aborted){const saved=requirePreparedWorkbench(protocolId,value,token);scopes.current={...scopes.current,[saved.candidate_revision_uuid]:saved};settled=true;setBusy(false);setPrepared(saved);}
    }).catch(error=>{if(!controller.signal.aborted){settled=true;setBusy(false);setError(error.message);}});
    return()=>{controller.abort();if(!settled){setBusy(false);setError('Preparation was interrupted. Retry to recover the authoritative snapshot.');}};
  },[protocolId,queue.data?.queue_revision,queue.data?.pending_epoch_count,queue.data?.total_candidate_count,queue.loading,queue.error,recovering,nonce,prepared?.queue_revision]);
  const authorityChanged=!!queue.data?.queue_revision&&prepared?.queue_revision!==queue.data.queue_revision;
  const remember=useCallback(value=>{drafts.current={...drafts.current,[prepared.candidate_revision_uuid]:value};onSession?.({...snapshot.current,drafts:drafts.current});setDraftVersion(value=>value+1);},[prepared?.candidate_revision_uuid,onSession]);
  return <section>
    <div className="incoming-worklist"><strong>Cumulative unmerged recordings</strong><button onClick={onHistory}>Proposal history</button></div>
    {recovering&&prepared?.queue_revision!==queue.data?.queue_revision&&<p role="status">The pending set changed. Recover the saved operation before preparing the updated incoming set.</p>}
    {busy&&<p role="status">Preparing the cumulative unmerged snapshot…</p>}
    {error&&<p role="alert">{error}<button onClick={()=>setNonce(value=>value+1)}>Retry cumulative preparation</button></p>}
    {receiptExport&&<WorkbenchExportDialog protocolId={protocolId} item={{candidate_revision_uuid:receiptExport}} acceptReceipt={drafts.current[receiptExport].receipt} state={drafts.current[receiptExport].exportState||{}} onState={value=>{drafts.current={...drafts.current,[receiptExport]:{...drafts.current[receiptExport],exportState:value}};onSession?.({...snapshot.current,drafts:drafts.current});setDraftVersion(value=>value+1);}} onClose={()=>setReceiptExport(null)} onChanged={reviewProps.onChange}/>}
    {Object.entries(drafts.current).filter(([key])=>key!==prepared?.candidate_revision_uuid).map(([key,value])=><div key={key}>{value.unconfirmed||value.acceptPending?<p role="status">An earlier acceptance needs receipt recovery. <button disabled={!scopes.current[key]} onClick={()=>setPrepared(scopes.current[key])}>Recover earlier acceptance</button></p>:value.receipt&&!value.exportState?.exported?<p>Earlier acceptance saved · {value.receipt.event_uuid} <button onClick={()=>setReceiptExport(key)}>Export accepted additions</button></p>:null}</div>)}
    {queue.data?.pending_epoch_count===0&&!recovering&&<p role="status">No incoming recordings currently await review. Saved exclusions remain available in the cumulative draft.</p>}
    {prepared?<FrozenIncomingReview {...reviewProps} preserveBrowser externalBusy={busy||!!(queue.loading||queue.error||authorityChanged)&&!recovering} key={prepared.candidate_revision_uuid} protocolId={protocolId} item={{candidate_revision_uuid:prepared.candidate_revision_uuid,protocol_uuid:protocolId}} scopeKind="cumulative_pending" capabilities={queue.data.capabilities} session={draft} onSession={remember}/>:!busy&&!error&&queue.data.pending_epoch_count>0&&<p role="status">Waiting for the authoritative pending queue.</p>}
    {Object.entries(drafts.current).filter(([key])=>key!==prepared?.candidate_revision_uuid).flatMap(([key,value])=>[...(value.exportState?.completed||[]),...(value.receipt||value.exportState?.exported?[{receipt:value.receipt,exported:value.exportState?.exported}]:[])]).map((value,index)=><p key={value.exported?.dataset_uuid||value.receipt?.event_uuid||index}>{value.receipt&&<>Earlier acceptance · receipt {value.receipt.event_uuid} </>}{value.exported&&<a href={value.exported.download_url} download>{value.exported.name||'Download incoming export'}</a>}</p>)}
  </section>;
}
