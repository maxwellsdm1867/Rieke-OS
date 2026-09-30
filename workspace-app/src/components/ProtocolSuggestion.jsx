import NeuronIcon from './NeuronIcon.jsx';
import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Check,ChevronDown,LoaderCircle,Plus,Sparkles,Pin,Database,Users,Activity,Clock3,CalendarDays,FileCheck2,X,Layers3,RefreshCw,MinusCircle,CheckCircle2} from 'lucide-react';
import {api,humanize,time,number,duration} from '../api.js';
import ProtocolDiff,{CompactProtocolDiff} from './ProtocolDiff.jsx';
import {approveProtocolSuggestion} from '../protocolSuggestions.js';
import './ProtocolSuggestion.css';
import {datedCellLabel} from '../recordingIdentity.js';
import {importReadiness,suggestionDates} from '../importReadiness.js';
import {useProjectPreference} from '../useProjectPreference.js';

export default function ProtocolSuggestion({suggestion,onChange,onReview,onProtocol,importView=false,disabled=false,approvalSignal=0,onBusyChange,onApproved}){
  const [comparison,setComparison]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[applied,setApplied]=useState(false);
  const lastSignal=useRef(approvalSignal);
  useEffect(()=>{if(approvalSignal!==lastSignal.current){lastSignal.current=approvalSignal;if(approvalSignal>0)void add();}},[approvalSignal]);
  if(!suggestion)return null;
  const shown=comparison || suggestion;
  const alreadyApplied=applied||suggestion.status==='applied';
  async function add(){
    if(busy||alreadyApplied||suggestion.status!=='pending')return;
    setBusy(true);onBusyChange?.(true);setError('');setMessage('');
    try{
      const result=await approveProtocolSuggestion(suggestion,shown,api);
      if(!result.applied){setComparison(result.comparison);setMessage('The dataset or inspection state changed. Review this refreshed comparison, then approve it individually.');return;}
      setApplied(true);onApproved?.(suggestion.candidate_revision_uuid);setMessage('Approved. The saved dataset in this sidebar protocol is updated. Open it to inspect the new epochs; no export file was created.');onChange?.();
    }catch(error){setError(error.message);}finally{setBusy(false);onBusyChange?.(false);}
  }
  const removing=(shown.diff_counts?.removed || 0)>0;
  return <section className={`protocol-new-data ${importView?'import-ready-protocol':''} ${alreadyApplied?'is-added':''}`} aria-label={importView?humanize(suggestion.protocol_name):"New data matching saved protocol query"}>
    <div className="protocol-new-data-heading"><Sparkles size={19}/><div><h2>{importView?humanize(suggestion.protocol_name):suggestion.status==='stale'?'Saved proposal needs a refresh':'New data matches your saved query'}</h2><p>{suggestion.source_filename || 'Imported recording'} · {time(suggestion.created_at)}</p></div>{importView&&<span className={`import-ready-state ${alreadyApplied?'added':''}`}>{alreadyApplied?<CheckCircle2 size={15}/>:suggestion.status==='stale'?<Clock3 size={13}/>:<Sparkles size={13}/>} {alreadyApplied?'Approved':suggestion.status==='stale'?'Refresh needed':'Pending approval'}</span>}</div>
    {importView?<ReadinessVisual suggestion={shown} applied={alreadyApplied}/>:<CompactProtocolDiff comparison={shown}/>}{suggestion.status==='stale'&&<p className="protocol-new-data-note" role="status">Source membership changed after this proposal was saved. Open the protocol and use Refresh & compare to regenerate it before adding data.</p>}
    <div className="protocol-suggestion-actions"><button className="primary" disabled={disabled||busy||alreadyApplied||suggestion.status==='stale'} onClick={add}>{busy?<LoaderCircle size={15} className="spin"/>:alreadyApplied?<Check size={15}/>:<Plus size={15}/>} {busy?'Approving…':alreadyApplied?'Approved':importView?'Approve':removing?'Apply dataset update':'Add matched data'}</button><span>{removing?'This proposal includes removals.':'Existing inspection decisions are preserved.'}</span></div>
    <details className="protocol-suggestion-details" open={!!comparison}><summary><ChevronDown size={13}/> Details · affected cells & epochs</summary><div className="protocol-suggestion-actions">{onReview&&!alreadyApplied&&<button disabled={disabled||busy} onClick={()=>onReview(suggestion.candidate_revision_uuid,suggestion.protocol_uuid)}>Inspect changes <ArrowRight size={14}/></button>}{importView&&onProtocol&&<button className="quiet" onClick={()=>onProtocol(suggestion.protocol_uuid)}>Open protocol <ArrowRight size={13}/></button>}</div><ProtocolDiff comparison={shown} detailsOnly={importView}/></details>
    {message&&<p className="protocol-new-data-note" role="status">{message}</p>}
    {error&&<div className="error" role="alert">{error}<p>Open the protocol and use Refresh & compare if the source or saved query changed. Check Activity & logs before retrying an interrupted request.</p></div>}
  </section>;
}
function ReadinessVisual({suggestion,applied=false}){
  const summary=suggestion.diff_summary||{},current=summary.current||{},proposed=summary.proposed||{},delta=summary.delta||{},diff=suggestion.diff_counts||{};
  const value=count=>Number.isFinite(count)?number(count):'—';
  const hasMembership=[current.epochs,proposed.epochs,diff.added,diff.removed].every(Number.isInteger);
  const added=diff.added,removed=diff.removed,retained=hasMembership?Math.max(0,current.epochs-removed):0;
  const scale=Math.max(1,current.epochs||0,proposed.epochs||0);
  return <div className="import-ready-visual">
    <div className="import-compare-cards">{[['cells','Cells',NeuronIcon],['epochs','Epochs',Activity]].map(([key,label,Icon])=><div className="import-compare-card" key={key}><header><Icon size={19}/><strong>{label}</strong>{Number.isFinite(delta[key])&&<span className={delta[key]<0?'is-removal':''}>{delta[key]>0?'+':''}{value(delta[key])} net</span>}</header><div className="import-before-after"><div><small>Before</small><strong>{value(current[key])}</strong></div><ArrowRight size={21}/><div><small>{applied?'Approved dataset':'After approval'}</small><strong>{value(proposed[key])}</strong></div></div></div>)}</div>
    {hasMembership&&<div className="import-membership-comparison" role="img" aria-label={`${retained} retained epochs; ${added} added; ${removed} removed`}><div><span>Before</span><div className="import-membership-bar"><i style={{width:`${retained/scale*100}%`}}/><i className="removed" style={{width:`${removed/scale*100}%`}}/></div></div><div><span>{applied?'Approved':'Proposed'}</span><div className="import-membership-bar"><i style={{width:`${retained/scale*100}%`}}/><i className="new" style={{width:`${added/scale*100}%`}}/></div></div></div>}
    <div className="import-membership-caption">{hasMembership&&<><span><i/>{value(retained)} retained</span><span><i className="new"/>+{value(added)} added</span><span className={removed>0?'import-removal':''}><i className="removed"/>−{value(removed)} removed</span></>}{diff.changed>0&&<span><RefreshCw size={12}/>{value(diff.changed)} metadata changed</span>}</div>
  </div>;
}

export function ImportSuggestions({suggestions=[],approvedHistory=[],protocols=[],projectId,sources=[],jobs=[],onReview,onProtocol,onChange,autoOpenJobUuid=null,dialogOnly=false,reviewLoading=false}){
  const preferences=useProjectPreference(projectId,'protocol_shortcuts').value;
  const [approvalBatch,setApprovalBatch]=useState({sequence:0,revisions:[]}),[busyCount,setBusyCount]=useState(0),[open,setOpen]=useState(false);
  const dialogRef=useRef(null),reviewHadPending=useRef(false);
  const [approvedHere,setApprovedHere]=useState([]);
  const busy=busyCount>0;
  function busyChanged(value){setBusyCount(count=>Math.max(0,count+(value?1:-1)));}
  const current=suggestions.map(item=>approvedHere.includes(item.candidate_revision_uuid)?{...item,status:'applied'}:item);
  const model=importReadiness({suggestions:current.filter(item=>item.status!=='applied'),protocols,preferences});
  const past=[...new Map([...current.filter(item=>item.status==='applied'),...approvedHistory].map(item=>[item.candidate_revision_uuid,item])).values()];
  const reviewPending=model.ready>0||model.stale>0;
  useEffect(()=>{if(!open){reviewHadPending.current=false;return;}if(reviewPending)reviewHadPending.current=true;else if(reviewHadPending.current&&!busy&&!reviewLoading)setOpen(false);},[open,reviewPending,busy,reviewLoading]);
  const latest=(autoOpenJobUuid&&jobs.find(job=>job.job_uuid===autoOpenJobUuid))||[...jobs].filter(job=>job&&(['complete','completed','success'].includes(job.status)||(job.status==='complete_with_warnings'&&job.catalog_committed===true))).sort((a,b)=>String(b.finished_at).localeCompare(String(a.finished_at)))[0];
  const catalogDelta=latest?.catalog_delta||latest?.progress?.catalog_delta;
  const source=sources.find(item=>item.source_sha256===latest?.source_sha256)||(latest?{filename:latest.source?.split?.('/').pop()||latest.filename||'Imported recording',counts:latest.progress?.counts}:null);
  useEffect(()=>{if(autoOpenJobUuid)setOpen(true);},[autoOpenJobUuid]);
  useEffect(()=>{if(open&&!dialogRef.current?.open)dialogRef.current?.showModal();else if(!open&&dialogRef.current?.open)dialogRef.current.close();},[open,latest?.job_uuid,suggestions.length]);
  if(!suggestions.length&&!latest)return null;
  const render=item=><ProtocolSuggestion key={`${item.protocol_uuid}:${item.candidate_revision_uuid}`} suggestion={item} onChange={onChange} onProtocol={id=>{setOpen(false);onProtocol?.(id);}} onReview={(...args)=>{setOpen(false);onReview?.(...args);}} importView disabled={busy||reviewLoading} approvalSignal={approvalBatch.revisions.includes(item.candidate_revision_uuid)?approvalBatch.sequence:0} onBusyChange={busyChanged} onApproved={id=>setApprovedHere(previous=>previous.includes(id)?previous:[...previous,id])}/>;
  const approveAll=<button className="primary" disabled={busy||reviewLoading||!model.pinnedReady} onClick={()=>setApprovalBatch(value=>({sequence:value.sequence+1,revisions:model.pinnedPending.map(item=>item.candidate_revision_uuid)}))}>{busy?<LoaderCircle size={15} className="spin"/>:<Check size={15}/>} {busy?'Checking updates…':'Approve All'}</button>;
  const summary=<section className="import-readiness" aria-label="Import readiness summary"><header className="import-readiness-heading"><div><div className="eyebrow">IMPORT REVIEW</div><h2><FileCheck2 size={23}/> {model.pinnedReady>0?'Review your pinned protocol updates.':'Protocol matching summary.'}</h2><p>Review the catalog import, then approve matching data for your pinned protocols.</p></div><div className="import-heading-actions">{!open&&approveAll}<span className="import-ready-total">{model.pinnedReady} pinned updates pending{model.added>0?` · ${model.added} approved`:''}{model.stale>0?` · ${model.stale} need refresh`:''}</span></div></header>{source&&<div className="import-source-summary"><Database size={21}/><div><strong>{source.filename}</strong><small>Latest completed import · {time(latest.finished_at)}</small></div><span><strong>{number(source.counts?.cells)}</strong> cells in imported source</span><span><strong>{number(source.counts?.epochs)}</strong> epochs in imported source</span><span className="import-checked"><Check size={14}/> Imported</span></div>}{catalogDelta&&<div className="import-catalog-delta" aria-label="Added to overall data store"><h3><Database size={16}/> Added to the overall data store</h3><div>{[['sources_added','recordings'],['cells_added','cells'],['epochs_added','epochs'],['protocol_types_added','protocol types']].filter(([key])=>Number.isInteger(catalogDelta[key])).map(([key,label])=><span key={key}><strong>+{number(catalogDelta[key])}</strong> {label}</span>)}</div><p>New catalog records from this import. Protocol updates below are approved separately.</p></div>}{latest?.recording_storage?.verified&&latest?.recording_storage?.original_removal_safe&&<p className="import-managed-copy"><Check size={15}/> Saved a verified copy in this project. You can remove the original H5 from Downloads; keep the project copy.</p>}{latest?.warnings?.length>0&&<p className="error">Some post-import checks need attention. See import diagnostics below.</p>}
  {reviewLoading&&<p className="import-managed-copy" role="status"><LoaderCircle size={15} className="spin"/> Refreshing catalog totals and protocol matches…</p> }{model.pinned.some(row=>row.suggestion)&&<div className="import-priority-group"><h3><Pin size={14}/> Pinned protocols · {model.pinnedReady} pending</h3>{model.pinned.filter(row=>row.suggestion).map(row=>render(row.suggestion))}</div>}
  {model.other.length>0&&<div className="import-priority-group"><h3>Other pending updates · {model.other.length}</h3>{model.other.map(render)}</div>}
  {!model.ready&&!model.stale&&<p className="import-review-empty" role="status">No unapproved protocol updates.</p>}
  {past.length>0&&<details className="import-other-protocols"><summary>Approved updates <span>{past.length}</span></summary>{past.map(item=><details key={item.candidate_revision_uuid} className="import-approved-entry"><summary><CheckCircle2 size={15}/> {humanize(item.protocol_name)} · {item.source_filename} · Approved {time(item.approved_at||item.created_at)}</summary>{render(item)}</details>)}</details>}
<p className="import-readiness-footnote">Approval updates the existing sidebar protocol’s saved dataset and records its query and changes. It does not create or replace an export file. Open the protocol to inspect and tag epochs. Cells may appear in more than one protocol.</p></section>;
  return <>{!dialogOnly&&<div className="import-review-launcher"><FileCheck2 size={18}/><span>{reviewPending?'Protocol updates ready for review':latest?'Import complete · review saved':'Import review'}</span><button onClick={()=>setOpen(true)}>Review import</button></div>}<dialog ref={dialogRef} className="import-review-dialog" onCancel={event=>{if(busy)event.preventDefault();else setOpen(false);}} onClose={()=>setOpen(false)} aria-labelledby="import-review-title"><header><div><h2 id="import-review-title">Review imported data</h2><p>Closing this review leaves unapproved protocol updates pending.</p></div><div className="import-heading-actions">{approveAll}<button className="icon-button" disabled={busy} aria-label="Close import review" onClick={()=>setOpen(false)}><X size={18}/></button></div></header>{open&&summary}<footer><button disabled={busy} onClick={()=>setOpen(false)}>Done reviewing</button></footer></dialog></>;
}
