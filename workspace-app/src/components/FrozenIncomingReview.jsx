import {useCallback,useEffect,useRef,useState} from 'react';
import {api,number} from '../api.js';
import Inspector,* as InspectorCapabilities from './Inspector.jsx';
import ProtocolViewFilter from './ProtocolViewFilter.jsx';
import {acceptWorkbench,acceptanceFailureKind,previewWorkbench,requireWorkbenchContext,saveWorkbenchDecisions,workbenchCandidateRoot,workbenchPreviewCounts} from '../workbenchAuthority.js';

export default function FrozenIncomingReview({projectId,protocolId,item,revision,onChange,onDefer,onNext,onQC,session,onSession,capabilities={}}){
  const root=workbenchCandidateRoot(protocolId,item.candidate_revision_uuid);
  const [context,setContext]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[nonce,setNonce]=useState(0);
  const [unconfirmed,setUnconfirmed]=useState(session?.unconfirmed||false);
  const [highlighted,setHighlighted]=useState(session?.selected||[]);
  const [filters,setFilters]=useState(session?.filters||{}),[preview,setPreview]=useState(session?.preview||null),[receipt,setReceipt]=useState(session?.receipt||null);
  const selected=useRef(session?.selected||[]),operation=useRef(session?.operation||null),inFlight=useRef(false),viewer=useRef(session?.viewer||null),current=useRef(null),snapshot=useRef(null);
  selected.current=highlighted;current.current=context;snapshot.current={filters,selected:selected.current,operation:operation.current,receipt,preview,unconfirmed,viewer:viewer.current};
  const publish=useCallback(value=>{onSession?.({...snapshot.current,...value});},[onSession]);
  useEffect(()=>{publish({});},[filters,receipt,preview,unconfirmed,publish]);
  useEffect(()=>{
    const controller=new AbortController();setContext(null);setError('');
    api(`${root}/context`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setContext(requireWorkbenchContext(value));}).catch(error=>{if(!controller.signal.aborted)setError(error.message);});
    return()=>controller.abort();
  },[root,nonce]);
  async function save(decisions,{deferred,selectionMode}={}){
    if(inFlight.current||unconfirmed||!capabilities.drafts||!current.current)return false;
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
    if(inFlight.current||unconfirmed||!capabilities.additive_accept||!context)return;inFlight.current=true;setBusy(true);setError('');
    try{const value=await previewWorkbench(root,context,mode,api,value=>{current.current=value;setContext(value);});workbenchPreviewCounts(value);setPreview(value);operation.current=crypto.randomUUID();publish({preview:value,operation:operation.current});}
    catch(error){setError(error.message);setPreview(null);}finally{inFlight.current=false;setBusy(false);}
  }
  async function accept(){
    if(inFlight.current||!preview||receipt)return;inFlight.current=true;setBusy(true);setError('');
    try{const result=await acceptWorkbench(root,preview,operation.current,api);setUnconfirmed(false);setReceipt(result);publish({receipt:result,unconfirmed:false,operation:operation.current});setPreview(null);onChange?.();}
    catch(error){
      if(acceptanceFailureKind(error)==='rejected'){
        setPreview(null);operation.current=null;setUnconfirmed(false);publish({unconfirmed:false,preview:null,operation:null});setContext(null);
        setError(`Acceptance was rejected. Refresh the proposal and preview again. ${error.message}`);
      }else{setUnconfirmed(true);publish({unconfirmed:true,preview,operation:operation.current});setError(`Acceptance may have committed. Retry this same operation to recover its receipt; do not create another operation. ${error.message}`);}
    }
    finally{inFlight.current=false;setBusy(false);}
  }
  const protocol=context?.protocol;
  const adapterReady=capabilities.frozen_browse===true&&InspectorCapabilities.FROZEN_CANDIDATE_INSPECTOR_SUPPORTED===true&&!!protocol;
  return <section>
    <div className="incoming-review-context"><strong>Frozen incoming additions</strong><code>{item.candidate_revision_uuid.slice(0,8)}</code><button disabled={busy} onClick={onDefer}>Back to queue</button><button disabled={busy||unconfirmed||!capabilities.drafts||!context} onClick={defer}>Defer & return to queue</button>{onNext&&<button disabled={busy||unconfirmed} onClick={onNext}>Next proposal</button>}
      <p>Review marks and exclusions are saved to your draft. Shared tags publish immediately. Adding to main preserves its existing epochs and curation; opening this view does not mark anything reviewed.</p>
      {context?.draft.deferred&&<button disabled={busy||unconfirmed||!capabilities.drafts} onClick={()=>save([],{deferred:false})}>Resume deferred review</button>}
      {context&&<span>Draft version {context.draft.draft_version} · scope {context.candidate_scope_revision.slice(0,12)}</span>}
      <button disabled={busy||unconfirmed||!capabilities.drafts||!context||!selected.current.length} onClick={()=>saveHighlights(true)}>Save highlighted as selected</button><button disabled={busy||unconfirmed||!capabilities.drafts||!context||!selected.current.length} onClick={()=>saveHighlights(false)}>Clear highlighted selections</button>
      <button disabled={busy||unconfirmed||!capabilities.additive_accept||!context||!!receipt} onClick={()=>compare('selected')}>Preview selected additions</button><button disabled={busy||unconfirmed||!capabilities.additive_accept||!context||!!receipt} onClick={()=>compare('all')}>Preview accept all</button><button disabled title="Incoming-only export service is not yet available">Export new selection</button><button disabled title="Requires the incoming-only export service and staged receipt">Accept & export</button>
    </div>
    {error&&<div className="error" role="alert">{error}<button disabled={busy} onClick={()=>setNonce(value=>value+1)}>Refresh draft</button></div>}
    {!context&&!error&&<p role="status">Loading frozen proposal…</p>}
    {preview&&<section className="incoming-proposal" aria-label="Additive acceptance preview"><h2>{preview.mode==='all'?'All eligible incoming additions':'Selected incoming additions'}</h2><p>Existing main epochs stay included. Explicit draft exclusions stay excluded.</p><dl>{workbenchPreviewCounts(preview).map(({key,label,count})=><div key={key}><dt>{label}</dt><dd>{number(count)}</dd></div>)}</dl><button disabled={busy||!capabilities.additive_accept||!!receipt} className="primary" onClick={accept}>{busy?'Accepting…':unconfirmed?'Recover acceptance receipt':'Add these additions to main'}</button></section>}
    {receipt&&<p role="status">Added to main · binding version {receipt.binding.version} · receipt {receipt.event_uuid}. No export artifact was created.</p>}
    {context&&adapterReady?<><ProtocolViewFilter readContext={{root,candidate_scope_revision:context.candidate_scope_revision}} purpose="browse" projectId={projectId} protocol={protocol} filters={filters} revision={revision} disabled={busy||unconfirmed} onChange={setFilters}/><Inspector readContext={{root,candidate_scope_revision:context.candidate_scope_revision}} projectId={projectId} protocol={protocol} filters={filters} revision={`${revision}:${context.draft.draft_version}`} onChange={onChange} onBack={defer} onQC={onQC} onFilterChange={setFilters} onSelectionChange={select} onReviewDecision={decide} initialNavigation={viewer.current} onSessionChange={value=>{viewer.current=value;publish({viewer:value});}} splitRecipe={session?.splitRecipe||['date','cell','block']} onExport={()=>{}}/></>:context&&<p role="status">Frozen proposal loaded. The candidate browser adapter is not yet available in this build. No global query is substituted.</p>}
  </section>;
}
