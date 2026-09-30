import {useEffect,useMemo,useRef,useState} from 'react';
import {Search,Users,Activity,Clock3,X} from 'lucide-react';
import PredicateBuilder from './PredicateBuilder.jsx';
import {compilePredicate} from './predicateState.js';
import {useProjectPreference} from '../useProjectPreference.js';
import {api,number,time} from '../api.js';
import {presetKey} from '../searchPresets.js';
import {Status} from './Common.jsx';
import './PredicateDialog.css';

export default function PredicateDialog({draft:initialDraft,catalog,onSearch,onClose,protocols=[],projectId,previousRun=null,previousPredicate=null,title='Search predicate',submitLabel='View matching epochs'}){
  const dialog=useRef(null),request=useRef(null);
  const [preview,setPreview]=useState(previousRun?{run:previousRun,predicate:previousPredicate}:null);
  const [previewBusy,setPreviewBusy]=useState(false);
  const [draft,setDraft]=useState(initialDraft),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const shortcuts=useProjectPreference(projectId,'protocol_shortcuts');
  const pinnedProtocols=useMemo(()=>protocols.filter(protocol=>shortcuts.value[protocol.protocol_uuid]?.section==='pinned').sort((a,b)=>(shortcuts.value[a.protocol_uuid].rank||0)-(shortcuts.value[b.protocol_uuid].rank||0)),[protocols,shortcuts.value]);
  const compiled=useMemo(()=>{try{return {predicate:compilePredicate(draft,catalog.data?.fields||null)};}catch(error){return {error:error.message};}},[draft,catalog.data]);
  useEffect(()=>{const el=dialog.current;el.showModal();return()=>{request.current?.abort();el.close();};},[]);
  async function previewMatches(){
    if(busy||previewBusy||compiled.error||!catalog.data)return;
    const controller=new AbortController();request.current=controller;setPreviewBusy(true);setError('');
    try{const result=await api('/explore/run',{method:'POST',body:{predicate:compiled.predicate,splits:''},signal:controller.signal});if(!controller.signal.aborted)setPreview({run:result.last_run,predicate:compiled.predicate});}
    catch(error){if(!controller.signal.aborted)setError(error.message);}
    finally{if(!controller.signal.aborted)setPreviewBusy(false);}
  }
  const previewMatchesDraft=!!preview&&!!compiled.predicate&&presetKey(preview.predicate)===presetKey(compiled.predicate);
  async function search(){
    if(busy||compiled.error||!catalog.data)return;
    request.current=new AbortController();setBusy(true);setError('');
    try{await onSearch(draft,compiled.predicate,request.current.signal);}
    catch(error){if(!request.current.signal.aborted)setError(error.message);}
    finally{if(!request.current.signal.aborted)setBusy(false);}
  }
  return <dialog ref={dialog} className="predicate-dialog" aria-labelledby="predicate-dialog-title" onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2 id="predicate-dialog-title"><Search size={18}/> {title}</h2><button className="icon-button" aria-label="Close predicate editor" onClick={onClose}><X size={17}/></button></header>
    <div className="predicate-dialog-body"><Status {...catalog} retry={catalog.reload}>{catalog.data&&<PredicateBuilder pinnedProtocols={pinnedProtocols} draft={draft} fields={catalog.data.fields} disabled={busy||previewBusy} onChange={setDraft}/>}</Status>
      {(compiled.error||error)&&<p role="alert" className="mx-validation">{error||compiled.error}</p>}
      <div className="predicate-preview" aria-label="Predicate preview"><div>{preview?<><strong>{previewMatchesDraft?'Last matching result':'Previous search result'}</strong><span><Users size={14}/><b>{number(preview.run.cell_count)}</b> cells <Activity size={14}/><b>{number(preview.run.epoch_count)}</b> epochs</span><small><Clock3 size={12}/> Last run {time(preview.run.ran_at)}{!previewMatchesDraft?' · Conditions have changed':''}</small></>:<span>Preview the matching cells and epochs.</span>}</div><button disabled={busy||previewBusy||catalog.loading||!catalog.data||!!compiled.error} onClick={previewMatches}><Search size={14}/>{previewBusy?'Checking…':'Preview matches'}</button></div>
      <details className="mx-predicate-json"><summary>Exact predicate</summary><pre>{compiled.predicate?JSON.stringify(compiled.predicate,null,2):'Complete the conditions to search.'}</pre></details>
    </div>
    <footer><span>Browse matching epochs, then export or update a pinned protocol.</span><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy||previewBusy||catalog.loading||!catalog.data||!!compiled.error} onClick={search}>{busy?'Searching…':submitLabel}</button></footer>
  </dialog>;
}
