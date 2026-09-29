import {useEffect,useRef,useState} from 'react';
import {Download,Pin,X} from 'lucide-react';
import CandidateExportPanel from './CandidateExportPanel.jsx';
import ProtocolApplyPanel from './ProtocolApplyPanel.jsx';
import NewPinnedProtocol from './NewPinnedProtocol.jsx';
import {exportProtocolGroups,pinProtocolPreference} from '../exportProtocolTargets.js';
import './ExportSelectionDialog.css';

export default function ExportSelectionDialog({candidate,protocols,projectId,initialProtocolId,defaultName,defaultFormat,disabled,onClose,onApplied,onChanged}){
  const dialog=useRef(null),[mode,setMode]=useState(null),[busy,setBusy]=useState(false),[pinError,setPinError]=useState(''),[appliedId,setAppliedId]=useState(null);
  const key=`rieke-os.sidebar.protocols.v1.${projectId}`;
  function preferences(){try{const value=JSON.parse(localStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}}
  const groups=exportProtocolGroups(protocols,preferences(),initialProtocolId);
  useEffect(()=>{const el=dialog.current;el.showModal();return()=>el.close();},[]);
  function finishPin(id){
    try{
      if(!projectId)throw new Error('Project identity unavailable');
      localStorage.setItem(key,JSON.stringify(pinProtocolPreference(preferences(),id)));
      window.dispatchEvent(new Event('rieke-protocol-shortcuts-changed'));
      onApplied?.(id);
    }catch(error){setAppliedId(id);setPinError('Dataset updated, but the sidebar shortcut could not be saved. Retry pinning without applying the dataset again.');onChanged?.();}
  }
  return <dialog ref={dialog} className="export-selection-dialog" aria-labelledby="export-selection-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
    <header><h2 id="export-selection-title"><Download size={17}/> Export selection</h2><button className="icon-button" disabled={busy} aria-label="Close export options" onClick={onClose}><X size={17}/></button></header>
    <nav aria-label="Export destination"><button disabled={busy} aria-pressed={mode==='direct'} className={mode==='direct'?'active':''} onClick={()=>setMode('direct')}><Download size={18}/><span><strong>Export directly</strong><small>SQLite or EpicTree / MATLAB</small></span></button><button disabled={busy} aria-pressed={mode==='protocol'} className={mode==='protocol'?'active':''} onClick={()=>setMode('protocol')}><Pin size={18}/><span><strong>Update pinned protocol</strong><small>Match Protocol ID, then review changes</small></span></button><button disabled={busy} aria-pressed={mode==='new'} className={mode==='new'?'active':''} onClick={()=>setMode('new')}><Pin size={18}/><span><strong>Create pinned protocol</strong><small>Keep this selection as a new dataset</small></span></button></nav>
    <div className="export-selection-body">
      {!mode&&<p className="export-choice-hint">Choose a destination for these matching epochs.</p>}
      {mode==='direct'&&<CandidateExportPanel candidate={candidate} defaultName={defaultName} defaultFormat={defaultFormat} disabled={disabled} onBusyChange={setBusy} onExported={onChanged}/>}
      {mode==='new'&&<NewPinnedProtocol candidate={candidate} defaultName={defaultName} disabled={disabled||!!appliedId} onBusyChange={setBusy} onCreated={finishPin}/>}
      {mode==='protocol'&&<><ProtocolApplyPanel candidate={candidate} protocols={groups.flatMap(group=>group.protocols)} targetGroups={groups} initialProtocolId={initialProtocolId} disabled={disabled||!!appliedId} onBusyChange={setBusy} onApplied={finishPin} pinnedExport/>
        <p className="export-linked-context">Cell typing and backtracking recordings stay linked by cell UUID. The protocol overview refreshes after applying.</p>
      </>}
      {pinError&&<div role="alert"><p>{pinError}</p><button onClick={()=>finishPin(appliedId)}>Retry sidebar pin</button></div>}
    </div>
  </dialog>;
}
