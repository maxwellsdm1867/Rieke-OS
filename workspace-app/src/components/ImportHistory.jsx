import {useEffect,useState} from 'react';
import {Check,CopyCheck,FileWarning,LoaderCircle,ChevronRight} from 'lucide-react';
import {time} from '../api.js';
import {Empty} from './Common.jsx';
import {ImportProgressMeter} from './ImportStatusBar.jsx';
import {IMPORT_TERMINAL,isImportPending,jobProgressView,sourceName,elapsedLabel,sourceCountsLabel} from '../importProgress.js';
import './ImportHistory.css';
export {IMPORT_TERMINAL};

export default function ImportHistory({jobs=[],onStores,observedAt}) {
  const [now,setNow]=useState(Date.now());
  const records=Array.isArray(jobs)?jobs:[];
  const pending=records.some(isImportPending);
  useEffect(()=>{if(!pending)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[pending]);
  if(!records.length)return <Empty title="No import attempts yet">Each attempt records its duplicate check, validation result and completion time.</Empty>;
  return <div className="import-history">{records.map((raw,index)=><ImportHistoryRow key={raw?.job_uuid||index} raw={raw} now={now} observedAt={observedAt} onStores={onStores}/>)}</div>;
}

function ImportHistoryRow({raw,now,observedAt,onStores}){
    const job=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw:{status:'interrupted',error:'Saved job record is malformed; inspect diagnostic details before retrying.'};
    const view=jobProgressView(job,now,observedAt || now),duplicate=job.status==='duplicate';
    const Icon=view.pending?LoaderCircle:duplicate?CopyCheck:view.failed||view.warning||view.interrupted?FileWarning:Check;
    const warnings=Array.isArray(job.duplicate_check?.same_name_warnings)?job.duplicate_check.same_name_warnings:[];
    const attention=view.pending||view.failed||view.interrupted||view.warning||view.requiresReconciliation||warnings.length>0||!!job.audit_write_error||!!job.warnings?.length;
    const [open,setOpen]=useState(attention);
    useEffect(()=>{if(attention)setOpen(true);},[attention]);
    return <details open={open} onToggle={event=>{if(event.target===event.currentTarget)setOpen(event.currentTarget.open);}} className={`import-history-row ${view.failed||view.interrupted?'is-failed':duplicate?'is-duplicate':''}`}>
      <summary className="import-history-summary"><ChevronRight className="import-history-chevron" size={14}/><Icon size={16} className={view.pending?'spin':''} aria-hidden="true"/><strong className="import-history-filename" title={sourceName(job)}>{sourceName(job)}</strong><span className="import-history-result">{duplicate?'Already imported · skipped':view.label}</span><time>{time(job.finished_at || job.started_at || job.created_at)}</time></summary>
      <div className="import-history-expanded">
        <div className="import-history-progress">{view.pending&&<p>{view.stage}{job.progress?.message?` · ${job.progress.message}`:''}</p>}<ImportProgressMeter count={view.count} pending={view.pending} label={`${view.stage} progress`}/>{view.elapsed!=null&&<p>{elapsedLabel(view.elapsed)} elapsed{view.stageElapsed!=null&&view.pending?` · ${elapsedLabel(view.stageElapsed)} in this stage`:''}{view.pending&&view.progressAge!=null?` · last stage/count update ${elapsedLabel(view.progressAge)} ago`:''}</p>}</div>
        {view.committed&&sourceCountsLabel(job)&&<p>Source totals: {sourceCountsLabel(job)}</p>}{duplicate&&<p>Existing catalog records and query participation were kept. No parsing or duplicate records were added.</p>}
        {(view.failed||view.interrupted)&&<p role="status">{typeof job.error==='string'?job.error:job.diagnostics?.message}</p>}
        {view.requiresReconciliation&&<p className="import-name-warning">{view.committed?'Catalog commit is confirmed; finalization needs reconciliation. Inspect diagnostics before retrying follow-up work.':'Catalog commit state is unconfirmed. Inspect the data stores and diagnostic record before submitting this source again.'}</p>}
        {view.committed&&!view.requiresReconciliation&&(view.interrupted||view.warning)&&<p>The catalog import committed. Follow-up work needs attention; do not assume the data was rolled back.</p>}
        {warnings.length>0&&<p className="import-name-warning">A registered file has the same name but different contents. It was not treated as a duplicate; identity validation still applies.</p>}
        {Array.isArray(job.warnings)&&job.warnings.map((warning,index)=><p className="import-name-warning" key={index}>{typeof warning==='string'?warning:warning?.message || 'A follow-up check needs attention.'}{['protocol_query','post_import_refresh'].includes(warning?.stage)?' Open the protocol and use Refresh & compare to retry its saved query.':''}</p>)}
        {job.audit_write_error&&<p className="import-name-warning">The SQL audit could not be written. This attempt remains in the local job log.</p>}
        <details><summary>Import evidence & diagnostic details</summary>{job.log_path&&<p>Log: <code>{String(job.log_path)}</code></p>}<pre>{JSON.stringify(raw,null,2)}</pre></details>
        {onStores&&<button className="import-history-store-link" onClick={onStores}>Inspect data stores</button>}
      </div>
    </details>;
}
