import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowUpCircle,RefreshCw,X} from 'lucide-react';
import {api} from '../api.js';
import {updateNotice,releaseLink,watchAppUpdates,mergeUpdateCheck} from '../appUpdates.js';
import './AppUpdates.css';
import {desktopBridge} from '../desktopLifecycle.js';

function UpdateDialog({status,busy,operation,error,onCheck,onClose,onDownload,onRestart,download}){
  const dialog=useRef(null);
  useEffect(()=>{dialog.current.showModal();const element=dialog.current;return()=>element.close();},[]);
  const installed=typeof status?.installed==='string'?status.installed:status?.installed?.version;
  const notice=updateNotice(status),url=releaseLink(status?.release_url);
  const desktop=!!desktopBridge();
  const testing=desktop&&status?.channel==='unsigned-testing';
  const ready=status?.state==='Ready'||!!notice&&(status?.staged_version===notice.version||download?.state==='complete'&&download.result?.version===notice.version);
  return createPortal(<dialog ref={dialog} className="app-update-dialog" aria-labelledby="app-update-title" onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2 id="app-update-title">Release / Publish</h2><button autoFocus className="icon-button" aria-label="Close updates" onClick={onClose}><X size={18}/></button></header>
    <p>Rieke OS app version: <strong>{installed||'Development checkout'}</strong></p>
    {testing&&<p><strong>Unsigned testing</strong> · Install only releases you trust from the Rieke OS GitHub repository.</p>}
    <p className="app-update-automatic">{testing?'Updates are checked automatically at startup and about once an hour. You choose when to download and restart to update.':desktop?'Updates are checked automatically at startup and about once an hour. Available updates download quietly.':'Updates are checked automatically when you open the app and every 15 minutes while it is visible. Available updates appear here quietly.'}</p>
    {!testing&&(desktop||status?.can_stage)&&<p>New versions download automatically. After you close Rieke OS and its project services, the next launch applies the prepared update.</p>}
    <p role="status">{status?.state==='Installing'?'Restarting to update…':status?.state==='Draining'?'Waiting for current work to finish…':status?.state==='Validating'?'Verifying the update…':busy?(operation==='restart'?'Preparing to restart…':operation==='download'||status?.state==='Downloading'?'Downloading the update…':'Checking for updates…'):notice?.message||status?.message||'Check for a published Rieke OS release.'}</p>
    {status?.check_error&&!error&&<p role="status">{status.check_error} The previously found update is still shown.</p>}
    {error&&<p role="alert" className="error">{error}</p>}
    {notice&&!desktop&&!status?.can_stage&&<p>Automatic installation is not available for this installation. Review the release instructions before updating.</p>}
    {desktop&&['Downloading','Validating'].includes(status?.state)&&<p role="status">Preparing the update. The current app remains active.</p>}
    {desktop&&ready&&<p role="status">{testing?'Update ready. Choose when to restart to update.':'Update ready for an orderly quit. Startup will be checked before projects reopen.'}</p>}
    {download?.state==='running'&&<p role="status">Downloading and verifying the update. The current app remains active.</p>}
    {ready&&!testing&&<p role="status">{download?.result?.message||'Update ready. Close Rieke OS and all project services; the next launch will use this version.'}</p>}
    {download?.state==='failed'&&<p role="alert">{download.error}</p>}
    {status?.checked_at&&<small>Last checked: {new Date(status.checked_at).toLocaleString()}</small>}
    <footer>{url&&(desktop?<button onClick={()=>desktopBridge().openReleaseNotes(url)}>Release notes</button>:<a href={url} target="_blank" rel="noopener noreferrer">Release notes</a>)}{notice&&(testing?status.can_download:!desktop&&status.can_stage)&&!ready&&<button disabled={busy||download?.state==='running'} onClick={onDownload}>{download?.state==='failed'?'Retry download':'Download update'}</button>}{testing&&ready&&<button disabled={busy} onClick={onRestart}>Restart to update</button>}<button disabled={busy} onClick={onCheck}><RefreshCw size={14} className={busy?'spin':''}/> Check for updates</button></footer>
  </dialog>,document.body);
}

export default function AppUpdates({sidebar=false}){
  const [status,setStatus]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[open,setOpen]=useState(false);
  const alive=useRef(false),checking=useRef(false);
  const [download,setDownload]=useState(null);
  const [operation,setOperation]=useState(null);
  async function check(force=false){
    if(checking.current)return;checking.current=true;setBusy(true);setError('');
    try{const bridge=desktopBridge();const result=bridge?await bridge.checkForUpdates():await api('/app/updates/check',{method:'POST',body:force?{force:true}:{}});if(alive.current){setStatus(previous=>mergeUpdateCheck(previous,result));if(result.download)setDownload(result.download);}}
    catch(error){if(alive.current){setError(error.message);setStatus(previous=>mergeUpdateCheck(previous,{state:'error',message:'Could not check for updates. The current app remains usable.'}));}}
    finally{checking.current=false;if(alive.current)setBusy(false);}
  }
  async function stage(){
    setError('');setOperation('download');
    try{const bridge=desktopBridge();if(bridge){const result=await bridge.downloadUpdate();if(alive.current&&result?.state)setStatus(result);}
      else{const result=await api('/app/updates/stage',{method:'POST',body:{},headers:{'X-Rieke-Update-Token':status.update_token}});if(alive.current)setDownload(result);}}
    catch(error){if(alive.current)setError(error.message);}
    finally{if(alive.current)setOperation(null);}
  }
  async function restart(){
    setError('');setOperation('restart');
    try{const result=await desktopBridge().restartToUpdate();if(alive.current){if(!result?.ready)setError(result?.reason||'The app is waiting for its current work to finish.');else if(result.installing)setStatus(previous=>({...previous,state:'Installing'}));}}
    catch(error){if(alive.current)setError(error.message);}
    finally{if(alive.current)setOperation(null);}
  }
  useEffect(()=>{
    if(download?.state!=='running')return;
    let cancelled=false,timer;
    async function poll(){try{const result=await api('/app/updates/download');if(!cancelled){setError('');setDownload(result);if(result.state==='running')timer=setTimeout(poll,1500);}}catch(error){if(!cancelled){setError(`Update status unavailable: ${error.message}`);timer=setTimeout(poll,5000);}}}
    timer=setTimeout(poll,1000);return()=>{cancelled=true;clearTimeout(timer);};
  },[download?.state]);
  useEffect(()=>{alive.current=true;const bridge=desktopBridge();if(bridge){bridge.status().then(result=>{if(alive.current)setStatus(result);}).catch(()=>{});const stop=bridge.onStatus(result=>{if(alive.current)setStatus(result);});return()=>{alive.current=false;stop();};}const stop=watchAppUpdates(()=>check());return()=>{alive.current=false;stop();};},[]);
  const notice=updateNotice(status);
  const ready=status?.state==='Ready'||!!notice&&(status?.staged_version===notice.version||download?.state==='complete'&&download.result?.version===notice.version);
  const detail=ready?`Rieke OS ${notice?.version||status?.available||''} is ready${status?.channel==='unsigned-testing'?' — choose Restart to update':' for the next launch'}`:notice?.message;
  return <><button className={`${sidebar?'nav-item app-update-nav':'app-update-button'} ${notice?'has-update':''}`} onClick={()=>setOpen(true)} title={detail||status?.message||'App updates'} aria-label={`Release / Publish${detail?` — ${detail}`:''}`} aria-haspopup="dialog" aria-expanded={open}><ArrowUpCircle size={17}/><span>Release / Publish</span>{notice&&<span className="app-update-badge" role="status" aria-live="polite">{status?.channel==='unsigned-testing'?`${ready?'Ready · ':''}v${notice.version}`:ready?'Ready':'Update'}</span>}</button>
    {open&&<UpdateDialog status={status} busy={busy||!!operation||['Checking','Downloading','Validating','Draining','Installing'].includes(status?.state)} operation={operation} error={error} onCheck={()=>check(true)} onDownload={stage} onRestart={restart} download={download} onClose={()=>setOpen(false)}/>}</>;
}
