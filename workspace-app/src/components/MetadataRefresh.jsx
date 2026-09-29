import {useEffect,useRef,useState} from 'react';
import {AlertTriangle,Check,ChevronDown,RefreshCw,X} from 'lucide-react';
import {api,number,useResource} from '../api.js';
import {elapsedLabel} from '../importProgress.js';
import {validMetadataRefresh} from '../metadataRefresh.js';
import './MetadataRefresh.css';

export default function MetadataRefresh({revision,onChange}){
  const status=useResource('/metadata/status',revision);
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[seconds,setSeconds]=useState(0),[error,setError]=useState(''),[receipt,setReceipt]=useState(null),[warnings,setWarnings]=useState([]);
  const running=useRef(false),started=useRef(0),root=useRef(null);
  const saved=validMetadataRefresh(status.data?.last_refresh)?status.data.last_refresh:null;
  const last=receipt&&(!saved||Date.parse(receipt.completed_at)>=Date.parse(saved.completed_at))?receipt:saved;
  const visibleWarnings=last===receipt?warnings:(Array.isArray(last?.warnings)?last.warnings:[]);
  const latestError=status.data?.latest_attempt?.error || status.data?.latest_attempt?.error_type;
  useEffect(()=>{if(!busy)return;const timer=setInterval(()=>setSeconds((Date.now()-started.current)/1000),1000);return()=>clearInterval(timer);},[busy]);
  useEffect(()=>{if(!open)return;const outside=event=>{if(!root.current?.contains(event.target))setOpen(false);};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);},[open]);
  async function refresh(){
    if(running.current)return;
    running.current=true;started.current=Date.now();setSeconds(0);setBusy(true);setOpen(true);setError('');
    try{
      const result=await api('/metadata/refresh',{method:'POST',body:{}});
      if(!validMetadataRefresh(result.refresh))throw new Error('The refresh did not return a complete receipt. Check the latest status before running it again.');
      setReceipt(result.refresh);setWarnings(Array.isArray(result.warnings)?result.warnings:[]);onChange?.();status.reload();
    }catch(error){setError(error.message);status.reload();}
    finally{running.current=false;setBusy(false);}
  }
  return <div className="metadata-refresh" ref={root}>
    <button className="metadata-refresh-action" onClick={refresh} disabled={busy} title="Verify and incrementally refresh project metadata; protocol working datasets are unchanged" aria-label="Refresh project metadata"><RefreshCw size={15} className={busy?'spin':''}/><span>{busy?`Refreshing · ${elapsedLabel(seconds)}`:'Refresh metadata'}</span></button>
    <button className="icon-button metadata-refresh-details" onClick={()=>setOpen(value=>!value)} aria-expanded={open} aria-label="Metadata refresh status"><ChevronDown size={13}/></button>
    {open&&<section className="metadata-refresh-panel" aria-label="Metadata refresh status"><header><strong>Project metadata</strong><button className="icon-button" aria-label="Close metadata refresh status" onClick={()=>setOpen(false)}><X size={14}/></button></header>
      {busy?<p className="metadata-refresh-running" role="status"><RefreshCw size={15} className="spin"/> Verifying sources and refreshing changed metadata · {elapsedLabel(seconds)}</p>:error?<div className="metadata-refresh-error" role="alert"><AlertTriangle size={16}/><div><strong>Refresh result unconfirmed</strong><p>{error}</p><p>The last successful status is retained. Check status before trying again.</p></div></div>:receipt&&status.data?.status!=='needs_refresh'&&<p className="metadata-refresh-success" role="status"><Check size={15}/> Metadata refresh completed.</p>}
      {!busy&&status.data?.status==='needs_refresh'&&<p className="metadata-refresh-warning" role="status">Metadata needs a refresh. The last successful result below remains available.{latestError&&<span> Latest attempt: {typeof latestError==='string'?latestError:JSON.stringify(latestError)}</span>}</p>}
      {visibleWarnings.map((warning,index)=><p className="metadata-refresh-warning" role="status" key={index}>Refresh warning: {typeof warning==='string'?warning:warning?.message || JSON.stringify(warning)}</p>)}
      {last?<><div className="metadata-refresh-counts"><span><strong>{number(last.reused_sources)}</strong> sources reused</span><span><strong>{number(last.rebuilt_sources)}</strong> sources rebuilt</span></div><p>{number(last.sources)} sources · {number(last.epochs)} epochs · {number(last.protocols)} protocols</p><small>Last successful refresh: {new Date(last.completed_at).toLocaleString()} · {last.elapsed_seconds.toFixed(2)} s</small></>:<p>{status.loading?'Reading last refresh status…':status.data?.status==='needs_refresh'?'Metadata refresh is needed.':'No successful refresh has been reported.'}</p>}
      {status.error&&<p className="metadata-refresh-error" role="status">Status is unavailable: {status.error}</p>}
      <footer><span>Refresh does not apply protocol updates.</span><button disabled={status.loading} onClick={status.reload}>Check status</button></footer>
    </section>}
  </div>;
}
