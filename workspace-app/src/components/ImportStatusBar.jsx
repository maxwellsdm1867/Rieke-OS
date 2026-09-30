import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Check,FileWarning,LoaderCircle,X} from 'lucide-react';
import {jobProgressView,sourceName} from '../importProgress.js';
import './ImportStatusBar.css';

export function ImportProgressMeter({count,pending,label}){
  if(count)return <div className="import-progress-meter"><progress value={count.completed} max={count.total} aria-label={label || 'Current stage progress'}/><span>{count.label} · {Math.floor(count.percent)}%</span></div>;
  if(pending)return <div className="import-progress-meter"><progress aria-label={label || 'Current stage in progress; total not reported'}/><span>Stage total not reported</span></div>;
  return null;
}
export default function ImportStatusBar({monitor,transfer,onOpen}){
  const [notice,setNotice]=useState(null),[paused,setPaused]=useState(false);
  const seen=useRef(new Set()),initialized=useRef(false);
  useEffect(()=>{
    const rows=(Array.isArray(monitor.data?.jobs)?monitor.data.jobs:[]).filter(Boolean);
    const keyFor=job=>`${job.job_uuid}:${jobProgressView(job).pending?'running':job.status}`;
    // Existing import history should never become a new notification on reload.
    if(monitor.data&&!initialized.current){
      initialized.current=true;
      for(const job of rows)if(!jobProgressView(job).pending)seen.current.add(keyFor(job));
    }
    let next=null;
    if(transfer&&!['accepted'].includes(transfer.phase)){
      const failed=transfer.phase==='error';
      next={key:`request:${transfer.started_at}:${failed?'error':'running'}`,title:failed?'Import request needs attention':'Import started',filename:transfer.filename,attention:failed,pending:!failed};
    }else if(monitor.connectionError){
      next={key:`connection:${monitor.connectionError}`,title:'Import status unavailable',filename:'Open import history to check the connection.',attention:true};
    }else{
      const job=rows.find(row=>!seen.current.has(keyFor(row)));
      if(job){const view=jobProgressView(job);next={key:keyFor(job),title:view.pending?'Import in progress':view.label,filename:sourceName(job),pending:view.pending,attention:view.failed||view.warning||view.interrupted};}
    }
    if(next&&!seen.current.has(next.key)){seen.current.add(next.key);setPaused(false);setNotice(next);}
  },[monitor.data,monitor.connectionError,transfer]);
  useEffect(()=>{
    if(!notice||paused)return;
    const timer=setTimeout(()=>setNotice(null),notice.attention?10000:6000);
    return()=>clearTimeout(timer);
  },[notice,paused]);
  if(!notice)return null;
  const Icon=notice.attention?FileWarning:notice.pending?LoaderCircle:Check;
  return <aside className={`import-toast ${notice.attention?'is-attention':''}`} aria-label="Import notification" onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)} onFocus={()=>setPaused(true)} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setPaused(false);}}>
    <div role="status" aria-live="polite" aria-atomic="true"><Icon size={17} className={notice.pending?'spin':''}/><strong>{notice.title}</strong><span>{notice.filename}</span></div>
    <button className="import-toast-open" onClick={()=>{setNotice(null);onOpen();}} aria-label="View import details"><ArrowUpRight size={15}/> View details</button>
    <button className="icon-button" aria-label="Dismiss import notification" onClick={()=>setNotice(null)}><X size={14}/></button>
  </aside>;
}
