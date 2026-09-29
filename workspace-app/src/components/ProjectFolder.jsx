import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {FolderOpen,LoaderCircle,X} from 'lucide-react';
import {api} from '../api.js';
import './ProjectFolder.css';

export default function ProjectFolder({project,onClose,onFiles}){
  const dialog=useRef(null);
  const [directory,setDirectory]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{const element=dialog.current;element.showModal();return()=>element.close();},[]);
  async function open(event){
    event.preventDefault();if(busy||!directory.trim())return;
    setBusy(true);setError('');
    try{
      const result=await api('/projects/open-folder',{method:'POST',body:{directory:directory.trim()}});
      if(typeof result.url!=='string')throw new Error('The project service did not return an app URL.');
      const destination=new URL(result.url,window.location.href);
      if(!['http:','https:'].includes(destination.protocol)||!['127.0.0.1','localhost','[::1]'].includes(destination.hostname))throw new Error('The project service returned an invalid local URL.');
      window.location.assign(destination.href);
    }catch(error){setError(error.message);setBusy(false);}
  }
  return createPortal(<dialog ref={dialog} className="project-folder-dialog" aria-labelledby="project-folder-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
    <header><h2 id="project-folder-title"><FolderOpen size={19}/> Project folder</h2><button autoFocus className="icon-button" aria-label="Close project folder" disabled={busy} onClick={onClose}><X size={18}/></button></header>
    <section className="project-folder-current"><small>CURRENT PROJECT</small><strong>{project?.name||'Current project'}</strong><code>{project?.path||'Project folder unavailable'}</code><p>This folder holds the project’s database, imports, exports, and logs. Recordings imported by path can live elsewhere.</p>{onFiles&&<button disabled={busy} onClick={()=>{onClose();onFiles();}}>View project files</button>}</section>
    <form onSubmit={open}><h3>Open another project folder</h3><label htmlFor="existing-project-folder">Existing project folder</label><input id="existing-project-folder" required value={directory} disabled={busy} onChange={event=>setDirectory(event.target.value)} placeholder="/absolute/path/to/project" aria-describedby="project-folder-help"/><p id="project-folder-help">Paste the full path to the folder containing project.json and catalog.json, not its parent workspace. Opening switches projects; it does not move or copy your data.</p>{error&&<p className="project-folder-error" role="alert">{error}</p>}<footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary" disabled={busy||!directory.trim()}>{busy?<><LoaderCircle size={14} className="spin"/> Opening project…</>:<>Open project folder</>}</button></footer></form>
  </dialog>,document.body);
}
