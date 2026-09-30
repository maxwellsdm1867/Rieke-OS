import {useEffect,useRef,useState} from 'react';
import {api,time} from '../api.js';
import {epochResourceCache} from '../resourceCache.js';
import {startExternalTagMonitor} from '../externalTagMonitor.js';
import {Tags,AlertCircle,CheckCircle2,RefreshCw} from 'lucide-react';

export default function ExternalTagSync({enabled,onChange}){
  const changed=useRef(onChange),monitor=useRef(null);
  changed.current=onChange;
  const [status,setStatus]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    if(!enabled)return;
    const control=startExternalTagMonitor({scan:()=>api('/annotations/scan',{method:'POST',body:{}}),
      onChange:()=>{epochResourceCache.invalidate();changed.current?.();},
      onStatus:result=>{setStatus(result);setError('');},onError:setError,
      visible:()=>document.visibilityState!=='hidden'});
    monitor.current=control;
    const focus=()=>{if(document.visibilityState!=='hidden')control.check();};
    window.addEventListener('focus',focus);document.addEventListener('visibilitychange',focus);
    return()=>{control.stop();monitor.current=null;window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',focus);};
  },[enabled]);
  if(!enabled)return null;
  const issue=status?.exports?.flatMap(item=>item.errors||[])[0];
  const latest=status?.latest_import||[...(status?.receipts||[])].reverse().find(item=>item.addition_count>0);
  const attention=!!error||!!issue;
  const pending=status?.exports?.some(item=>item.pending>0);
  const heading=attention?'Couldn’t finish checking':pending?'Checking imports':status?'Checked for new tags':'Checking for new tags';
  return <details className="external-tag-sync"><summary aria-label="External tag sync" title={heading}><Tags size={16}/><span className="external-tag-label">External tags</span><span className={`tag-sync-dot ${attention?'warning':status?'ready':'pending'}`} aria-hidden="true"/></summary>
    <div className="tag-sync-card">
      <header className={attention?'warning':''}>{attention?<AlertCircle size={17}/>:<CheckCircle2 size={17}/>}<strong>{heading}</strong><button className="icon-button" aria-label="Check for new tags" title="Check now" onClick={()=>monitor.current?.check()}><RefreshCw size={14}/></button></header>
      <dl><div><dt>Last checked</dt><dd>{status?time(status.checked_at):'Checking…'}</dd></div>
        <div><dt>Latest import</dt><dd>{latest?<><strong>{latest.addition_count} {latest.addition_count===1?'tag':'tags'} from {latest.authors.map(author=>author.display_name).join(', ')}</strong><small>{time(latest.received_at)}</small></>:'No new tags imported yet'}</dd></div>
      </dl>
      {attention&&<p className="tag-sync-error" role="alert">{error||issue.error}</p>}
    </div>
  </details>;
}
