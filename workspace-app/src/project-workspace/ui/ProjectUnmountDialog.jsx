import {useState} from 'react';
import {LoaderCircle,LogOut} from 'lucide-react';
import ProjectSetupDialog from './ProjectSetupDialog.jsx';
import {api} from '../../api.js';
import {unmountProject} from '../../projectUnmount.js';
import './ProjectUnmountDialog.css';

export default function ProjectUnmountDialog({project,pending,launcherUrl,onClose,onUnmount,saveView}){
 const [working,setWorking]=useState(false),[error,setError]=useState(''),[closed,setClosed]=useState(null),[paused,setPaused]=useState(null);
 async function confirm(){
  if(working)return;setWorking(true);setError('');
  try{const result=await unmountProject({project,request:api,busy:pending,retryClosed:!!paused,launcherUrl,saveView});onUnmount(result);}
  catch(error){setError(error.message);if(error.data?.state==='closed')setClosed(error.data);if(error.data?.close_unconfirmed)setPaused(error.data);setWorking(false);}
 }
 return <ProjectSetupDialog label="Unmount project" busy={working||!!closed||!!paused} onClose={onClose}>
  <section className="project-unmount"><h2>Unmount {project.name}?</h2><p>Remove this project from your project list. All files, recordings, database, annotations, exports and backups are retained.</p>
   <code>{project.path}</code>
   <p>{project.current?'The project will close safely. Your current workspace view is saved in this browser. ':''}Remount with <strong>Open a project</strong> and choose this folder.</p>
   {!project.available&&<p>Folder unavailable. This removes its saved reference; no drive access is required.</p>}
   {pending&&<p role="status">Wait for the current import or project operation to finish.</p>}
   {error&&<p className="project-unmount-error" role="alert">{error}</p>}
   {paused&&<p role="status">Unmount is unverified; changes remain paused. Retry after checking its log.</p>}
   <footer>{closed?<button onClick={()=>onUnmount(closed)}>Return to projects</button>:paused?<><button disabled={working||!paused.launcher_url} onClick={()=>onUnmount(paused)}>Return to projects</button><button disabled={working} onClick={confirm}>Retry unmount</button></>:<><button autoFocus disabled={working} onClick={onClose}>Cancel</button><button disabled={working||pending} onClick={confirm}>{working?<LoaderCircle size={14} className="spin"/>:<LogOut size={14}/>} {working?'Unmounting…':'Unmount project'}</button></>}</footer>
  </section>
 </ProjectSetupDialog>;
}
