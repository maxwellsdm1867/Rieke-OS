import {useEffect,useRef,useState} from 'react';
import {api,number} from '../api.js';
import {acceptIncoming,acceptedBinding,exportIncoming} from '../incomingReview.js';
import {ExportDestination} from './ProtocolExports.jsx';
import {exportDownloadLabel} from '../exportFormats.js';
import ProtocolDiff from './ProtocolDiff.jsx';
import './ExportSelectionDialog.css';

export default function IncomingExportDialog({item,accept=false,state={},onState,onClose,onChanged}){
  const dialog=useRef(null),inFlight=useRef(false);
  const [candidate,setCandidate]=useState(null),[loadError,setLoadError]=useState(''),[busy,setBusy]=useState(false);
  const [format,setFormat]=useState('wheeler-sqlite'),[name,setName]=useState(''),[confirmRemoval,setConfirmRemoval]=useState(false);
  const shown=state.comparison||item;
  useEffect(()=>{const el=dialog.current;el.showModal();return()=>el.close();},[]);
  useEffect(()=>{
    const controller=new AbortController();
    api(`/explore/revisions/${item.candidate_revision_uuid}?summary=1`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setCandidate(value);}).catch(error=>{if(!controller.signal.aborted)setLoadError(error.message);});
    return()=>controller.abort();
  },[item.candidate_revision_uuid]);
  async function submit(event){
    event.preventDefault();if(inFlight.current||!candidate)return;
    inFlight.current=true;setBusy(true);
    let receipt=state.receipt;
    try{
      if(accept&&!receipt){
        const result=await acceptIncoming(item,shown,api);
        if(!result.receipt){onState({...state,comparison:result.comparison,error:'The comparison changed. Review the refreshed changes before accepting.',phase:'compare'});setConfirmRemoval(false);return;}
        receipt=result.receipt;
        onState({receipt,phase:'accepted'});onChanged?.();
      }
      onState({receipt,phase:'exporting'});
      const exported=await exportIncoming(candidate,{format,name},api);
      onState({receipt,exported,phase:'exported'});onChanged?.();
    }catch(error){onState({receipt,comparison:state.comparison,phase:error.acceptanceUnconfirmed?'unconfirmed':receipt?'export-failed':'failed',error:error.message});}
    finally{inFlight.current=false;setBusy(false);}
  }
  async function reconcile(){
    if(inFlight.current)return;inFlight.current=true;setBusy(true);
    try{
      const comparison=await api(`/explore/revisions/${item.candidate_revision_uuid}/compare-to-protocol`,{method:'POST',body:{protocol_uuid:item.protocol_uuid}});
      const binding=acceptedBinding(comparison,item);
      onState(binding?{receipt:{binding},phase:'accepted',error:'Acceptance confirmed. You can export without applying again.'}:{comparison,phase:'compare',error:'The candidate is not currently bound. Review this comparison before a new acceptance attempt.'});
      onChanged?.();
    }catch(error){onState({...state,error:error.message});}finally{inFlight.current=false;setBusy(false);}
  }
  const removes=shown.diff_counts?.removed>0;
  return <dialog ref={dialog} className="export-selection-dialog" aria-label={accept?'Accept and export incoming dataset':'Export incoming dataset'} onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
    <header><h2>{accept?'Accept & export':'Export incoming result'}</h2><button disabled={busy} onClick={onClose} aria-label="Close incoming export">Close</button></header>
    <div className="export-selection-body">
      <p>{accept?'Acceptance replaces the pinned protocol with this exact saved cohort. Export follows as a separate step.':'Export this immutable candidate without changing a protocol.'} This one-off artifact contains the candidate’s included epochs and saved tree; protocol masks and curation tags are not merged.</p>
      <p>Candidate <code>{item.candidate_revision_uuid}</code> · {number(candidate?.recipe?.epoch_count??item.next_count)} epochs</p>
      {accept&&!state.receipt&&<><ProtocolDiff comparison={shown}/>{removes&&<label><input type="checkbox" checked={confirmRemoval} disabled={busy} onChange={event=>setConfirmRemoval(event.target.checked)}/> Replace the pinned cohort, including removal of {number(shown.diff_counts.removed)} epochs.</label>}</>}
      {state.receipt&&<p role="status">Accepted revision {state.receipt.binding.revision_uuid} · binding version {state.receipt.binding.version}. Export retries do not apply it again.</p>}
      {loadError&&<p role="alert">{loadError} Close and reopen to reload the candidate.</p>}
      {state.error&&<p role="alert">{state.phase==='export-failed'?'Dataset acceptance succeeded; export failed. ':''}{state.error}{state.phase==='export-failed'&&' Check export history for an interrupted artifact before retrying.'}</p>}
      {state.phase==='unconfirmed'?<div><p>Acceptance may have committed. Reconcile the current binding before any further write.</p><button disabled={busy} onClick={reconcile}>Check acceptance status</button></div>:!state.exported&&<form onSubmit={submit}>
        <label>Export name (optional)<input value={name} maxLength={120} disabled={busy} onChange={event=>setName(event.target.value)}/></label>
        <ExportDestination value={format} onChange={setFormat} disabled={busy}/>
        <button className="primary" disabled={busy||!candidate||(accept&&!state.receipt&&removes&&!confirmRemoval)}>{busy?'Working…':state.receipt?'Retry export only':accept?'Accept & export':'Export'}</button>
      </form>}
      {state.exported&&<p role="status">{state.exported.name} · {number(state.exported.epoch_count)} epochs <a className="button" href={state.exported.download_url} download>Download {exportDownloadLabel(state.exported.format)}</a></p>}
    </div>
  </dialog>;
}
