import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {api,number} from '../../api.js';
import {Activity,CircleDot,Download,GitMerge,History,RefreshCw,X} from 'lucide-react';
import {prepareSelectedIncoming,selectedReview} from '../selectedIncomingWorkflow.js';
import NeuronIcon from '../../components/NeuronIcon.jsx';
import {clearTagFilters} from '../../typed-query/protocolViewFilter.js';
import IncomingCellTypes from './IncomingCellTypes.jsx';
import {mergeIntentMatches} from '../incomingMergeIntent.js';
import Inspector,* as InspectorCapabilities from '../../epoch-browser/ui/Inspector.jsx';
import ProtocolViewFilter from '../../typed-query/ui/ProtocolViewFilter.jsx';
import WorkbenchExportDialog from "../../exports/ui/WorkbenchExportDialog.jsx";
import IncomingMergePreview from './IncomingMergePreview.jsx';
import {nextWorkbenchWorkflow} from "../../exports/workbenchExport.js";
import {acceptWorkbench,acceptanceFailureKind,requireWorkbenchContext,saveWorkbenchDecisions,workbenchCandidateRoot,workbenchRoot,workbenchPreviewCounts} from '../workbenchAuthority.js';
import {useAnnotationProfile} from '../../annotations/annotationProfile.js';

export default function FrozenIncomingReview({projectId,protocolId,item,revision,onChange,onDefer,onNext,onQC,session,onSession,capabilities={},exportIntent=null,acceptOperation=null,scopeKind='proposal',externalBusy=false,preserveBrowser=false,pendingCounts=null,onHistory,onRefresh,refreshing=false,filterTarget=null,toolbarTarget=null,mergeRequest=null,onMergeRequestHandled,preparedContextToken,takePreparedContext}){
  const root=workbenchCandidateRoot(protocolId,item.candidate_revision_uuid);
  const [draftSelectionTarget,setDraftSelectionTarget]=useState(null),[selectionIntent,setSelectionIntent]=useState(null);
  const [context,setContext]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[nonce,setNonce]=useState(0);
  const [unconfirmed,setUnconfirmed]=useState(session?.unconfirmed||session?.acceptPending||false),[acceptPending,setAcceptPending]=useState(false);
  const [highlighted,setHighlighted]=useState(session?.selected||[]);
  const [filters,setFilters]=useState(session?.filters||{}),[preview,setPreview]=useState(session?.preview||null),[receipt,setReceipt]=useState(session?.receipt||null);
  const [exportState,setExportState]=useState(session?.exportState||(exportIntent?{format:exportIntent.format,name:exportIntent.name}:{})),[exportDialog,setExportDialog]=useState(null);
  const selected=useRef(session?.selected||[]),operation=useRef(session?.operation||null),inFlight=useRef(false),viewer=useRef(session?.viewer||null),current=useRef(null),snapshot=useRef(null),loadedOwner=useRef(null),displayed=useRef(null);
  const profile=useAnnotationProfile();
  const loadOwner=useMemo(()=>({root,projectId,protocolId,revision,nonce,profileUuid:profile.profileUuid,
    profileReady:!!profile.profileUuid&&!profile.loading&&!profile.error,token:preparedContextToken}),
    [root,projectId,protocolId,revision,nonce,profile.profileUuid,profile.loading,profile.error,preparedContextToken]);
  const activeOwner=useRef(loadOwner),claimedContext=useRef(null);
  activeOwner.current=loadOwner;
  const contextFresh=context!==null&&loadedOwner.current===loadOwner;
  // A multi-batch draft save advances authority between batches. Keep the
  // browser on its inert committed view until the complete save settles.
  if(contextFresh&&!busy&&!externalBusy)displayed.current={context,revision};
  const visible=contextFresh&&!busy&&!externalBusy?{context,revision}:displayed.current;
  selected.current=highlighted;current.current=contextFresh?context:null;snapshot.current={filters,selected:selected.current,operation:operation.current,receipt,preview,unconfirmed,acceptPending,viewer:viewer.current,exportState};
  const publish=useCallback(value=>{onSession?.({...snapshot.current,...value});},[onSession]);
  // Inspector publishes from an effect. Keep its callback stable when the
  // cumulative parent rerenders after saving this viewer snapshot.
  const rememberViewer=useCallback(value=>{viewer.current=value;publish({viewer:value});},[publish]);
  useEffect(()=>{publish({});},[filters,receipt,preview,unconfirmed,acceptPending,exportState,publish]);
  useEffect(()=>{
    const controller=new AbortController();setContext(null);setError('');
    // Effect replay may reuse this component's claim. A real remount gets a
    // new ref and cannot claim the parent's consumed response a second time.
    let initial=claimedContext.current?.owner===loadOwner?claimedContext.current.context:null;
    if(!initial&&nonce===0&&!externalBusy){
      initial=takePreparedContext?.({...loadOwner,candidate:item.candidate_revision_uuid});
      if(initial)claimedContext.current={owner:loadOwner,context:initial};
    }
    if(initial){loadedOwner.current=loadOwner;setContext(requireWorkbenchContext(initial));}
    else api(`${root}/context`,{signal:controller.signal}).then(value=>{
      if(!controller.signal.aborted&&activeOwner.current===loadOwner){loadedOwner.current=loadOwner;setContext(requireWorkbenchContext(value));}
    }).catch(error=>{if(!controller.signal.aborted&&activeOwner.current===loadOwner)setError(error.message);});
    return()=>controller.abort();
  },[loadOwner,takePreparedContext]);
  useEffect(()=>{
    if(!acceptOperation||session?.unconfirmed||session?.exportState?.prepared)return;
    const controller=new AbortController();
    api(`${workbenchRoot(protocolId)}/receipts/${encodeURIComponent(acceptOperation)}`,{signal:controller.signal}).then(value=>{
      if(controller.signal.aborted)return;
      if(value.operation_uuid!==acceptOperation||value.candidate_revision_uuid!==item.candidate_revision_uuid||!value.event_uuid||!value.binding)throw new Error('Saved acceptance receipt does not match this incoming proposal.');
      setReceipt(value);
    }).catch(error=>{if(!controller.signal.aborted)setError(`Saved acceptance could not be loaded. ${error.message}`);});
    return()=>controller.abort();
  },[protocolId,acceptOperation,item.candidate_revision_uuid]);
  async function save(decisions,{deferred,selectionMode}={}){
    if(activeOwner.current!==loadOwner||externalBusy||inFlight.current||unconfirmed||exportState.pending||!exportState.exported&&(exportState.acceptOperation||exportState.prepared)||!capabilities.drafts||!current.current)return false;
    inFlight.current=true;setBusy(true);setError('');setPreview(null);operation.current=null;
    try{
      await saveWorkbenchDecisions({root,context:current.current,decisions,deferred,selectionMode},api,value=>{
        if(activeOwner.current===loadOwner){current.current=value;setContext(value);}
      });
      // The server may have committed the old owner's draft. Its reply cannot
      // replace a newer owner's read or navigate that owner out of review.
      if(activeOwner.current!==loadOwner)return false;
      publish({});return true;
    }catch(error){if(activeOwner.current===loadOwner){setError(`Some decisions may already be saved. Refresh the draft before continuing. ${error.message}`);setContext(null);}return false;}
    finally{inFlight.current=false;setBusy(false);}
  }
  function select(next){selected.current=next;setHighlighted(next);publish({selected:next});}
  async function decide({epoch_uuids,changes}){
    const decisions=epoch_uuids.map(epoch_uuid=>({epoch_uuid,...(typeof changes.reviewed==='boolean'?{reviewed:changes.reviewed}:changes.review_state==='approved'?{reviewed:true}:changes.review_state==='unreviewed'?{reviewed:false}:{}),...(typeof changes.included==='boolean'?{excluded:!changes.included}:{})}));
    return save(decisions);
  }
  async function defer(){if(await save([],{deferred:true}))onDefer();}
  function beginSelected(ids,kind='merge'){
    if(activeOwner.current!==loadOwner||externalBusy||inFlight.current||exportLocked||!contextFresh||receipt||preview||selectionIntent)return;
    setError('');
    try{
      const intent={...selectedReview(current.current,ids),kind,scope:current.current.candidate_scope_revision,version:current.current.draft.draft_version};
      if(intent.excluded.length){setError(`${intent.excluded.length} selected epochs are excluded. Adjust the selection or explicitly change those exclusions before continuing.`);return;}
      setSelectionIntent(intent);
      if(!intent.unreviewed.length)void prepareSelection(intent,false);
    }catch(error){setError(error.message);}
  }
  async function prepareSelection(intent,review){
    if(activeOwner.current!==loadOwner||externalBusy||inFlight.current||exportLocked||!current.current)return;
    if(current.current.candidate_scope_revision!==intent.scope||current.current.draft.draft_version!==intent.version){setSelectionIntent(null);setError('The draft changed. Inspect the current selection and choose Merge or Export again.');return;}
    inFlight.current=true;setBusy(true);setError('');setPreview(null);operation.current=null;
    try{
      const value=await prepareSelectedIncoming({root,context:current.current,ids:intent.ids,review},api,value=>{
        if(activeOwner.current===loadOwner){current.current=value;setContext(value);}
      });
      if(activeOwner.current!==loadOwner)return;
      if(intent.kind==='merge'){
        if(exportState.exported)setExportState(nextWorkbenchWorkflow(exportState));
        setPreview(value);operation.current=crypto.randomUUID();publish({preview:value,operation:operation.current});
      }else{
        const next={...nextWorkbenchWorkflow(exportState),mode:'selected',preview:value,phase:'previewed'};
        setExportState(next);publish({exportState:next});setExportDialog(intent.kind==='merge-export');
      }
    }catch(error){if(activeOwner.current===loadOwner){setError(`Draft changes may already be saved. Refresh and inspect the selection before trying again. ${error.message}`);setContext(null);}}
    finally{setSelectionIntent(null);inFlight.current=false;setBusy(false);}
  }
  async function accept(){
    if(activeOwner.current!==loadOwner||externalBusy||!contextFresh&&!unconfirmed||inFlight.current||exportState.pending||!preview||receipt)return;inFlight.current=true;setBusy(true);setError('');
    setAcceptPending(true);publish({acceptPending:true});
    try{const result=await acceptWorkbench(root,preview,operation.current,api);setUnconfirmed(false);setReceipt(result);publish({receipt:result,unconfirmed:false,acceptPending:false,operation:operation.current});setPreview(null);onChange?.();}
    catch(error){
      if(acceptanceFailureKind(error)==='rejected'){
        setPreview(null);operation.current=null;setUnconfirmed(false);publish({unconfirmed:false,acceptPending:false,preview:null,operation:null});
        if(activeOwner.current===loadOwner){setContext(null);setError(`Acceptance was rejected. Refresh the proposal and preview again. ${error.message}`);}
      }else{setUnconfirmed(true);publish({unconfirmed:true,acceptPending:false,preview,operation:operation.current});setError(`Acceptance may have committed. Retry this same operation to recover its receipt; do not create another operation. ${error.message}`);}
    }
    finally{inFlight.current=false;setBusy(false);setAcceptPending(false);}
  }
  const protocol=visible?.context.protocol;
  const readContext=visible?{root,candidate_scope_revision:visible.context.candidate_scope_revision,
    ...(visible.context.tree_selection===true?{tree_selection:true}:{}),
    ...(visible.context.list_selection===true?{list_selection:true,expected_binding_version:visible.context.expected_binding_version}:{}),
    ...(visible.context.tree_column_pages===true?{tree_column_pages:true}:{}),
    ...(visible.context.selection_summary===true?{selection_summary:true,expected_binding_version:visible.context.expected_binding_version}:{}),
    ...(typeof visible.context.candidate_recipe_sha256==='string'&&visible.context.candidate_recipe_sha256&&Number.isSafeInteger(visible.context.expected_binding_version)&&visible.context.expected_binding_version>=0
      ?{cohort_key:JSON.stringify([root,visible.context.candidate_recipe_sha256,visible.context.expected_binding_version])}:{})}:null;
  const adapterReady=capabilities.frozen_browse===true&&InspectorCapabilities.FROZEN_CANDIDATE_INSPECTOR_SUPPORTED===true&&!!protocol;
  const exportLocked=unconfirmed||!!exportState.pending||!exportState.exported&&(!!exportState.acceptOperation||!!exportState.prepared);
  const handledMergeRequests=useRef(new Set());
  useEffect(()=>{
    if(!mergeRequest||handledMergeRequests.current.has(mergeRequest.request_uuid))return;
    if(!mergeIntentMatches(mergeRequest,projectId,protocolId)||scopeKind!=='cumulative_pending'){
      handledMergeRequests.current.add(mergeRequest.request_uuid);onMergeRequestHandled?.('The merge request does not match this cumulative workspace.');return;
    }
    if(externalBusy||busy||!contextFresh&&!error)return;
    handledMergeRequests.current.add(mergeRequest.request_uuid);
    if(error||!contextFresh||!capabilities.additive_accept){onMergeRequestHandled?.('Refresh the incoming draft before requesting a merge preview.');return;}
    if(exportLocked||acceptPending||receipt||preview){onMergeRequestHandled?.('A saved operation or preview is already open. Resolve or cancel it before requesting another merge.');return;}
    if(!Number.isSafeInteger(context.counts?.pending_epochs)||context.counts.pending_epochs<=0){onMergeRequestHandled?.('No confirmed pending additions are available for a merge preview.');return;}
    onMergeRequestHandled?.('Select the epochs to merge, then choose Merge to review and preview them.');
  },[mergeRequest,projectId,protocolId,scopeKind,externalBusy,busy,contextFresh,context,error,exportLocked,acceptPending,receipt,preview,capabilities.additive_accept,onMergeRequestHandled]);
  function cancelPreview(){
    if(inFlight.current||unconfirmed||acceptPending||exportLocked)return;
    setPreview(null);operation.current=null;publish({preview:null,operation:null});
  }
  function openExport(accept){if(!receipt&&!exportLocked){beginSelected(selected.current,accept?'merge-export':'export');return;}setExportDialog(accept);}
  function reviewRemaining(){const next=nextWorkbenchWorkflow({...exportState,receipt});setExportState(next);setReceipt(null);setPreview(null);operation.current=null;publish({receipt:null,preview:null,operation:null,exportState:next});setNonce(value=>value+1);}
  const countLabel=value=>Number.isSafeInteger(value)&&value>=0?number(value):'Unavailable';
  const cells=pendingCounts?pendingCounts.pending_cell_count:contextFresh?context?.counts?.pending_cells:null;
  const epochs=pendingCounts?pendingCounts.pending_epoch_count:contextFresh?context?.counts?.pending_epochs:null;
  const incomingCount=value=>Number.isSafeInteger(value)&&value>0?`+${number(value)}`:countLabel(value);
  const reviewKnown=contextFresh&&!externalBusy&&context.draft.decisions_truncated===false&&Array.isArray(context.draft.decisions)&&context.draft.decisions_total===context.draft.decisions.length;
  const notReviewed=reviewKnown&&!context.draft.decisions.some(value=>value.reviewed);
  const incomingStatus=epochs>0?(notReviewed?'Not reviewed':'Pending merge'):epochs===0?'No pending':'Incoming';
  return <section className="incoming-review">
    <div className="incoming-action-bar" aria-label="Incoming review actions">
      <div className="incoming-bar-metrics" aria-label={scopeKind==='cumulative_pending'?'Distinct pending incoming counts':'Pending proposal counts'}><span className={`incoming-bar-scope ${epochs>0?'is-pending':''}`} title={epochs>0&&notReviewed?'Your current draft has no reviewed incoming epochs':'Unmerged incoming recordings; review and merge remain separate'}>{epochs>0&&notReviewed&&<CircleDot size={11} aria-hidden="true"/>}{incomingStatus}</span>
        <IncomingCellTypes cells={contextFresh&&!busy&&!externalBusy?context.protocol?.cells:null} count={contextFresh?context.protocol?.counts?.cells:null} scope="Frozen proposal" trigger={<span><NeuronIcon size={18}/><strong>{incomingCount(cells)}</strong><small>cells</small></span>}/>
        <span><Activity size={18} aria-hidden="true"/><strong>{incomingCount(epochs)}</strong><small>epochs</small></span>
      </div>
      <div className="incoming-bar-actions">
        <div className="incoming-draft-host" ref={setDraftSelectionTarget}/>
        <button disabled={busy||externalBusy||!!selectionIntent||!!preview||unconfirmed||!contextFresh&&!receipt&&!exportLocked||!receipt&&!exportLocked&&!highlighted.length||!capabilities.incoming_export} title={capabilities.incoming_export?(receipt?'Export accepted additions':'Export exact incoming additions'):'Incoming-only export service is not yet available'} onClick={()=>openExport(false)}><Download size={14} aria-hidden="true"/> {receipt?'Export accepted':'Export'}</button>
        <button disabled={busy||externalBusy} title="Leave review; saved draft and pending operations remain available" onClick={onDefer}><X size={14} aria-hidden="true"/> Cancel</button>
      <details className="incoming-review-details"><summary>Review details</summary><div>        <button disabled={busy||externalBusy||!!selectionIntent||!!preview||unconfirmed||!contextFresh&&!receipt&&!exportLocked||!receipt&&!exportLocked&&!highlighted.length||!capabilities.incoming_export||!capabilities.additive_accept} onClick={()=>openExport(true)}><GitMerge size={14} aria-hidden="true"/> Merge & export</button>
<div className="incoming-selection-tools">
      {onRefresh&&<button className="incoming-utility" disabled={refreshing} onClick={onRefresh}><RefreshCw size={13} aria-hidden="true"/> Refresh</button>}
      {onHistory&&<button className="incoming-utility" onClick={onHistory}><History size={13} aria-hidden="true"/> Proposal history</button>}
      </div>
        <p>{scopeKind==='cumulative_pending'?'Distinct pending cells and epochs across saved proposals. Review opens only the unmerged incoming set; original proposals remain in history.':'This browser shows one frozen proposal. Its pending counts may overlap other proposals; the queue totals count each identity once.'}</p>
        <p>Review marks and exclusions are saved to your draft. Shared tags publish immediately. Merge to main adds eligible epochs and preserves existing main recordings and curation. Opening this view does not mark anything reviewed.</p>
        <p>Select marks exact epochs for Merge or Export. Merge saves that selection to your draft, asks for any required review, and shows a fresh preview before confirmation. Shared tags and exclusions stay separate. Cancel keeps saved draft changes and does not undo a submitted operation.</p>
        {exportIntent&&<p>Reused incoming export settings. The previous artifact stays unchanged; export requires an explicit action.</p>}
        {contextFresh&&<p>Draft version {context.draft.draft_version} · scope <code>{context.candidate_scope_revision.slice(0,12)}</code> · proposal <code>{item.candidate_revision_uuid.slice(0,8)}</code></p>}
        {scopeKind!=='cumulative_pending'&&contextFresh&&context?.counts&&<p>{countLabel(context.counts.incoming_epochs)} proposal additions · {countLabel(context.counts.already_present_epochs)} already in main.</p>}
        <button disabled={busy||externalBusy||exportLocked||!capabilities.drafts||!contextFresh} onClick={defer}>Defer & return to queue</button>
        {onNext&&<button disabled={busy||externalBusy||unconfirmed} onClick={onNext}>Next proposal</button>}
      </div></details>
      </div>
    </div>
      {context?.draft.deferred&&<button disabled={busy||externalBusy||exportLocked||!capabilities.drafts} onClick={()=>save([],{deferred:false})}>Resume deferred review</button>}
    {exportLocked&&!unconfirmed&&!exportState.exported&&<p role="status">A saved export workflow is awaiting a receipt. Reopen Export to resume it before changing this draft.</p>}
    {error&&<div className="error" role="alert">{error}<button disabled={busy||externalBusy} onClick={()=>setNonce(value=>value+1)}>Refresh draft</button></div>}
    {!contextFresh&&!error&&<p role="status">Loading frozen proposal…</p>}
    {selectionIntent&&<section className="incoming-selection-review" aria-label="Review selected epochs"><strong>{number(selectionIntent.ids.length)} selected epochs</strong><span>{number(selectionIntent.unreviewed.length)} need your review</span><button className="primary" disabled={busy||externalBusy||!contextFresh} onClick={()=>prepareSelection(selectionIntent,true)}>Mark selected reviewed & preview</button><button disabled={busy||externalBusy} onClick={()=>setSelectionIntent(null)}>Cancel review</button><p>Review marks are saved to your draft. Main changes only after the next preview is confirmed.</p></section>}
    {preview&&<IncomingMergePreview preview={preview} context={contextFresh?context:null}><button disabled={busy||externalBusy||!contextFresh&&!unconfirmed||(!exportState.exported&&(!!exportState.prepared||!!exportState.acceptOperation))||!capabilities.additive_accept||!!receipt||!unconfirmed&&preview.accepted_epoch_count===0} className="primary" onClick={accept}>{busy?'Accepting…':unconfirmed?'Recover acceptance receipt':'Add these additions to main'}</button>{!unconfirmed&&<button disabled={busy||acceptPending||exportLocked} onClick={cancelPreview}>Cancel merge preview</button>}{preview.accepted_epoch_count===0&&!unconfirmed&&<p role="status">No eligible new epochs in this preview. Main is unchanged.</p>}</IncomingMergePreview>}
    {receipt&&<p role="status">Acceptance saved · binding version {receipt.binding.version} · receipt {receipt.event_uuid}.{!exportState.exported&&' No export artifact has been confirmed.'}</p>}
    {receipt&&!exportLocked&&<button disabled={busy||externalBusy} onClick={reviewRemaining}>Review remaining additions</button>}
    {(exportState.completed||[]).map((value,index)=><p key={value.exported?.dataset_uuid||value.receipt?.event_uuid||index}>{value.receipt&&<>Earlier acceptance · receipt {value.receipt.event_uuid} </>}{value.exported&&<a href={value.exported.download_url} download>{value.exported.name||'Download earlier incoming export'}</a>}</p>)}
    {exportDialog!==null&&<WorkbenchExportDialog selectedOnly externalBusy={externalBusy||!contextFresh&&!exportLocked&&!receipt} protocolId={protocolId} item={item} accept={exportDialog} acceptReceipt={receipt} state={exportState} onState={value=>{setExportState(value);if(value.receipt)setReceipt(value.receipt);publish({exportState:value,...(value.receipt?{receipt:value.receipt}:{})});}} onClose={()=>{setExportDialog(null);setNonce(value=>value+1);}} onChanged={onChange}/>}
    {visible&&adapterReady?<div className="incoming-browser" tabIndex={-1} aria-label="Incoming epoch browser">{filterTarget&&createPortal(<ProtocolViewFilter readContext={readContext} purpose="browse" projectId={projectId} protocol={protocol} filters={filters} revision={visible.revision} disabled={busy||externalBusy||exportLocked||!!selectionIntent||!!preview} onChange={setFilters}/>,filterTarget)}<Inspector draftSelectionTarget={draftSelectionTarget} readPaused={busy||externalBusy||!contextFresh} draftSelection={{selected:highlighted,disabled:busy||externalBusy||exportLocked||!!selectionIntent||!!preview||!capabilities.drafts||!contextFresh||!!receipt,onMerge:capabilities.additive_accept?ids=>beginSelected(ids):null}} toolbarTarget={toolbarTarget} readContext={readContext} projectId={projectId} protocol={protocol} filters={filters} revision={`${visible.revision}:${visible.context.draft.draft_version}`} onChange={onChange} onBack={defer} onQC={onQC} onFilterChange={setFilters} onTagFilter={predicate=>setFilters(current=>({...clearTagFilters(current),tag_predicate:JSON.stringify(predicate)}))} onSelectionChange={select} onReviewDecision={decide} initialNavigation={viewer.current} onSessionChange={rememberViewer} splitRecipe={session?.splitRecipe||['date','cell','block']} onExport={capabilities.incoming_export&&!unconfirmed&&!externalBusy&&contextFresh?()=>openExport(false):undefined}/></div>:contextFresh&&<p role="status">Frozen proposal loaded. The candidate browser adapter is not yet available in this build. No global query is substituted.</p>}
  </section>;
}
