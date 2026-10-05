import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Check,GitMerge,LoaderCircle,Sparkles,Pin,Database,FileCheck2,X,CheckCircle2} from 'lucide-react';
import {humanize,time,number} from "../../api.js";
import ProtocolDiff from './ProtocolDiff.jsx';
import './ProtocolSuggestion.css';
import {importReadiness} from "../../recording-import/importReadiness.js";
import {useProjectPreference} from "../../project-preferences/useProjectPreference.js";
import {importReviewStatusLabel} from "../../recording-import/useImportReviewStatus.js";

export default function ProtocolSuggestion({suggestion,onMerge,onProtocol,importView=false,disabled=false}){
  const launching=useRef(false),[error,setError]=useState('');
  if(!suggestion)return null;
  const applied=suggestion.status==='applied',stale=suggestion.status==='stale';
  const hasAdditions=Number.isSafeInteger(suggestion.diff_counts?.added)&&suggestion.diff_counts.added>0;
  function merge(){
    if(launching.current||disabled||applied||stale||!hasAdditions||!onMerge)return;
    launching.current=true;setError('');
    if(onMerge(suggestion.protocol_uuid)!==true){launching.current=false;setError('The destination is unavailable. Refresh the project before merging.');}
  }
  return <section className={`protocol-new-data ${importView?'import-ready-protocol':''} ${applied?'is-added':''}`} aria-label={importView?humanize(suggestion.protocol_name):'New data matching saved protocol query'}>
    <div className="protocol-new-data-heading"><Sparkles size={19}/><div><h2>{importView?humanize(suggestion.protocol_name):applied?'Applied dataset update':stale?'Saved proposal needs a refresh':'New data matches your saved query'}</h2><p>{suggestion.source_filename||'Imported recording'} · {time(suggestion.created_at)}</p></div></div>
    <div className="protocol-match-summary"><ProtocolDiff comparison={suggestion}/><div className="protocol-match-actions">
      {!applied&&<button className="primary" disabled={disabled||stale||!hasAdditions||!onMerge} onClick={merge} title="Preview eligible additions across the incoming queue, preserving main recordings and your draft exclusions"><GitMerge size={15}/> Merge matched data</button>}
      <button disabled={disabled||!onProtocol} onClick={()=>onProtocol?.(suggestion.protocol_uuid)}>Inspect in Workbench <ArrowRight size={14}/></button>
      {!applied&&<small>{stale?'Refresh the saved proposal in Workbench.':'Merge opens a fresh preview of eligible additions for confirmation.'}</small>}
    </div></div>
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}

export function ImportSuggestions({suggestions=[],approvedHistory=[],protocols=[],projectId,sources=[],jobs=[],onReview,onProtocol,onMerge,onChange,autoOpenJobUuid=null,dialogOnly=false,reviewLoading=false,reviewStatus=null}){
  const preferences=useProjectPreference(projectId,'protocol_shortcuts').value;
  const [open,setOpen]=useState(false);
  const dialogRef=useRef(null),reviewHadPending=useRef(false);
  const current=suggestions;
  const model=importReadiness({suggestions:current.filter(item=>item.status!=='applied'),protocols,preferences});
  const past=[...new Map([...current.filter(item=>item.status==='applied'),...approvedHistory].map(item=>[item.candidate_revision_uuid,item])).values()];
  const reviewPending=model.ready>0||model.stale>0;
  useEffect(()=>{if(!open){reviewHadPending.current=false;return;}if(reviewPending)reviewHadPending.current=true;else if(reviewHadPending.current&&!reviewLoading)setOpen(false);},[open,reviewPending,reviewLoading]);
  const latest=(autoOpenJobUuid&&jobs.find(job=>job.job_uuid===autoOpenJobUuid))||[...jobs].filter(job=>job&&(['complete','completed','success'].includes(job.status)||(job.status==='complete_with_warnings'&&job.catalog_committed===true))).sort((a,b)=>String(b.finished_at).localeCompare(String(a.finished_at)))[0];
  const catalogDelta=latest?.catalog_delta||latest?.progress?.catalog_delta;
  const source=sources.find(item=>item.source_sha256===latest?.source_sha256)||(latest?{filename:latest.source?.split?.('/').pop()||latest.filename||'Imported recording',counts:latest.progress?.counts}:null);
  useEffect(()=>{if(autoOpenJobUuid)setOpen(true);},[autoOpenJobUuid]);
  useEffect(()=>{if(open&&!dialogRef.current?.open)dialogRef.current?.showModal();else if(!open&&dialogRef.current?.open)dialogRef.current.close();},[open,latest?.job_uuid,suggestions.length]);
  const pendingReview=Number.isSafeInteger(reviewStatus?.pendingProtocols)&&reviewStatus.pendingProtocols>0;
  const reviewLabel=importReviewStatusLabel(reviewStatus);
  if(!suggestions.length&&!latest&&!pendingReview)return null;
  const render=item=><ProtocolSuggestion key={`${item.protocol_uuid}:${item.candidate_revision_uuid}`} suggestion={item} onProtocol={onProtocol?id=>{setOpen(false);onProtocol(id);}:undefined} onMerge={onMerge?id=>{const opened=onMerge(id);if(opened===true)setOpen(false);return opened;}:undefined} importView disabled={reviewLoading}/>;
  const summary=<section className="import-readiness" aria-label="Import readiness summary"><header className="import-readiness-heading"><div><div className="eyebrow">IMPORT REVIEW</div><h2><FileCheck2 size={23}/> {model.pinnedReady>0?'Review your pinned protocol updates.':'Protocol matching summary.'}</h2></div><div className="import-heading-actions"><span className="import-ready-total">{model.pinnedReady} pinned updates pending{model.stale>0?` · ${model.stale} need refresh`:''}</span></div></header>{source&&<div className="import-source-summary"><Database size={21}/><div><strong>{source.filename}</strong><small>Latest completed import · {time(latest.finished_at)}</small></div><span><strong>{number(source.counts?.cells)}</strong> cells in imported source</span><span><strong>{number(source.counts?.epochs)}</strong> epochs in imported source</span><span className="import-checked"><Check size={14}/> Imported</span></div>}{catalogDelta&&<div className="import-catalog-delta" aria-label="Added to overall data store"><h3><Database size={16}/> Added to the overall data store</h3><div>{[['sources_added','recordings'],['cells_added','cells'],['epochs_added','epochs'],['protocol_types_added','protocol types']].filter(([key])=>Number.isInteger(catalogDelta[key])).map(([key,label])=><span key={key}><strong>+{number(catalogDelta[key])}</strong> {label}</span>)}</div><p>New catalog records from this import. Merge matched recordings into a protocol below.</p></div>}{latest?.recording_storage?.verified&&latest?.recording_storage?.original_removal_safe&&<p className="import-managed-copy"><Check size={15}/> Saved a verified copy in this project. You can remove the original H5 from Downloads; keep the project copy.</p>}{latest?.warnings?.length>0&&<p className="error">Some post-import checks need attention. See import diagnostics below.</p>}
  {reviewLoading&&<p className="import-managed-copy" role="status"><LoaderCircle size={15} className="spin"/> Refreshing catalog totals and protocol matches…</p> }{model.pinned.some(row=>row.suggestion)&&<div className="import-priority-group"><h3><Pin size={14}/> Pinned protocols · {model.pinnedReady} pending</h3>{model.pinned.filter(row=>row.suggestion).map(row=>render(row.suggestion))}</div>}
  {model.other.length>0&&<div className="import-priority-group"><h3>Other pending updates · {model.other.length}</h3>{model.other.map(render)}</div>}
  {!model.ready&&!model.stale&&<p className="import-review-empty" role="status">No pending protocol updates.</p>}
  {past.length>0&&<details className="import-other-protocols"><summary>Applied dataset updates <span>{past.length}</span></summary>{past.map(item=><details key={item.candidate_revision_uuid} className="import-approved-entry"><summary><CheckCircle2 size={15}/> {humanize(item.protocol_name)} · {item.source_filename} · Applied {time(item.approved_at||item.created_at)}</summary>{render(item)}</details>)}</details>}
<p className="import-readiness-footnote">Each merge previews the current incoming queue for that protocol. Existing main recordings and draft exclusions are retained. Cells may appear in more than one protocol.</p></section>;
  return <>{!dialogOnly&&<div className="import-review-launcher"><FileCheck2 size={18}/><span role="status" aria-live="polite">{reviewLabel}</span><button className={`import-review-button${pendingReview?' has-pending':''}`} aria-label={`Review import — ${reviewLabel}`} aria-haspopup="dialog" onClick={()=>setOpen(true)}>Review import{pendingReview&&<span className="import-review-dot" aria-hidden="true"/>}</button></div>}<dialog ref={dialogRef} className="import-review-dialog" onCancel={()=>setOpen(false)} onClose={()=>setOpen(false)} aria-labelledby="import-review-title"><header><div><h2 id="import-review-title">Review imported data</h2><p>Closing this review leaves incoming recordings pending.</p></div><div className="import-heading-actions"><button className="icon-button" aria-label="Close import review" onClick={()=>setOpen(false)}><X size={18}/></button></div></header>{open&&summary}<footer><button onClick={()=>setOpen(false)}>Done reviewing</button></footer></dialog></>;
}
