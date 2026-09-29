import {useEffect,useState} from 'react';
import {ArrowUpRight,Check,ChevronDown,FileWarning,LoaderCircle,RefreshCw,Upload,X} from 'lucide-react';
import {actualProgress,byteLabel,elapsedLabel,jobProgressView,selectImportJob,sourceName,sourceCountsLabel} from '../importProgress.js';
import './ImportStatusBar.css';

export function ImportProgressMeter({count,pending,label}){
  if(count)return <div className="import-progress-meter"><progress value={count.completed} max={count.total} aria-label={label || 'Current stage progress'}/><span>{count.label} · {Math.floor(count.percent)}%</span></div>;
  if(pending)return <div className="import-progress-meter"><progress aria-label={label || 'Current stage in progress; total not reported'}/><span>Stage total not reported</span></div>;
  return null;
}
export default function ImportStatusBar({monitor,transfer,onOpen,onDismissTransfer}){
  const [now,setNow]=useState(Date.now()),[dismissed,setDismissed]=useState(()=>new Set()),[details,setDetails]=useState(false);
  const rows=(Array.isArray(monitor.data?.jobs)?monitor.data.jobs:[]).filter(job=>job&&typeof job==='object');
  const transferVisible=transfer&&!['accepted'].includes(transfer.phase);
  const queued=transfer?.phase==='accepted'&&!rows.some(job=>job.job_uuid===transfer.job_uuid);
  const selected=selectImportJob(rows,dismissed,now);
  const job=queued?{job_uuid:transfer.job_uuid,status:'queued',source:transfer.filename,created_at:transfer.started_at}:selected;
  const view=job?jobProgressView(job,now,monitor.observedAt || now):null;
  const ticking=transferVisible||queued||view?.pending||!!monitor.connectionError;
  useEffect(()=>{if(!ticking)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[ticking]);
  useEffect(()=>setDetails(false),[job?.job_uuid,transfer?.started_at]);
  if(!transferVisible&&!job&&!monitor.connectionError)return null;
  const error=transferVisible&&transfer.phase==='error';
  const uncertain=!!monitor.connectionError;
  const pending=transferVisible? !error:view?.pending;
  const Icon=error||uncertain||view?.failed||view?.warning||view?.interrupted?FileWarning:pending?LoaderCircle:Check;
  const title=transferVisible?(error?(transfer.requestRejected?'Import request rejected':'Import request status unconfirmed'):transfer.phase==='uploading'?'Uploading recording':transfer.phase==='starting'?'Starting import request':'Upload sent · waiting for server'):uncertain?'Import status unavailable':view?.label || 'Import monitor';
  const filename=transferVisible?transfer.filename:job?sourceName(job):'Checking connection';
  const count=transferVisible?actualProgress({completed:transfer.loaded,total:transfer.total,unit:'bytes'}):view?.count;
  const elapsed=transferVisible?Math.max(0,(now-Date.parse(transfer.started_at))/1000):view?.elapsed;
  function dismiss(){if(transferVisible){onDismissTransfer?.();return;}if(job)setDismissed(previous=>new Set([...previous,`${job.job_uuid}:${job.status}`]));}
  return <section className={`import-status-bar ${error||uncertain||view?.failed||view?.interrupted?'is-attention':''}`} aria-label="Import progress">
    <div className="import-status-main"><Icon size={18} className={pending&&!uncertain?'spin':''}/><div className="import-status-description"><div role="status" aria-live="polite" aria-atomic="true"><strong>{title}</strong>{view?.pending&&!transferVisible&&!uncertain&&<span className="import-stage-announcement">{view.stage}</span>}<span title={filename}>{filename}</span></div><p>{transferVisible?(error?transfer.error:transfer.phase==='uploading'?'Bytes transferred to the local server. Parsing starts after the request is accepted.':transfer.phase==='starting'?'Waiting for the server to create an import job.':'Transfer finished. The server has not yet returned an import job.'):
      uncertain?'Connection interrupted. The last confirmed job state is shown; this does not establish import failure or rollback.':view?.requiresReconciliation?(view.committed?'Catalog commit confirmed; finalization needs reconciliation. Inspect diagnostics before retrying follow-up work.':'Check the catalog and diagnostics before submitting this source again; commit state is unconfirmed.'):view?.pending?view.stage:job?.message || (view?.warning?'Data was imported; review the follow-up diagnostics.':view?.failed?job.error:job?.status==='duplicate'?'No duplicate catalog records were added.':'Recorded in import history.')}</p></div>
      <div className="import-status-actions">{elapsed!=null&&<span className="import-elapsed">{elapsedLabel(elapsed)} elapsed</span>}<button onClick={onOpen}><ArrowUpRight size={13}/> Import workbench</button>{(error||uncertain)&&<button onClick={monitor.reload}><RefreshCw size={13}/> Refresh status</button>}<button onClick={()=>setDetails(value=>!value)} aria-expanded={details}><ChevronDown size={13}/> Diagnostics</button>{!pending&&!uncertain&&<button className="icon-button" aria-label="Dismiss import status" onClick={dismiss}><X size={14}/></button>}</div>
    </div>
    {!transferVisible&&view?.committed&&sourceCountsLabel(job)&&<p className="import-status-freshness">Source totals: {sourceCountsLabel(job)}</p>}
    {!error&&!uncertain&&<ImportProgressMeter count={count} pending={pending} label={transferVisible?'Upload bytes transferred':`${view?.stage || 'Import'} progress`}/>}
    {!transferVisible&&view?.pending&&<div className="import-status-freshness"><span>{view.stageElapsed!=null?`${elapsedLabel(view.stageElapsed)} in this stage`:'Stage start time not recorded'}</span><span>{view.progressAge!=null?`Last stage/count update ${elapsedLabel(view.progressAge)} ago`:'Stage progress timestamp not reported'}</span><span>{view.heartbeatAge!=null?`Monitor checked ${elapsedLabel(view.heartbeatAge)} ago`:monitor.observedAt?`Last status received ${elapsedLabel((now-monitor.observedAt)/1000)} ago`:'Waiting for a status response'}</span>{view.staleProgress&&<strong>No recent stage/count change; the monitor heartbeat does not prove parser progress.</strong>}</div>}
    {details&&<div className="import-status-diagnostics"><p>Diagnostics are read-only. Refresh checks status; it does not submit the import again.</p>{monitor.connectionError&&<p role="status">Connection error: {monitor.connectionError}</p>}<pre>{JSON.stringify(transferVisible?transfer:job,null,2)}</pre></div>}
  </section>;
}
