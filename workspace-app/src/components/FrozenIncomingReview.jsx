import {useCallback,useEffect,useRef,useState} from 'react';
import {api,number} from '../api.js';
import {Activity,CheckSquare,Download,GitMerge,History,Layers,RefreshCw,Search,Square,X} from 'lucide-react';
import NeuronIcon from './NeuronIcon.jsx';
import Inspector,* as InspectorCapabilities from './Inspector.jsx';
import ProtocolViewFilter from './ProtocolViewFilter.jsx';
import WorkbenchExportDialog from './WorkbenchExportDialog.jsx';
import {nextWorkbenchWorkflow} from '../workbenchExport.js';
import {acceptWorkbench,acceptanceFailureKind,previewWorkbench,requireWorkbenchContext,saveWorkbenchDecisions,workbenchCandidateRoot,workbenchRoot,workbenchPreviewCounts} from '../workbenchAuthority.js';

export default function FrozenIncomingReview({projectId,protocolId,item,revision,onChange,onDefer,onNext,onQC,session,onSession,capabilities={},exportIntent=null,acceptOperation=null,scopeKind='proposal',externalBusy=false,preserveBrowser=false,pendingCounts=null,onHistory,onRefresh,refreshing=false}){
  const browserRegion=useRef(null);
  const root=workbenchCandidateRoot(protocolId,item.candidate_revision_uuid);
  const [context,setContext]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[nonce,setNonce]=useState(0);
  const [unconfirmed,setUnconfirmed]=useState(session?.unconfirmed||session?.acceptPending||false),[acceptPending,setAcceptPending]=useState(false);
  const [highlighted,setHighlighted]=useState(session?.selected||[]);
  const [filters,setFilters]=useState(session?.filters||{}),[preview,setPreview]=useState(session?.preview||null),[receipt,setReceipt]=useState(session?.receipt||null);
  const [exportState,setExportState]=useState(session?.exportState||(exportIntent?{format:exportIntent.format,name:exportIntent.name}:{})),[exportDialog,setExportDialog]=useState(null);
  const selected=useRef(session?.selected||[]),operation=useRef(session?.operation||null),inFlight=useRef(false),viewer=useRef(session?.viewer||null),current=useRef(null),snapshot=useRef(null),loadedRevision=useRef(revision),displayed=useRef(null);
  const contextFresh=context!==null&&loadedRevision.current===revision;
  if(contextFresh&&!externalBusy)displayed.current={context,revision};
  const visible=contextFresh&&!externalBusy?{context,revision}:externalBusy||preserveBrowser?displayed.current:null;
  selected.current=highlighted;current.current=contextFresh?context:null;snapshot.current={filters,selected:selected.current,operation:operation.current,receipt,preview,unconfirmed,acceptPending,viewer:viewer.current,exportState};
  const publish=useCallback(value=>{onSession?.({...snapshot.current,...value});},[onSession]);
  useEffect(()=>{publish({});},[filters,receipt,preview,unconfirmed,acceptPending,exportState,publish]);
  useEffect(()=>{
    const controller=new AbortController();setContext(null);setError('');
    api(`${root}/context`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted){loadedRevision.current=revision;setContext(requireWorkbenchContext(value));}}).catch(error=>{if(!controller.signal.aborted)setError(error.message);});
    return()=>controller.abort();
  },[root,nonce,revision]);
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
    if(externalBusy||inFlight.current||unconfirmed||exportState.pending||!exportState.exported&&(exportState.acceptOperation||exportState.prepared)||!capabilities.drafts||!current.current)return false;
    inFlight.current=true;setBusy(true);setError('');setPreview(null);operation.current=null;
    try{
      await saveWorkbenchDecisions({root,context:current.current,decisions,deferred,selectionMode},api,value=>{current.current=value;setContext(value);});
      publish({});return true;
    }catch(error){setError(`Some decisions may already be saved. Refresh the draft before continuing. ${error.message}`);setContext(null);return false;}
    finally{inFlight.current=false;setBusy(false);}
  }
  function select(next){selected.current=next;setHighlighted(next);publish({selected:next});}
  async function saveHighlights(value){return save(selected.current.map(epoch_uuid=>({epoch_uuid,selected:value})),{selectionMode:'selected'});}
  async function decide({epoch_uuids,changes}){
    const decisions=epoch_uuids.map(epoch_uuid=>({epoch_uuid,...(typeof changes.reviewed==='boolean'?{reviewed:changes.reviewed}:changes.review_state==='approved'?{reviewed:true}:changes.review_state==='unreviewed'?{reviewed:false}:{}),...(typeof changes.included==='boolean'?{excluded:!changes.included}:{})}));
    return save(decisions);
  }
  async function defer(){if(await save([],{deferred:true}))onDefer();}
  async function compare(mode){
    if(externalBusy||inFlight.current||unconfirmed||exportState.pending||!capabilities.additive_accept||!contextFresh)return;inFlight.current=true;setBusy(true);setError('');
    if(exportState.exported)setExportState(nextWorkbenchWorkflow(exportState));
    try{const value=await previewWorkbench(root,context,mode,api,value=>{current.current=value;setContext(value);});workbenchPreviewCounts(value);setPreview(value);operation.current=crypto.randomUUID();publish({preview:value,operation:operation.current});}
    catch(error){setError(error.message);setPreview(null);}finally{inFlight.current=false;setBusy(false);}
  }
  async function accept(){
    if(externalBusy||!contextFresh&&!unconfirmed||inFlight.current||exportState.pending||!preview||receipt)return;inFlight.current=true;setBusy(true);setError('');
    setAcceptPending(true);publish({acceptPending:true});
    try{const result=await acceptWorkbench(root,preview,operation.current,api);setUnconfirmed(false);setReceipt(result);publish({receipt:result,unconfirmed:false,acceptPending:false,operation:operation.current});setPreview(null);onChange?.();}
    catch(error){
      if(acceptanceFailureKind(error)==='rejected'){
        setPreview(null);operation.current=null;setUnconfirmed(false);publish({unconfirmed:false,acceptPending:false,preview:null,operation:null});setContext(null);
        setError(`Acceptance was rejected. Refresh the proposal and preview again. ${error.message}`);
      }else{setUnconfirmed(true);publish({unconfirmed:true,acceptPending:false,preview,operation:operation.current});setError(`Acceptance may have committed. Retry this same operation to recover its receipt; do not create another operation. ${error.message}`);}
    }
    finally{inFlight.current=false;setBusy(false);setAcceptPending(false);}
  }
  const protocol=visible?.context.protocol;
  const readContext=visible?{root,candidate_scope_revision:visible.context.candidate_scope_revision,
    ...(typeof visible.context.candidate_recipe_sha256==='string'&&visible.context.candidate_recipe_sha256&&Number.isSafeInteger(visible.context.expected_binding_version)&&visible.context.expected_binding_version>=0
      ?{cohort_key:JSON.stringify([root,visible.context.candidate_recipe_sha256,visible.context.expected_binding_version])}:{})}:null;
  const adapterReady=capabilities.frozen_browse===true&&InspectorCapabilities.FROZEN_CANDIDATE_INSPECTOR_SUPPORTED===true&&!!protocol;
  const exportLocked=unconfirmed||!!exportState.pending||!exportState.exported&&(!!exportState.acceptOperation||!!exportState.prepared);
  function openExport(accept){if(exportState.exported||exportState.phase==='rejected')setExportState(nextWorkbenchWorkflow(exportState));setExportDialog(accept);}
  function reviewRemaining(){const next=nextWorkbenchWorkflow({...exportState,receipt});setExportState(next);setReceipt(null);setPreview(null);operation.current=null;publish({receipt:null,preview:null,operation:null,exportState:next});setNonce(value=>value+1);}
  const countLabel=value=>Number.isSafeInteger(value)&&value>=0?number(value):'Unavailable';
  const cells=pendingCounts?pendingCounts.pending_cell_count:contextFresh?context?.counts?.pending_cells:null;
  const epochs=pendingCounts?pendingCounts.pending_epoch_count:contextFresh?context?.counts?.pending_epochs:null;
  // The server remains the authority for exact eligibility, including truncated
  // draft decisions. Never infer a count by summing proposals or viewer rows.
  const noReviewedSelection=contextFresh&&context.draft.selection_mode==='selected'&&context.draft.decisions_truncated===false&&Array.isArray(context.draft.decisions)&&!context.draft.decisions.some(value=>value.selected&&value.reviewed&&!value.excluded);
  function explore(){browserRegion.current?.focus();browserRegion.current?.scrollIntoView({block:'nearest'});}
  return <section className="incoming-review">
    <div className="incoming-action-bar" aria-label="Incoming review actions">
      <div className="incoming-bar-metrics" aria-label={scopeKind==='cumulative_pending'?'Distinct pending incoming counts':'Pending proposal counts'}><span className="incoming-bar-scope">Incoming</span>
        <span><NeuronIcon size={18}/><strong>{countLabel(cells)}</strong><small>cells</small></span>
        <span><Activity size={18} aria-hidden="true"/><strong>{countLabel(epochs)}</strong><small>epochs</small></span>
      </div>
      <div className="incoming-bar-actions">
        <button className="primary" disabled={!visible||!adapterReady} onClick={explore}><Search size={14} aria-hidden="true"/> Review / Explore</button>
        <button disabled={busy||externalBusy||exportLocked||!capabilities.additive_accept||!contextFresh||!!receipt||noReviewedSelection} title="Preview saved selected and reviewed additions before merging to main" onClick={()=>compare('selected')}><GitMerge size={14} aria-hidden="true"/> Merge selected epochs</button>
        <button disabled={busy||externalBusy||exportLocked||!capabilities.additive_accept||!contextFresh||!!receipt||context?.counts?.pending_epochs===0} title="Preview all eligible incoming additions, keeping draft exclusions" onClick={()=>compare('all')}><Layers size={14} aria-hidden="true"/> Merge all</button>
        <button disabled={busy||externalBusy||unconfirmed||!contextFresh&&!receipt&&!exportLocked||!capabilities.incoming_export} title={capabilities.incoming_export?(receipt?'Export accepted additions':'Export exact incoming additions'):'Incoming-only export service is not yet available'} onClick={()=>openExport(false)}><Download size={14} aria-hidden="true"/> {receipt?'Export accepted':'Export'}</button>
        <button disabled={busy||externalBusy||unconfirmed||!contextFresh&&!receipt&&!exportLocked||!capabilities.incoming_export||!capabilities.additive_accept} onClick={()=>openExport(true)}><GitMerge size={14} aria-hidden="true"/> Merge & export</button>
        <button disabled={busy||externalBusy} title="Leave review; saved draft and pending operations remain available" onClick={onDefer}><X size={14} aria-hidden="true"/> Cancel</button>
      </div>
    </div>
    <div className="incoming-selection-tools">
      <button disabled={busy||externalBusy||exportLocked||!capabilities.drafts||!contextFresh||!selected.current.length} onClick={()=>saveHighlights(true)}><CheckSquare size={14} aria-hidden="true"/> Save highlighted as selected</button>
      <button disabled={busy||externalBusy||exportLocked||!capabilities.drafts||!contextFresh||!selected.current.length} onClick={()=>saveHighlights(false)}><Square size={14} aria-hidden="true"/> Clear highlighted selections</button>
      {onRefresh&&<button className="incoming-utility" disabled={refreshing} onClick={onRefresh}><RefreshCw size={13} aria-hidden="true"/> Refresh</button>}
      {onHistory&&<button className="incoming-utility" onClick={onHistory}><History size={13} aria-hidden="true"/> Proposal history</button>}
      <details className="incoming-review-details"><summary>Review details</summary><div>
        <p>{scopeKind==='cumulative_pending'?'Distinct pending cells and epochs across saved proposals. Review opens only the unmerged incoming set; original proposals remain in history.':'This browser shows one frozen proposal. Its pending counts may overlap other proposals; the queue totals count each identity once.'}</p>
        <p>Review marks and exclusions are saved to your draft. Shared tags publish immediately. Merge to main adds eligible epochs and preserves existing main recordings and curation. Opening this view does not mark anything reviewed.</p>
        <p>Merge selected uses saved selected and reviewed epochs. Merge all deliberately approves eligible incoming additions and retains draft exclusions. Both show exact counts before confirmation. Cancel leaves the draft pending and does not roll back a submitted operation.</p>
        {exportIntent&&<p>Reused incoming export settings. The previous artifact stays unchanged; export requires an explicit action.</p>}
        {contextFresh&&<p>Draft version {context.draft.draft_version} · scope <code>{context.candidate_scope_revision.slice(0,12)}</code> · proposal <code>{item.candidate_revision_uuid.slice(0,8)}</code></p>}
        {scopeKind!=='cumulative_pending'&&contextFresh&&context?.counts&&<p>{countLabel(context.counts.incoming_epochs)} proposal additions · {countLabel(context.counts.already_present_epochs)} already in main.</p>}
        <button disabled={busy||externalBusy||exportLocked||!capabilities.drafts||!contextFresh} onClick={defer}>Defer & return to queue</button>
        {onNext&&<button disabled={busy||externalBusy||unconfirmed} onClick={onNext}>Next proposal</button>}
      </div></details>
      {context?.draft.deferred&&<button disabled={busy||externalBusy||exportLocked||!capabilities.drafts} onClick={()=>save([],{deferred:false})}>Resume deferred review</button>}
    </div>
    {exportLocked&&!unconfirmed&&!exportState.exported&&<p role="status">A saved export workflow is awaiting a receipt. Reopen Export to resume it before changing this draft.</p>}
    {error&&<div className="error" role="alert">{error}<button disabled={busy||externalBusy} onClick={()=>setNonce(value=>value+1)}>Refresh draft</button></div>}
    {!contextFresh&&!error&&<p role="status">Loading frozen proposal…</p>}
    {preview&&<section className="incoming-proposal" aria-label="Additive acceptance preview"><h2>{preview.mode==='all'?'All eligible incoming additions':'Selected incoming additions'}</h2><p>Existing main epochs stay included. Explicit draft exclusions stay excluded.</p><dl>{workbenchPreviewCounts(preview).map(({key,label,count})=><div key={key}><dt>{label}</dt><dd>{number(count)}</dd></div>)}</dl><button disabled={busy||externalBusy||!contextFresh&&!unconfirmed||(!exportState.exported&&(!!exportState.prepared||!!exportState.acceptOperation))||!capabilities.additive_accept||!!receipt} className="primary" onClick={accept}>{busy?'Accepting…':unconfirmed?'Recover acceptance receipt':'Add these additions to main'}</button></section>}
    {receipt&&<p role="status">Acceptance saved · binding version {receipt.binding.version} · receipt {receipt.event_uuid}.{!exportState.exported&&' No export artifact has been confirmed.'}</p>}
    {receipt&&!exportLocked&&<button disabled={busy||externalBusy} onClick={reviewRemaining}>Review remaining additions</button>}
    {(exportState.completed||[]).map((value,index)=><p key={value.exported?.dataset_uuid||value.receipt?.event_uuid||index}>{value.receipt&&<>Earlier acceptance · receipt {value.receipt.event_uuid} </>}{value.exported&&<a href={value.exported.download_url} download>{value.exported.name||'Download earlier incoming export'}</a>}</p>)}
    {exportDialog!==null&&<WorkbenchExportDialog externalBusy={externalBusy||!contextFresh&&!exportLocked&&!receipt} protocolId={protocolId} item={item} accept={exportDialog} acceptReceipt={receipt} state={exportState} onState={value=>{setExportState(value);if(value.receipt)setReceipt(value.receipt);publish({exportState:value,...(value.receipt?{receipt:value.receipt}:{})});}} onClose={()=>{setExportDialog(null);setNonce(value=>value+1);}} onChanged={onChange}/>}
    {visible&&adapterReady?<div className="incoming-browser" ref={browserRegion} tabIndex={-1} aria-label="Incoming epoch browser"><ProtocolViewFilter readContext={readContext} purpose="browse" projectId={projectId} protocol={protocol} filters={filters} revision={visible.revision} disabled={busy||externalBusy||exportLocked} onChange={setFilters}/><Inspector readContext={readContext} projectId={projectId} protocol={protocol} filters={filters} revision={`${visible.revision}:${visible.context.draft.draft_version}`} onChange={onChange} onBack={defer} onQC={onQC} onFilterChange={setFilters} onSelectionChange={select} onReviewDecision={decide} initialNavigation={viewer.current} onSessionChange={value=>{viewer.current=value;publish({viewer:value});}} splitRecipe={session?.splitRecipe||['date','cell','block']} onExport={capabilities.incoming_export&&!unconfirmed&&!externalBusy&&contextFresh?()=>openExport(false):undefined}/></div>:contextFresh&&<p role="status">Frozen proposal loaded. The candidate browser adapter is not yet available in this build. No global query is substituted.</p>}
  </section>;
}
