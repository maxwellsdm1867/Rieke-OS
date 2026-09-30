import {useEffect,useRef,useState} from 'react';
import {Database,Download,FileCode,LoaderCircle} from 'lucide-react';
import {api,number} from '../api.js';
import './CandidateExportPanel.css';

// A saved candidate is an immutable search result, not a pinned protocol.
export default function CandidateExportPanel({candidate,onExported,disabled=false,onChange,defaultName='',defaultFormat='wheeler-sqlite',onBusyChange}) {
  const [name,setName]=useState(defaultName),[format,setFormat]=useState(['wheeler-sqlite','epictree-mat','reference-json'].includes(defaultFormat)?defaultFormat:'wheeler-sqlite');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[completed,setCompleted]=useState(null);
  useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
  const inFlight=useRef(false),currentRevision=useRef(null);
  const revision=candidate?.revision_uuid,recipe=candidate?.recipe;
  currentRevision.current=revision;
  const expected=recipe?.full_recipe_sha256||recipe?.content_sha256;
  const count=recipe?.epoch_count??candidate?.summary?.matched_count??recipe?.epochs?.length??0;
  useEffect(()=>{setError('');setCompleted(null);setName(defaultName);setFormat(['wheeler-sqlite','epictree-mat','reference-json'].includes(defaultFormat)?defaultFormat:'wheeler-sqlite');},[revision,defaultName,defaultFormat]);
  function changeName(value){setName(value);onChange?.({name:value,format});}
  function changeFormat(value){setFormat(value);onChange?.({name,format:value});}
  async function exportResult(event){
    event.preventDefault();
    if(inFlight.current||disabled||!revision||!expected||!count)return;
    inFlight.current=true;setBusy(true);setError('');setCompleted(null);
    const submittedRevision=revision;
    try {
      const result=await api(`/explore/revisions/${revision}/exports`,{method:'POST',body:{format,expected_recipe_sha256:expected,...(name.trim()?{name:name.trim()}:{})}});
      if(currentRevision.current===submittedRevision)setCompleted(result);
      onExported?.(result);
    } catch(failure) {
      if(currentRevision.current===submittedRevision)setError(failure.message);
    } finally {inFlight.current=false;setBusy(false);}
  }
  return <section className="candidate-export" aria-label="Export saved search result">
    <header><strong>Export this result</strong><span>{number(count)} epochs · one-off export</span></header>
    <p>Export this selection’s included epochs and saved tree. Existing protocol masks and tags are not merged. Any explicitly queried tags stay in the query evidence.</p>
    <form onSubmit={exportResult}>
      <label className="candidate-export-name">Name <span>(optional)</span><input value={name} onChange={event=>changeName(event.target.value)} maxLength={120} placeholder={recipe?.name?`${recipe.name} · automatic date`:'Automatic name and date'} disabled={busy||disabled}/></label>
      <fieldset disabled={busy||disabled}><legend>Handoff format</legend>
        <label><input type="radio" name={`candidate-format-${revision||'draft'}`} value="wheeler-sqlite" checked={format==='wheeler-sqlite'} onChange={()=>changeFormat('wheeler-sqlite')}/><Database size={15}/><span>SQLite database<small>Query in Wheeler or another SQL tool</small></span></label>
        <label><input type="radio" name={`candidate-format-${revision||'draft'}`} value="epictree-mat" checked={format==='epictree-mat'} onChange={()=>changeFormat('epictree-mat')}/><FileCode size={15}/><span>EpicTree / MATLAB<small>Tree, lazy traces and selection mask</small></span></label>
        {format==='reference-json'&&<label><input type="radio" checked readOnly/><FileCode size={15}/><span>Reference JSON<small>Preserved from this saved export</small></span></label>}
      </fieldset>
      <div className="candidate-export-actions"><button className="primary" type="submit" disabled={busy||disabled||!revision||!expected||!count}>{busy?<LoaderCircle size={15} className="candidate-export-spinner"/>:<Download size={15}/>} {busy?'Preparing export…':'Export result'}</button><small>Original H5 files remain linked. No protocol or pin is created.</small></div>
    </form>
    {!revision&&<p className="candidate-export-note">Save the current result before exporting.</p>}
    {error&&<p role="alert" className="candidate-export-error">{error}</p>}
    {completed&&<div role="status" className="candidate-export-complete"><span>{completed.name} · {number(completed.epoch_count)} epochs exported</span><a href={completed.download_url} download><Download size={14}/> Download {completed.format==='epictree-mat'?'MATLAB bundle':completed.format==='reference-json'?'reference package':'SQLite database'}</a></div>}
  </section>;
}
