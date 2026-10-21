import {useSemanticReset} from '../../useSemanticReset.js';
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {protocolMergeUndoVersion,subscribeMergeUndone} from '../../incoming-workbench/mergeUndo.js';
import {importReviewCards,mergeAllRequest,pendingProtocolSuggestion,sourceMergeRequest} from '../protocolSuggestions.js';
import useWorkbenchQueue from '../../incoming-workbench/useWorkbenchQueue.js';
import {ArrowRight,Check,Info,LoaderCircle,Sparkles,Pin,Database,FileCheck2,X} from 'lucide-react';
import {humanize,time,number} from "../../api.js";
import ProtocolDiff from './ProtocolDiff.jsx';
import ViewPreparation from './ViewPreparation.jsx';
import InspectImportButton from '../../recording-import/ui/InspectImportButton.jsx';
import './ProtocolSuggestion.css';
import {managedRecordingMessage} from '../../recording-import/importProgress.js';
import {useProjectPreference} from "../../project-preferences/useProjectPreference.js";
import {importReviewStatusLabel} from "../../recording-import/useImportReviewStatus.js";

// Overview mode passes pendingProtocol/main instead of a suggestion: the card
// then follows the cumulative queue (mergeable pending only) and its hold merges
// all of it. A verified receipt retires the card for the queue revision it
// showed; the refreshed queue then decides whether anything is still pending.
export default function ProtocolSuggestion({suggestion:given,pendingProtocol=null,main=null,projectId,revision,queue:provided,protocolName,onMerge,onProtocol,importView=false,disabled=false}){
  const launching=useRef(false),[merging,setMerging]=useState(false),[error,setError]=useState(''),[retired,setRetired]=useState(null);
  const queue=useWorkbenchQueue(pendingProtocol||'',revision,pendingProtocol?provided:null,projectId);
  const undoVersion=useSyncExternalStore(subscribeMergeUndone,()=>protocolMergeUndoVersion(projectId,pendingProtocol||given?.protocol_uuid));
  if(queue.preparation||queue.preparing)return <ViewPreparation resource={queue}/>;
  const pending=pendingProtocol&&!given?pendingProtocolSuggestion(queue.data,main,pendingProtocol):null;
  if(pending?.blocked)return <p className="protocol-merge-blocked" role="status"><Info size={14} aria-hidden="true"/> {pending.blocked}</p>;
  const suggestion=given||(pending&&!(retired?.queueRevision===pending.queue_revision&&retired.undoVersion===undoVersion)?pending:null);
  if(!suggestion)return null;
  const mergeAll=suggestion.merge_all===true;
  const applied=suggestion.status==='applied',stale=suggestion.status==='stale';
  const hasAdditions=Number.isSafeInteger(suggestion.diff_counts?.added)&&suggestion.diff_counts.added>0;
  const sourceRequest=mergeAll?mergeAllRequest(suggestion):sourceMergeRequest(suggestion),identity=mergeAll?`${suggestion.protocol_uuid}:${suggestion.queue_revision}`:`${suggestion.candidate_revision_uuid}:${suggestion.source_sha256}`;
  // Overview and import review share one hold control and one source-scoped
  // merge request; a plain click never merges or opens a cumulative preview.
  const holdMerge=onMerge&&sourceRequest?()=>merge(importView||mergeAll?sourceRequest:{...sourceRequest,origin:'protocol-overview'}):undefined;
  async function merge(options){
    if(launching.current||disabled||applied||stale||!hasAdditions||!onMerge||mergeAll&&(queue.loading||queue.error))return;
    launching.current=true;setMerging(true);setError('');
    try{if(await onMerge(suggestion.protocol_uuid,options)!==true)throw Error('The destination is unavailable. Refresh the project before merging.');if(mergeAll){setRetired({queueRevision:suggestion.queue_revision,undoVersion});queue.reload();}}
    catch(error){setError(error.message);}
    finally{launching.current=false;setMerging(false);}
  }
  const title=humanize(protocolName??suggestion.protocol_name);
  const mergeAllLabels=mergeAll?{mergeLabel:'Hold to merge all',mergeTitle:'Hold for one second to merge every new mergeable epoch into Main'}:{};
  return <section className={`protocol-new-data ${importView?'import-ready-protocol':''} ${applied?'is-added':''}`} aria-label={importView?title:'New data matching saved protocol query'}>
    <div className="protocol-new-data-heading"><Sparkles size={19}/><div><h2>{importView?title:applied?'Applied dataset update':stale?'Saved proposal needs a refresh':'New data matches your saved query'}</h2><p>{mergeAll?`${number(suggestion.pending_epoch_count)} new ${suggestion.pending_epoch_count===1?'epoch':'epochs'}${Number.isSafeInteger(suggestion.pending_cell_count)?` from ${number(suggestion.pending_cell_count)} ${suggestion.pending_cell_count===1?'cell':'cells'}`:''} not yet in Main${suggestion.recordings.length?` · from ${suggestion.recordings.join(', ')}${suggestion.more_recordings?' and more':''}`:''}`:<>{suggestion.source_filename||'Imported recording'} · {time(suggestion.created_at)}</>}</p></div></div>
    <div className="protocol-match-summary"><ProtocolDiff comparison={suggestion} showProtocolCount={!mergeAll}/><div className="protocol-match-actions">
      {importView?<InspectImportButton key={identity} identity={identity} disabled={disabled||merging||!onProtocol||mergeAll&&(queue.loading||!!queue.error)} onInspect={()=>onProtocol?.(suggestion.protocol_uuid,mergeAll?{}:{candidate_revision_uuid:suggestion.candidate_revision_uuid})} onMerge={holdMerge} {...mergeAllLabels}/>:!applied?<InspectImportButton key={identity} identity={identity} disabled={disabled||merging||!onProtocol||mergeAll&&(queue.loading||!!queue.error)} onInspect={()=>onProtocol?.(suggestion.protocol_uuid)} onMerge={holdMerge} {...mergeAllLabels}/>:<button disabled={disabled||!onProtocol} onClick={()=>onProtocol?.(suggestion.protocol_uuid)}>Inspect in Workbench <ArrowRight size={14}/></button>}
      {!importView&&!applied&&<small>{stale?'Refresh the saved proposal in Workbench.':mergeAll?(holdMerge?'Hold to merge all new epochs into Main, or inspect them in Workbench to pick some. Existing Main recordings and draft exclusions are kept.':'Inspect in Workbench to review and merge these additions.'):holdMerge?`Hold to merge eligible additions from ${suggestion.source_filename||'this recording'} into Main. Main recordings and draft exclusions are kept; additions from other pending recordings stay in Workbench.`:'Inspect in Workbench to review and merge these additions.'}</small>}
    </div></div>
    {merging&&<p role="status">{mergeAll?'Merging all new epochs into Main…':'Merging eligible additions into Main…'}</p>}
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}

// Review imported data shows the same per-protocol pending pool as Overview and
// Workbench: one Overview card (import view) per protocol with mergeable pending
// epochs, from /workbench/summary. Its hold merges all of that protocol. The
// dialog closes by itself only once a refreshed summary shows nothing pending.
export function ImportSuggestions({workbenchSummary=null,protocols=[],projectId,sources=[],jobs=[],onProtocol,onMerge,autoOpenJobUuid=null,dialogOnly=false,reviewLoading=false,reviewStatus=null}){
  const preferences=useProjectPreference(projectId,'protocol_shortcuts').value;
  const [open,setOpen]=useState(false);
  // Pending counts may stay cached while editing Main; opening review renews
  // the queue fence before its hold controls can submit an acceptance.
  useEffect(()=>{if(open)workbenchSummary?.reload?.();},[open,workbenchSummary?.reload]);
  const dialogRef=useRef(null),reviewHadPending=useRef(false);
  const model=importReviewCards({summary:workbenchSummary?.data,protocols,preferences});
  const unavailable=!!workbenchSummary?.error||!!workbenchSummary?.preparation||!!workbenchSummary?.preparing;
  const refreshing=reviewLoading||!!workbenchSummary?.loading||unavailable;
  const reviewPending=model.ready>0;
  useEffect(()=>{if(!open){reviewHadPending.current=false;return;}if(reviewPending)reviewHadPending.current=true;else if(reviewHadPending.current&&!refreshing)setOpen(false);},[open,reviewPending,refreshing]);
  const latest=(autoOpenJobUuid&&jobs.find(job=>job.job_uuid===autoOpenJobUuid))||[...jobs].filter(job=>job&&(['complete','completed','success'].includes(job.status)||(job.status==='complete_with_warnings'&&job.catalog_committed===true))).sort((a,b)=>String(b.finished_at).localeCompare(String(a.finished_at)))[0];
  const managedMessage=managedRecordingMessage(latest);
  const catalogDelta=latest?.catalog_delta||latest?.progress?.catalog_delta;
  const source=sources.find(item=>item.source_sha256===latest?.source_sha256)||(latest?{filename:latest.source?.split?.('/').pop()||latest.filename||'Imported recording',counts:latest.progress?.counts}:null);
  useSemanticReset(autoOpenJobUuid,()=>{if(autoOpenJobUuid)setOpen(true);});
  useEffect(()=>{if(open&&!dialogRef.current?.open)dialogRef.current?.showModal();else if(!open&&dialogRef.current?.open)dialogRef.current.close();},[open,latest?.job_uuid,model.ready]);
  const pendingReview=Number.isSafeInteger(reviewStatus?.pendingProtocols)&&reviewStatus.pendingProtocols>0;
  const reviewLabel=importReviewStatusLabel(reviewStatus);
  if(!model.ready&&!latest&&!pendingReview&&!unavailable)return null;
  const render=row=><ProtocolSuggestion key={`${projectId}:${row.protocol.protocol_uuid}`} projectId={projectId} pendingProtocol={row.protocol.protocol_uuid} queue={row.queue} main={row.main} protocolName={row.protocol.name} onProtocol={onProtocol?(id,options)=>{setOpen(false);onProtocol(id,options);}:undefined} onMerge={onMerge} importView disabled={refreshing}/>;
  const summary=<section className="import-readiness" aria-label="Import readiness summary"><header className="import-readiness-heading"><div><div className="eyebrow">IMPORT REVIEW</div><h2><FileCheck2 size={23}/> {model.pinnedReady>0?'Review your pinned protocol updates.':'Protocol matching summary.'}</h2></div><div className="import-heading-actions"><span className="import-ready-total">{unavailable?'Pending updates unavailable':`${model.pinnedReady} pinned updates pending`}</span></div></header>{source&&<div className="import-source-summary"><Database size={21}/><div><strong>{source.filename}</strong><small>Latest completed import · {time(latest.finished_at)}</small></div><span><strong>{number(source.counts?.cells)}</strong> cells in imported source</span><span><strong>{number(source.counts?.epochs)}</strong> epochs in imported source</span><span className="import-checked"><Check size={14}/> Imported</span></div>}{catalogDelta&&<div className="import-catalog-delta" aria-label="Added to overall data store"><h3><Database size={16}/> Added to the overall data store</h3><div>{[['sources_added','recordings'],['cells_added','cells'],['epochs_added','epochs'],['protocol_types_added','protocol types']].filter(([key])=>Number.isInteger(catalogDelta[key])).map(([key,label])=><span key={key}><strong>+{number(catalogDelta[key])}</strong> {label}</span>)}</div><p>New catalog records from this import. Merge new data into a protocol below.</p></div>}{managedMessage&&<p className="import-managed-copy"><Check size={15}/> {managedMessage}</p>}{latest?.warnings?.length>0&&<p className="error">Some post-import checks need attention. See import diagnostics below.</p>}
  {(reviewLoading||workbenchSummary?.loading)&&<p className="import-managed-copy" role="status"><LoaderCircle size={15} className="spin"/> Refreshing catalog totals and protocol matches…</p> }{model.pinned.length>0&&<div className="import-priority-group"><h3><Pin size={14}/> Pinned protocols · {model.pinnedReady} pending</h3>{model.pinned.map(render)}</div>}
  {model.other.length>0&&<div className="import-priority-group"><h3>Other pending updates · {model.other.length}</h3>{model.other.map(render)}</div>}
  <ViewPreparation resource={workbenchSummary}/>
  {workbenchSummary?.error&&!workbenchSummary?.preparation&&<p role="alert">Pending updates unavailable. <button onClick={workbenchSummary.reload}>Retry</button></p>}
  {!model.ready&&!unavailable&&<p className="import-review-empty" role="status">No pending protocol updates.</p>}
<p className="import-readiness-footnote">Hold to merge all new data for a protocol into Main, or inspect it in Workbench to pick individual epochs. Existing Main recordings and draft exclusions are kept. Cells may appear in more than one protocol.</p></section>;
  return <>{!dialogOnly&&<div className="import-review-launcher"><FileCheck2 size={18}/><span role="status" aria-live="polite">{reviewLabel}</span><button className={`import-review-button${pendingReview?' has-pending':''}`} aria-label={`Review import — ${reviewLabel}`} aria-haspopup="dialog" onClick={()=>setOpen(true)}>Review import{pendingReview&&<span className="import-review-dot" aria-hidden="true"/>}</button></div>}<dialog ref={dialogRef} className="import-review-dialog" onCancel={()=>setOpen(false)} onClose={()=>setOpen(false)} aria-labelledby="import-review-title"><header><div><h2 id="import-review-title">Review imported data</h2><p>Closing this review leaves incoming recordings pending.</p></div><div className="import-heading-actions"><button className="icon-button" aria-label="Close import review" onClick={()=>setOpen(false)}><X size={18}/></button></div></header>{open&&summary}<footer><button onClick={()=>setOpen(false)}>Done reviewing</button></footer></dialog></>;
}
