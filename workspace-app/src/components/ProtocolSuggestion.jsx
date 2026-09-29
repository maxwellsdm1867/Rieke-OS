import {useEffect,useState} from 'react';
import {ArrowRight,Check,ChevronDown,LoaderCircle,Plus,Sparkles,Pin,Database,Users,Activity,Clock3,CalendarDays,FileCheck2} from 'lucide-react';
import {api,humanize,time,number,duration} from '../api.js';
import ProtocolDiff,{CompactProtocolDiff} from './ProtocolDiff.jsx';
import {sameSuggestionComparison} from '../protocolSuggestions.js';
import './ProtocolSuggestion.css';
import {importReadiness,suggestionDates} from '../importReadiness.js';

export default function ProtocolSuggestion({suggestion,onChange,onReview,onProtocol,importView=false}){
  const [comparison,setComparison]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[applied,setApplied]=useState(false);
  if(!suggestion)return null;
  const shown=comparison || suggestion;
  const alreadyApplied=applied||suggestion.status==='applied';
  async function add(){
    if(busy||alreadyApplied||suggestion.status!=='pending')return;
    setBusy(true);setError('');setMessage('');
    try{
      const fresh=await api(`/explore/revisions/${suggestion.candidate_revision_uuid}/compare-to-protocol`,{method:'POST',body:{protocol_uuid:suggestion.protocol_uuid}});
      if(!Number.isInteger(fresh.expected_binding_version)||typeof fresh.expected_query_revision!=='string')throw new Error('The comparison did not include a valid dataset version. Refresh this protocol before retrying.');
      if(!sameSuggestionComparison(shown,fresh)){setComparison(fresh);setMessage('The dataset or inspection state changed. Review this refreshed comparison, then add the saved candidate.');return;}
      const receipt=await api(`/explore/revisions/${suggestion.candidate_revision_uuid}/apply-to-protocol`,{method:'POST',body:{protocol_uuid:suggestion.protocol_uuid,expected_binding_version:fresh.expected_binding_version,expected_query_revision:fresh.expected_query_revision}});
      if(receipt.binding?.revision_uuid!==suggestion.candidate_revision_uuid||!Number.isInteger(receipt.binding?.version)){onChange?.();throw new Error('The update did not return a complete receipt. Check Activity & logs before retrying.');}
      setApplied(true);setMessage('Matched data added to this protocol. Inspection and exports now use the updated dataset.');onChange?.();
    }catch(error){setError(error.message);}finally{setBusy(false);}
  }
  const removing=(shown.diff_counts?.removed || 0)>0;
  return <section className={`protocol-new-data ${importView?'import-ready-protocol':''} ${alreadyApplied?'is-added':''}`} aria-label={importView?humanize(suggestion.protocol_name):"New data matching saved protocol query"}>
    <div className="protocol-new-data-heading"><Sparkles size={19}/><div><h2>{importView?humanize(suggestion.protocol_name):suggestion.status==='stale'?'Saved proposal needs a refresh':'New data matches your saved query'}</h2><p>{suggestion.source_filename || 'Imported recording'} · {time(suggestion.created_at)}</p></div>{importView&&<span className={`import-ready-state ${alreadyApplied?'added':''}`}>{alreadyApplied?<Check size={13}/>:suggestion.status==='stale'?<Clock3 size={13}/>:<Sparkles size={13}/>} {alreadyApplied?'Added':suggestion.status==='stale'?'Refresh needed':'Ready to add'}</span>}</div>
    {importView?<ReadinessVisual suggestion={shown}/>:<CompactProtocolDiff comparison={shown}/>}{suggestion.status==='stale'&&<p className="protocol-new-data-note" role="status">Source membership changed after this proposal was saved. Open the protocol and use Refresh & compare to regenerate it before adding data.</p>}
    <div className="protocol-suggestion-actions"><button className="primary" disabled={busy||alreadyApplied||suggestion.status==='stale'} onClick={add}>{busy?<LoaderCircle size={15} className="spin"/>:alreadyApplied?<Check size={15}/>:<Plus size={15}/>} {busy?'Checking & adding…':alreadyApplied?'Added':removing?'Apply dataset update':'Add matched data'}</button>{onReview&&!alreadyApplied&&<button disabled={busy} onClick={()=>onReview(suggestion.candidate_revision_uuid,suggestion.protocol_uuid)}>Inspect before adding <ArrowRight size={14}/></button>}{importView&&onProtocol&&<button className="quiet" onClick={()=>onProtocol(suggestion.protocol_uuid)}>Open protocol <ArrowRight size={13}/></button>}<span>{removing?'This proposal includes removals.':'Existing inspection decisions are preserved.'}</span></div>
    <details className="protocol-suggestion-details" open={!!comparison}><summary><ChevronDown size={13}/> See affected cells & epochs</summary><ProtocolDiff comparison={shown}/></details>
    {message&&<p className="protocol-new-data-note" role="status">{message}</p>}
    {error&&<div className="error" role="alert">{error}<p>Open the protocol and use Refresh & compare if the source or saved query changed. Check Activity & logs before retrying an interrupted request.</p></div>}
  </section>;
}
function ReadinessVisual({suggestion}){
  const summary=suggestion.diff_summary||{},current=summary.current||{},proposed=summary.proposed||{},delta=summary.delta||{},diff=suggestion.diff_counts||{};
  const dates=suggestionDates(suggestion),added=diff.added||0,removed=diff.removed||0,retained=Math.max(0,(current.epochs||0)-removed),scale=Math.max(1,retained+added);
  return <div className="import-ready-visual"><div className="import-ready-metrics"><div><span><Users size={14}/> Cells</span><strong>{number(current.cells)} <ArrowRight size={15}/> {number(proposed.cells)}</strong><small>{delta.cells>0?`+${number(delta.cells)} net new`:delta.cells<0?`${number(delta.cells)} net change`:'Same cells'}</small></div><div><span><Activity size={14}/> Epochs</span><strong className="import-new-count">+{number(added)}</strong><small>{number(current.epochs)} → {number(proposed.epochs)} in dataset</small></div><div><span><Clock3 size={14}/> Net recorded time</span><strong>{delta.duration_seconds==null?'—':`${delta.duration_seconds>=0?'+':'−'}${duration(Math.abs(delta.duration_seconds))}`}</strong><small>{proposed.duration_seconds==null?'Duration not recorded':`${duration(proposed.duration_seconds)} total`}</small></div></div><div className="import-membership-bar" role="img" aria-label={`${retained} retained epochs and ${added} added epochs; ${removed} removed`}><i style={{width:`${retained/scale*100}%`}}/><i className="new" style={{width:`${added/scale*100}%`}}/></div><div className="import-membership-caption"><span><i/>{number(retained)} retained</span><span><i className="new"/>+{number(added)} added</span>{removed>0&&<strong className="import-removal">−{number(removed)} removed</strong>}{diff.changed>0&&<strong>{number(diff.changed)} metadata changed</strong>}{dates.length>0&&<span className="import-ready-dates"><CalendarDays size={12}/>{dates.join(' · ')}{Object.values(summary.cell_changes?.truncated||{}).some(Boolean)?' · dates shown':''}</span>}</div></div>;
}
function readPins(projectId){try{return JSON.parse(localStorage.getItem(`rieke-os.sidebar.protocols.v1.${projectId}`))||{};}catch{return {};}}
export function ImportSuggestions({suggestions=[],protocols=[],projectId,sources=[],jobs=[],onReview,onProtocol,onChange}){
  const [preferences,setPreferences]=useState(()=>readPins(projectId));
  useEffect(()=>{const update=()=>setPreferences(readPins(projectId));update();window.addEventListener('storage',update);window.addEventListener('rieke-protocol-shortcuts-changed',update);return()=>{window.removeEventListener('storage',update);window.removeEventListener('rieke-protocol-shortcuts-changed',update);};},[projectId]);
  const model=importReadiness({suggestions,protocols,preferences});
  const latest=[...jobs].filter(job=>job&&(['complete','completed','success'].includes(job.status)||(job.status==='complete_with_warnings'&&job.catalog_committed===true))).sort((a,b)=>String(b.finished_at).localeCompare(String(a.finished_at)))[0];
  const source=sources.find(item=>item.source_sha256===latest?.source_sha256);
  if(!suggestions.length&&!latest)return null;
  const render=item=><ProtocolSuggestion key={item.suggestion_uuid||item.protocol_uuid} suggestion={item} onChange={onChange} onReview={onReview} onProtocol={onProtocol} importView/>;
  return <section className="import-readiness" aria-label="Import readiness summary"><header className="import-readiness-heading"><div><div className="eyebrow">IMPORT WORKBENCH</div><h2><FileCheck2 size={23}/> {model.ready>0?'Ready to add to your protocols.':'Protocol matching summary.'}</h2><p>Saved queries have prepared the protocol updates below.</p></div><span className="import-ready-total">{model.ready} ready{model.added>0?` · ${model.added} added`:''}{model.stale>0?` · ${model.stale} need refresh`:''}</span></header>{source&&<div className="import-source-summary"><Database size={21}/><div><strong>{source.filename}</strong><small>Latest completed import · {time(latest.finished_at)}</small></div><span><strong>{number(source.counts?.cells)}</strong> source cells</span><span><strong>{number(source.counts?.epochs)}</strong> source epochs</span><span className="import-checked"><Check size={14}/> Imported</span></div>}{latest?.warnings?.length>0&&<p className="error">Some post-import checks need attention. See import diagnostics below.</p>}
  {model.pinned.length>0&&<div className="import-priority-group"><h3><Pin size={14}/> Pinned protocols</h3>{model.pinned.map(({protocol,suggestion})=>suggestion?render(suggestion):<div className="import-no-match" key={protocol.protocol_uuid}><div><strong>{humanize(protocol.name)}</strong><small>No pending proposal. Open the protocol to check its saved query.</small></div><button onClick={()=>onProtocol(protocol.protocol_uuid)}>Open protocol <ArrowRight size={13}/></button></div>)}</div>}
  {model.other.length>0&&<details className="import-other-protocols" open={!model.pinned.some(row=>row.suggestion?.status==='pending')}><summary>{model.pinned.length?'Other saved protocols':'Saved protocol matches'} <span>{model.other.length}</span></summary>{model.other.map(render)}</details>}
  <p className="import-readiness-footnote">Add updates the protocol dataset and records its query and diff. Exports are available from each protocol. Cells may appear in more than one protocol.</p></section>;
}
