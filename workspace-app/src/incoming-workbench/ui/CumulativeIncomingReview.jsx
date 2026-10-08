import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {api,number,time} from '../../api.js';
import {Activity,History,RefreshCw} from 'lucide-react';
import NeuronIcon from '../../components/NeuronIcon.jsx';
import {requireWorkbenchContext,workbenchCandidateRoot,workbenchRoot} from '../workbenchAuthority.js';
import FrozenIncomingReview from './FrozenIncomingReview.jsx';
import WorkbenchExportDialog from "../../exports/ui/WorkbenchExportDialog.jsx";
import {useAnnotationProfile} from '../../annotations/annotationProfile.js';

export function requirePreparedWorkbench(protocol,value,queueRevision){
  if(value?.contract_version!==1||value.kind!=='workbench_pending_union'||typeof value.prepare_operation_uuid!=='string'||typeof value.candidate_revision_uuid!=='string'||value.root!==workbenchCandidateRoot(protocol,value.candidate_revision_uuid))throw new Error('The cumulative Workbench did not return an authoritative frozen destination.');
  requireWorkbenchContext(value.context);
  const contextProtocol=value.context.protocol?.definition?.protocol_uuid||value.context.protocol?.protocol_uuid;
  if(value.context.candidate_revision_uuid!==value.candidate_revision_uuid||contextProtocol!==protocol||value.context.protocol?.protocol_uuid&&value.context.protocol.protocol_uuid!==protocol)throw new Error('The cumulative Workbench context belongs to another candidate or protocol.');
  if(value.candidate_scope_revision!==value.context.candidate_scope_revision||value.queue_revision!==queueRevision)throw new Error('The cumulative Workbench scope changed while preparing. Refresh the queue.');
  return {...value,queue_revision:queueRevision};
}
// A replacement frozen candidate may keep the way the scientist was browsing,
// never its selected epochs, edit text, receipts or revision-bound tree pages.
function viewerPresentation(viewer){
  if(!viewer)return null;
  const result={};
  for(const key of ['treeOpen','treeMode','designMode'])if(typeof viewer[key]==='boolean')result[key]=viewer[key];
  for(const key of ['focused','focusCell'])if(viewer[key]===null||typeof viewer[key]==='string')result[key]=viewer[key];
  if(Number.isSafeInteger(viewer.offset)&&viewer.offset>=0)result.offset=viewer.offset;
  return result;
}
export default function CumulativeIncomingReview({queue,protocolId,session={},onSession,onHistory,onRefresh,onReviewProposal,refreshing=false,mergeRequest=null,onMergeRequestHandled,...reviewProps}){
  const [prepared,setPrepared]=useState(session.prepared||null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[nonce,setNonce]=useState(0);
  const [receiptExport,setReceiptExport]=useState(null),[,setDraftVersion]=useState(0);
  const drafts=useRef(session.drafts||{}),scopes=useRef(session.scopes||(session.prepared?{[session.prepared.candidate_revision_uuid]:session.prepared}:{})),attempted=useRef(null),snapshot=useRef(null);
  const presentationOwner=useRef({protocolId,projectId:reviewProps.projectId});
  const draft=prepared?drafts.current[prepared.candidate_revision_uuid]:null;
  const recovering=(!draft?.receipt&&(!!draft?.acceptPending||!!draft?.unconfirmed))||!!draft?.exportState?.pending||!!draft?.exportState&&!draft.exportState.exported&&!!(draft.exportState.prepared||draft.exportState.acceptOperation);
  const profile=useAnnotationProfile();
  const owner=useMemo(()=>({projectId:reviewProps.projectId,protocolId,revision:reviewProps.revision,
    profileUuid:profile.profileUuid,profileReady:!!profile.profileUuid&&!profile.loading&&!profile.error,
    queueRevision:queue.data?.queue_revision}),[reviewProps.projectId,protocolId,reviewProps.revision,profile.profileUuid,profile.loading,profile.error,queue.data?.queue_revision]);
  // Read refreshes retire freshness without silently retrying preparation.
  // Actual project/protocol/actor transitions create a different request owner.
  const requestOwner=useMemo(()=>({}),[reviewProps.projectId,protocolId,profile.profileUuid]);
  const freshContext=useRef(null),latest=useRef(null);
  latest.current={owner,candidate:prepared?.candidate_revision_uuid,ready:!queue.loading&&!queue.error&&!recovering};
  if(freshContext.current&&(freshContext.current.owner!==owner||!latest.current.ready))freshContext.current=null;
  // One mounted child may claim this response once. It never enters prepared,
  // scopes or the saved session; returning to a saved view still performs GET.
  const takePreparedContext=useCallback(expected=>{
    const seed=freshContext.current;
    const current=latest.current;
    if(!seed||seed.claimed||seed.token!==expected.token||!current.ready||seed.owner!==current.owner||current.candidate!==expected.candidate
      ||seed.candidate!==expected.candidate||!expected.profileReady
      ||['projectId','protocolId','revision','profileUuid'].some(key=>seed.owner[key]!==expected[key]))return null;
    seed.claimed=true;
    return seed.context;
  },[]);
  snapshot.current={prepared,drafts:drafts.current,scopes:scopes.current};
  useEffect(()=>{onSession?.(snapshot.current);},[prepared,onSession]);
  // A failed preparation cannot fulfill this preview request. Preserve all
  // saved drafts and receipts, but do not replay the request after a retry.
  useEffect(()=>{if(error&&mergeRequest)onMergeRequestHandled?.();},[error,mergeRequest,onMergeRequestHandled]);
  useEffect(()=>{
    const token=queue.data?.queue_revision;
    const hasHistory=(queue.data?.total_candidate_count||queue.data?.candidates?.length||0)>0;
    if(!token||queue.data.pending_epoch_count===0&&!hasHistory||queue.loading||queue.error||recovering||prepared?.queue_revision===token){setBusy(false);return;}
    const key=`${protocolId}:${token}:${nonce}`;
    if(attempted.current?.key!==key||attempted.current.requestOwner!==requestOwner){
      let responseFresh=false;
      attempted.current={key,owner,requestOwner,promise:api(`${workbenchRoot(protocolId)}/prepare`,{method:'POST',body:{expected_queue_revision:token},
        onResponse:response=>{responseFresh=response.headers?.get?.('X-Disco-Workbench-Context')==='fresh-v1';}
      }).then(value=>({value,responseFresh}))};
    }
    const attempt=attempted.current;
    // Preparation may commit before a response arrives. Effect cleanup only
    // detaches this display subscriber; StrictMode replay rejoins the same
    // request, and a real remount retries the exact server-idempotent body.
    let active=true;setBusy(true);setError('');
    attempt.promise.then(({value,responseFresh})=>{
      if(active&&attempted.current===attempt&&latest.current.owner===owner){const saved=requirePreparedWorkbench(protocolId,value,token);
        const previous=snapshot.current?.prepared,priorProtocol=previous?.context?.protocol?.definition?.protocol_uuid||previous?.context?.protocol?.protocol_uuid;
        const previousViewer=viewerPresentation(drafts.current[previous?.candidate_revision_uuid]?.viewer);
        const destination=drafts.current[saved.candidate_revision_uuid];
        if(previous?.candidate_revision_uuid!==saved.candidate_revision_uuid&&priorProtocol===protocolId&&presentationOwner.current.protocolId===protocolId&&presentationOwner.current.projectId===reviewProps.projectId&&previousViewer&&!Object.hasOwn(destination||{},'viewer')){
          drafts.current={...drafts.current,[saved.candidate_revision_uuid]:{...destination,viewer:previousViewer}};
        }
        presentationOwner.current={protocolId,projectId:reviewProps.projectId};
        freshContext.current=responseFresh&&attempt.owner===owner&&latest.current.ready&&owner.profileReady&&value.actor===owner.profileUuid
          &&owner.projectId&&saved.context.protocol?.definition?.project_uuid===owner.projectId
          ?{owner,token:{},claimed:false,candidate:saved.candidate_revision_uuid,context:saved.context}:null;
        scopes.current={...scopes.current,[saved.candidate_revision_uuid]:saved};setBusy(false);setPrepared(saved);}
    }).catch(error=>{if(active&&attempted.current===attempt&&latest.current.owner===owner){setBusy(false);setError(error.message);}});
    return()=>{active=false;};
  },[protocolId,reviewProps.projectId,queue.data?.queue_revision,queue.data?.pending_epoch_count,queue.data?.total_candidate_count,queue.loading,queue.error,recovering,nonce,prepared?.queue_revision,owner,requestOwner]);
  const eligibleProposals=(queue.data?.candidates||[]).filter(item=>['pending','pending_rebased','deferred'].includes(item.status)&&Number.isSafeInteger(item.eligible_pending_epoch_count)&&item.eligible_pending_epoch_count>0);
  const authorityChanged=!!queue.data?.queue_revision&&prepared?.queue_revision!==queue.data.queue_revision;
  const remember=useCallback(value=>{drafts.current={...drafts.current,[prepared.candidate_revision_uuid]:value};onSession?.({...snapshot.current,drafts:drafts.current});setDraftVersion(value=>value+1);},[prepared?.candidate_revision_uuid,onSession]);
  return <section className="incoming-cumulative">
    {!prepared&&<div className="incoming-action-bar"><div className="incoming-bar-metrics" aria-label="Distinct pending incoming counts"><span className={`incoming-bar-scope ${queue.data?.pending_epoch_count>0?'is-pending':''}`}>{queue.data?.pending_epoch_count>0?'Pending merge':queue.data?.pending_epoch_count===0?'No pending':'Incoming'}</span><span><NeuronIcon size={18}/><strong>{Number.isSafeInteger(queue.data?.pending_cell_count)?`${queue.data.pending_cell_count>0?'+':''}${number(queue.data.pending_cell_count)}`:'Unavailable'}</strong><small>cells</small></span><span><Activity size={18} aria-hidden="true"/><strong>{Number.isSafeInteger(queue.data?.pending_epoch_count)?`${queue.data.pending_epoch_count>0?'+':''}${number(queue.data.pending_epoch_count)}`:'Unavailable'}</strong><small>epochs</small></span></div><div className="incoming-bar-actions"><button disabled={refreshing} onClick={onRefresh}><RefreshCw size={13} aria-hidden="true"/> Refresh</button><button onClick={onHistory}><History size={13} aria-hidden="true"/> Proposal history</button></div></div>}
    {recovering&&prepared?.queue_revision!==queue.data?.queue_revision&&<p role="status">The pending set changed. Recover the saved operation before preparing the updated incoming set.</p>}
    {busy&&<p role="status">Preparing the cumulative unmerged snapshot…</p>}
    {error&&<section className="incoming-preparation-error" aria-label="Cumulative review recovery"><div role="alert"><strong>Merge preview unavailable</strong><p>{error}</p></div><p>Combined review is unavailable. Proposal history keeps the original snapshots and saved decisions. An eligible proposal can be reviewed on its own; its own selections and exclusions apply.</p><div className="incoming-actions">{onHistory&&<button onClick={onHistory}>Review saved proposals</button>}<button disabled={busy||queue.loading} onClick={()=>setNonce(value=>value+1)}>Retry cumulative preparation</button></div>{onReviewProposal&&eligibleProposals.map(item=><div key={item.candidate_revision_uuid} className="incoming-actions"><button disabled={busy||queue.loading||!!queue.error||recovering} onClick={()=>onReviewProposal(item.candidate_revision_uuid)}>Review eligible proposal</button><span>{item.source_filename||'Saved incoming proposal'} · {time(item.created_at)} · {number(item.eligible_pending_epoch_count)} eligible epochs</span></div>)}</section>}
    {receiptExport&&<WorkbenchExportDialog protocolId={protocolId} item={{candidate_revision_uuid:receiptExport}} acceptReceipt={drafts.current[receiptExport].receipt} state={drafts.current[receiptExport].exportState||{}} onState={value=>{drafts.current={...drafts.current,[receiptExport]:{...drafts.current[receiptExport],exportState:value}};onSession?.({...snapshot.current,drafts:drafts.current});setDraftVersion(value=>value+1);}} onClose={()=>setReceiptExport(null)} onChanged={reviewProps.onChange}/>}
    {Object.entries(drafts.current).filter(([key])=>key!==prepared?.candidate_revision_uuid).map(([key,value])=><div key={key}>{value.unconfirmed||value.acceptPending?<p role="status">An earlier acceptance needs receipt recovery. <button disabled={!scopes.current[key]} onClick={()=>setPrepared(scopes.current[key])}>Recover earlier acceptance</button></p>:value.receipt&&!value.exportState?.exported?<p>Earlier acceptance saved · {value.receipt.event_uuid} <button onClick={()=>setReceiptExport(key)}>Export accepted additions</button></p>:null}</div>)}
    {queue.data?.pending_epoch_count===0&&!recovering&&<p role="status">No pending incoming recordings. Saved exclusions remain in your draft.</p>}
    {prepared?<FrozenIncomingReview {...reviewProps} preparedContextToken={freshContext.current?.token} takePreparedContext={takePreparedContext} mergeRequest={mergeRequest} onMergeRequestHandled={onMergeRequestHandled} onHistory={onHistory} onRefresh={onRefresh} refreshing={refreshing} preserveBrowser pendingCounts={queue.data} externalBusy={busy||!!(queue.loading||queue.error||authorityChanged)&&!recovering} key={prepared.candidate_revision_uuid} protocolId={protocolId} item={{candidate_revision_uuid:prepared.candidate_revision_uuid,protocol_uuid:protocolId}} scopeKind="cumulative_pending" capabilities={queue.data.capabilities} session={draft} onSession={remember}/>:!busy&&!error&&queue.data.pending_epoch_count>0&&<p role="status">Waiting for the authoritative pending queue.</p>}
    {Object.entries(drafts.current).filter(([key])=>key!==prepared?.candidate_revision_uuid).flatMap(([key,value])=>[...(value.exportState?.completed||[]),...(value.receipt||value.exportState?.exported?[{receipt:value.receipt,exported:value.exportState?.exported}]:[])]).map((value,index)=><p key={value.exported?.dataset_uuid||value.receipt?.event_uuid||index}>{value.receipt&&<>Earlier acceptance · receipt {value.receipt.event_uuid} </>}{value.exported&&<a href={value.exported.download_url} download>{value.exported.name||'Download incoming export'}</a>}</p>)}
  </section>;
}
