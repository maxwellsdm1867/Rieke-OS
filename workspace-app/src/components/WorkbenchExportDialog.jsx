import {useEffect,useRef,useState} from 'react';
import {api,number} from '../api.js';
import {acceptWorkbench,acceptanceFailureKind,previewWorkbench,requireWorkbenchContext,workbenchCandidateRoot,workbenchPreviewCounts} from '../workbenchAuthority.js';
import {acceptedExportRequest,candidateExportRequest,submitWorkbenchExport} from '../workbenchExport.js';
import {ExportDestination} from './ProtocolExports.jsx';
import {exportDownloadLabel} from '../exportFormats.js';
import './ExportSelectionDialog.css';

export default function WorkbenchExportDialog({protocolId,item,accept=false,state={},onState,onClose,onChanged,acceptReceipt=null}){
  const root=workbenchCandidateRoot(protocolId,item.candidate_revision_uuid),dialog=useRef(null),inFlight=useRef(false),saved=useRef(state);
  saved.current=state;
  const accepting=state.workflow?state.workflow==='accept-export':accept;
  const [context,setContext]=useState(null),[loadError,setLoadError]=useState(''),[busy,setBusy]=useState(false);
  const [format,setFormat]=useState(state.format||'wheeler-sqlite'),[name,setName]=useState(state.name||''),[mode,setMode]=useState(state.mode||'selected');
  const committed=state.receipt||acceptReceipt,locked=busy||!!state.prepared||!!state.acceptOperation;
  function publish(patch){saved.current={...saved.current,...patch};onState(saved.current);}
  useEffect(()=>{const el=dialog.current;el?.showModal?.();return()=>el?.close?.();},[]);
  useEffect(()=>{
    if(committed||state.prepared||state.preview)return;
    const controller=new AbortController();
    api(`${root}/context`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted){setContext(requireWorkbenchContext(value));if(saved.current.phase==='rejected')publish({phase:null,error:''});}}).catch(error=>{if(!controller.signal.aborted)setLoadError(error.message);});
    return()=>controller.abort();
  },[root,!!committed,!!state.prepared,!!state.preview]);
  async function submit(event){
    event.preventDefault();if(inFlight.current)return;inFlight.current=true;setBusy(true);
    let receipt=committed,phase=receipt?'exporting':'comparing';
    publish({error:'',format,name,mode,workflow:accepting?'accept-export':'export',...(receipt?{receipt}:{})});
    try{
      let preview=saved.current.preview;
      if(!receipt&&!saved.current.prepared&&!preview){
        preview=await previewWorkbench(root,context,mode,api,setContext);workbenchPreviewCounts(preview);publish({preview});
      }
      if(accepting&&!receipt){
        phase='accepting';const op=saved.current.acceptOperation||crypto.randomUUID();publish({acceptOperation:op,phase});
        receipt=await acceptWorkbench(root,preview,op,api);publish({receipt,phase:'accepted'});onChanged?.();
      }
      phase='exporting';let prepared=saved.current.prepared;
      if(!prepared){
        const operationUuid=saved.current.exportOperation||crypto.randomUUID();publish({exportOperation:operationUuid});
        prepared=receipt?await acceptedExportRequest(protocolId,receipt,{format,name,operationUuid},api):candidateExportRequest(root,preview,{format,name,operationUuid});
        publish({prepared,phase});
      }
      const exported=await submitWorkbenchExport(prepared,api);publish({receipt,exported,phase:'exported'});onChanged?.();
    }catch(error){
      if(phase==='accepting'&&acceptanceFailureKind(error)==='rejected'){
        publish({phase:'rejected',acceptOperation:null,preview:null,error:`Acceptance rejected. Reopen to refresh the proposal. ${error.message}`});setContext(null);
      }else publish({receipt,phase:phase==='accepting'?'acceptance-unconfirmed':receipt?'export-failed':saved.current.prepared?'export-unconfirmed':'failed',error:error.message});
    }finally{inFlight.current=false;setBusy(false);}
  }
  return <dialog ref={dialog} className="export-selection-dialog" aria-label={accepting?'Accept and export incoming additions':'Export incoming additions'} onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
    <header><h2>{accepting?'Accept & export':'Export new additions'}</h2><button disabled={busy} onClick={onClose}>Close</button></header>
    <div className="export-selection-body">
      <p>{accepting?'Add eligible incoming epochs to main, then export only those newly accepted epochs. Existing main epochs and curation stay included.':'Export only new incoming epochs absent from main. Main membership stays unchanged.'} Shared tags are saved separately; this action does not publish scientific approval tags.</p>
      {committed&&<p role="status">Acceptance saved · binding version {committed.binding.version} · receipt {committed.event_uuid}. Export retries do not apply additions again.</p>}
      {loadError&&<p role="alert">{loadError} Close and reopen to load the frozen proposal.</p>}
      {state.error&&<p role="alert">{committed?'Acceptance succeeded; export has not been confirmed. ':''}{state.error}</p>}
      {state.phase==='acceptance-unconfirmed'&&<p>Acceptance may have committed. Retry the same saved operation to recover its receipt before exporting.</p>}
      {state.phase==='export-unconfirmed'&&<p>Export may have committed. Retry the same export operation to recover its artifact.</p>}
      {!state.exported&&<form onSubmit={submit}>
        {!committed&&<fieldset disabled={locked}><legend>Incoming additions</legend><label><input type="radio" name="incoming-mode" checked={mode==='selected'} onChange={()=>setMode('selected')}/> Saved selected and reviewed epochs</label><label><input type="radio" name="incoming-mode" checked={mode==='all'} onChange={()=>setMode('all')}/> Explicitly approve all eligible incoming additions, keeping draft exclusions</label></fieldset>}
        <label>Export name (optional)<input value={name} maxLength={120} disabled={locked} onChange={event=>setName(event.target.value)}/></label>
        <ExportDestination value={format} onChange={setFormat} disabled={locked}/>
        <button className="primary" disabled={busy||(!committed&&!state.prepared&&!state.preview&&!context)||state.phase==='rejected'}>{busy?'Working…':state.phase==='acceptance-unconfirmed'?'Recover acceptance & export':committed?'Export accepted additions':state.prepared?'Recover export receipt':accepting?'Accept & export':'Export'}</button>
      </form>}
      {state.exported&&<p role="status">{state.exported.name||'Export saved'} · {number(state.exported.epoch_count)} new epochs <a className="button" href={state.exported.download_url} download>Download {exportDownloadLabel(state.exported.format)}</a></p>}
    </div>
  </dialog>;
}
