import {useRetainedModal} from '../../retainedWorkspaceViews.js';
import {useAuthoredDraft} from '../../presentation/useAuthoredDraft.js';
import {useEffect,useMemo,useRef,useState} from 'react';
import {Search,X} from 'lucide-react';
import PredicateBuilder from './PredicateBuilder.jsx';
import {compilePredicate,newGroup} from './predicateState.js';
import {useProjectPreference} from '../../project-preferences/useProjectPreference.js';
import StableContent from '../../components/StableContent.jsx';
import './PredicateDialog.css';

// Building a query sends no preview, count or statistics request: the user runs
// the query (onSearch), results load, and one summary job follows them.
export default function PredicateDialog({draft:initialDraft,catalog,onSearch,onClose,protocols=[],projectId,protocolId,title='Search predicate',submitLabel='View matching epochs',readContext=null}){
  const dialog=useRef(null),request=useRef(null);
  const [draftText,setDraftText,draftState]=useAuthoredDraft(['predicate-editor',protocolId||'',readContext?.root||readContext?.cohort_key||'global'],JSON.stringify(initialDraft));
  const draft=useMemo(()=>{try{return JSON.parse(draftText);}catch{return initialDraft;}},[draftText]);
  const setDraft=value=>setDraftText(JSON.stringify(value));
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const shortcuts=useProjectPreference(projectId,'protocol_shortcuts');
  const pinnedProtocols=useMemo(()=>protocols.filter(protocol=>shortcuts.value[protocol.protocol_uuid]?.section==='pinned').sort((a,b)=>(shortcuts.value[a.protocol_uuid].rank||0)-(shortcuts.value[b.protocol_uuid].rank||0)),[protocols,shortcuts.value]);
  const compiled=useMemo(()=>{try{return {predicate:compilePredicate(draft,catalog.data?.fields||null)};}catch(error){return {error:error.message};}},[draft,catalog.data]);
  const exactDraft=useMemo(()=>{try{return compilePredicate(draft);}catch{return null;}},[draft]);
  // Fields come from the registry; no statistics are requested while editing.
  const fields=catalog.data?.fields||[];
  useRetainedModal(dialog);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function search(){
    if(busy||compiled.error||!catalog.data)return;
    request.current=new AbortController();setBusy(true);setError('');
    try{await onSearch(draft,compiled.predicate,request.current.signal);draftState.clear();}
    catch(error){if(!request.current.signal.aborted)setError(error.message);}
    finally{if(!request.current.signal.aborted)setBusy(false);}
  }
  return <dialog ref={dialog} className="predicate-dialog" aria-labelledby="predicate-dialog-title" onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2 id="predicate-dialog-title"><Search size={18}/> {title}</h2><button className="icon-button" aria-label="Close predicate editor" onClick={onClose}><X size={17}/></button></header>
    <div className="predicate-dialog-body"><StableContent data={catalog.data} loading={catalog.loading} error={catalog.error} retry={catalog.reload} scope={`${projectId||''}:${protocolId||''}`} label="Refreshing search fields">
      {catalog.data&&<PredicateBuilder pinnedProtocols={pinnedProtocols} draft={draft} fields={fields} disabled={busy||catalog.loading} onChange={setDraft}/>}
    </StableContent>
      {(compiled.error||error)&&<p role="alert" className="mx-validation">{error||compiled.error}</p>}
      <details className="mx-predicate-json"><summary>Exact predicate</summary><pre>{(compiled.predicate||exactDraft)?JSON.stringify(compiled.predicate||exactDraft,null,2):'Complete the conditions to search.'}</pre></details>
    </div>
    <footer>{readContext&&<button onClick={()=>setDraft(newGroup())}>Clear conditions</button>}<span>{readContext?'Criteria narrow this frozen protocol. Apply explicitly; Cancel keeps the current view.':'Browse matching epochs, then export or update a pinned protocol.'}</span><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy||catalog.loading||!catalog.data||!!compiled.error} onClick={search}>{busy?'Searching…':submitLabel}</button></footer>
  </dialog>;
}
