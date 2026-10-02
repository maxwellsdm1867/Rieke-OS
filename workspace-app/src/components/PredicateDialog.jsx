import {useEffect,useMemo,useRef,useState} from 'react';
import {Search,Users,Activity,Clock3,X} from 'lucide-react';
import PredicateBuilder from './PredicateBuilder.jsx';
import {compilePredicate,newGroup} from './predicateState.js';
import {useRequestedSummaries} from '../useRequestedSummaries.js';
import {fieldsWithSummaries,requestedSummaryFields} from '../requestedSummaries.js';
import SummaryStatus from './SummaryStatus.jsx';
import SummaryPreferences from './SummaryPreferences.jsx';
import {useProtocolSummaryPreferences} from '../useProtocolSummaryPreferences.js';
import {useProjectPreference} from '../useProjectPreference.js';
import {api,number,time} from '../api.js';
import {candidatePreviewReceipt} from '../frozenReadContext.js';
import {predicateIdentity} from '../predicateIdentity.js';
import {presetKey} from '../searchPresets.js';
import {Status} from './Common.jsx';
import './PredicateDialog.css';

export default function PredicateDialog({draft:initialDraft,catalog,onSearch,onClose,protocols=[],projectId,protocolId,previousRun=null,previousPredicate=null,title='Search predicate',submitLabel='View matching epochs',readContext=null}){
  const dialog=useRef(null),request=useRef(null),serial=useRef(0);
  const [preview,setPreview]=useState(previousRun?{run:previousRun,predicate:previousPredicate}:null);
  const [previewBusy,setPreviewBusy]=useState(false);
  const [draft,setDraft]=useState(initialDraft),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const shortcuts=useProjectPreference(projectId,'protocol_shortcuts');
  const pinnedProtocols=useMemo(()=>protocols.filter(protocol=>shortcuts.value[protocol.protocol_uuid]?.section==='pinned').sort((a,b)=>(shortcuts.value[a.protocol_uuid].rank||0)-(shortcuts.value[b.protocol_uuid].rank||0)),[protocols,shortcuts.value]);
  const compiled=useMemo(()=>{try{return {predicate:compilePredicate(draft,catalog.data?.fields||null)};}catch(error){return {error:error.message};}},[draft,catalog.data]);
  const exactDraft=useMemo(()=>{try{return compilePredicate(draft);}catch{return null;}},[draft]);
  const previewContext=predicateIdentity({readContext,generation:catalog.data?.generation||null});
  const liveContext=useRef(previewContext);liveContext.current=previewContext;
  const astKey=compiled.predicate?predicateIdentity(compiled.predicate):'';
  useEffect(()=>{if(!readContext)return;serial.current++;request.current?.abort();setPreviewBusy(false);setPreview(null);setPreviewPredicate(null);},[previewContext,astKey]);
  const preferences=useProtocolSummaryPreferences(projectId,protocolId,'filter');
  const requested=requestedSummaryFields({registry:catalog.data?.fields||[],predicate:draft,preferences:preferences.value});
  const [previewPredicate,setPreviewPredicate]=useState(null);
  const countPreview=useRequestedSummaries({...readContext,predicate:previewPredicate,summary_fields:[],generation:catalog.data?.generation},{enabled:!!readContext&&!readContext.root&&!!previewPredicate&&!!catalog.data?.generation});
  const summaries=useRequestedSummaries({...readContext,predicate:compiled.predicate,summary_fields:requested.fields,generation:catalog.data?.generation},
    {enabled:!!catalog.supportsSummaries&&!!catalog.data?.generation&&!!compiled.predicate&&requested.fields.length>0});
  const fields=fieldsWithSummaries(catalog.data?.fields||[],summaries);
  useEffect(()=>{const el=dialog.current;el.showModal();return()=>{request.current?.abort();el.close();};},[]);
  async function previewMatches(){
    if(busy||previewBusy||compiled.error||!catalog.data)return;
    if(readContext&&!readContext.root){setPreviewPredicate(compiled.predicate);return;}
    if(readContext?.root){
      const controller=new AbortController(),sequence=++serial.current,contextAtSubmit=previewContext;request.current?.abort();request.current=controller;setPreviewBusy(true);setError('');
      const body={candidate_scope_revision:readContext.candidate_scope_revision,filters:{...readContext.filters,metadata_predicate:JSON.stringify(compiled.predicate)}};
      const current=()=>!controller.signal.aborted&&serial.current===sequence&&liveContext.current===contextAtSubmit;
      try{const result=await api(`${readContext.root}/summary`,{method:'POST',signal:controller.signal,body});
        const count=candidatePreviewReceipt(result,body);
        if(current()){setPreview({run:{epoch_count:count},predicate:compiled.predicate,context:contextAtSubmit});setPreviewPredicate(compiled.predicate);}
      }catch(error){if(current())setError(error.message);}finally{if(current())setPreviewBusy(false);}return;
    }
    if(busy||previewBusy||compiled.error||!catalog.data)return;
    const controller=new AbortController();request.current=controller;setPreviewBusy(true);setError('');
    try{const result=await api('/explore/run',{method:'POST',body:{predicate:compiled.predicate,splits:'',catalog_summary:false},signal:controller.signal});if(!controller.signal.aborted)setPreview({run:result.last_run,predicate:compiled.predicate});}
    catch(error){if(!controller.signal.aborted)setError(error.message);}
    finally{if(!controller.signal.aborted)setPreviewBusy(false);}
  }
  const countMatchesDraft=!!previewPredicate&&!!compiled.predicate&&presetKey(previewPredicate)===presetKey(compiled.predicate);
  const previewMatchesDraft=!!preview&&(!readContext||preview.context===previewContext)&&!!compiled.predicate&&presetKey(preview.predicate)===presetKey(compiled.predicate);
  async function search(){
    if(busy||compiled.error||!catalog.data)return;
    request.current=new AbortController();setBusy(true);setError('');
    try{await onSearch(draft,compiled.predicate,request.current.signal);}
    catch(error){if(!request.current.signal.aborted)setError(error.message);}
    finally{if(!request.current.signal.aborted)setBusy(false);}
  }
  return <dialog ref={dialog} className="predicate-dialog" aria-labelledby="predicate-dialog-title" onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2 id="predicate-dialog-title"><Search size={18}/> {title}</h2><button className="icon-button" aria-label="Close predicate editor" onClick={onClose}><X size={17}/></button></header>
    <div className="predicate-dialog-body"><Status {...catalog} retry={catalog.reload}>{catalog.data&&<PredicateBuilder pinnedProtocols={pinnedProtocols} draft={draft} fields={fields} disabled={busy||previewBusy} onChange={setDraft}/>}</Status>
      {catalog.supportsSummaries&&<SummaryStatus state={{...summaries,retry:()=>{catalog.reload();summaries.retry();}}}/>}
      <SummaryPreferences fields={catalog.data?.fields||[]} preferences={preferences}/>
      {(compiled.error||error)&&<p role="alert" className="mx-validation">{error||compiled.error}</p>}
      <div className="predicate-preview" aria-label="Predicate preview"><div>{readContext?<><strong>Frozen protocol subset</strong><span>{readContext.root&&previewMatchesDraft?`${number(preview.run.epoch_count)} matching epochs`:countPreview.status==='ready'&&countMatchesDraft?`${number(countPreview.result.matched_count)} matching epochs`:countPreview.status==='pending'?'Checking…':'Preview counts unavailable'}</span>{countPreview.error&&<small role="alert">{countPreview.error}</small>}{countPreview.status==='pending'&&<button onClick={countPreview.cancel}>Cancel preview</button>}</>:preview?<><strong>{previewMatchesDraft?'Last matching result':'Previous search result'}</strong><span><Users size={14}/><b>{number(preview.run.cell_count)}</b> cells <Activity size={14}/><b>{number(preview.run.epoch_count)}</b> epochs</span><small><Clock3 size={12}/> Last run {time(preview.run.ran_at)}{!previewMatchesDraft?' · Conditions have changed':''}</small></>:<span>Preview the matching cells and epochs.</span>}</div><button disabled={busy||previewBusy||catalog.loading||!catalog.data||!!compiled.error} onClick={previewMatches}><Search size={14}/>{previewBusy?'Checking…':'Preview matches'}</button></div>
      <details className="mx-predicate-json"><summary>Exact predicate</summary><pre>{(compiled.predicate||exactDraft)?JSON.stringify(compiled.predicate||exactDraft,null,2):'Complete the conditions to search.'}</pre></details>
    </div>
    <footer>{readContext&&<button onClick={()=>setDraft(newGroup())}>Clear conditions</button>}<span>{readContext?'Criteria narrow this frozen protocol. Apply explicitly; Cancel keeps the current view.':'Browse matching epochs, then export or update a pinned protocol.'}</span><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy||previewBusy||catalog.loading||!catalog.data||!!compiled.error} onClick={search}>{busy?'Searching…':submitLabel}</button></footer>
  </dialog>;
}
