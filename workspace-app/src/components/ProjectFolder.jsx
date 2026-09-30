import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Activity,ArrowRight,Check,CheckCircle2,ChevronRight,Clock3,Copy,Database,Download,Files,FolderOpen,LoaderCircle,LogOut,Package,PackageOpen,Search,ShieldCheck,Tags,X} from 'lucide-react';
import {api} from '../api.js';
import {flushDesktopDrafts} from '../desktopLifecycle.js';
import {inspectAndOpenProject,localProjectUrl,runProjectTransfer} from '../projectTransfer.js';
import './ProjectFolder.css';
import FolderPathInput from './FolderPathInput.jsx';

const tasks=[{mode:'open',label:'Open',icon:FolderOpen},{mode:'prepare',label:'Share',icon:Package},{mode:'restore',label:'Receive',icon:PackageOpen}];
const contents=[{label:'Recordings',icon:Activity},{label:'Database',icon:Database},{label:'Saved queries',icon:Search},{label:'Tags',icon:Tags},{label:'History',icon:Clock3},{label:'Exports',icon:Download}];

export default function ProjectFolder({project,onClose,onFiles,initialMode='open',initialDirectory,initialInspection,onTransferComplete,preferredRoot}){
  const dialog=useRef(null),requestController=useRef(null);
  const [mode,setMode]=useState(initialMode);
  const [openPath,setOpenPath]=useState(initialMode==='open'?initialDirectory||'':''),[copied,setCopied]=useState(false),[relocate,setRelocate]=useState(false),[movePath,setMovePath]=useState('');
  const [directory,setDirectory]=useState(initialDirectory||(initialMode==='restore'?'':project?.path||''));
  const [destination,setDestination]=useState(''),[inspection,setInspection]=useState(initialInspection||null);
  const [rootSuggestions,setRootSuggestions]=useState(null);
  const [working,setBusy]=useState(false),[browsing,setBrowsing]=useState(false),[opening,setOpening]=useState(false),[closing,setClosing]=useState(false),[checking,setChecking]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null);
  const busy=working||browsing;
  const migrating=mode==='migrate', availableMigration=inspection?.desktop_compatibility?.migration_available===true;
  const visibleTasks=migrating?[...tasks,{mode:'migrate',label:'Desktop copy',icon:Copy}]:tasks;
  useEffect(()=>{const element=dialog.current;element.showModal();return()=>{requestController.current?.abort();element.close();};},[]);
  function chooseMode(next){
    setMode(next);setDirectory(next==='prepare'?project?.path||initialDirectory||'':'');setDestination('');setError('');setResult(null);setInspection(null);setRootSuggestions(null);
  }
  function chooseRoot(path){
    if(mode==='open')setOpenPath(path);else setDirectory(path);
    setRootSuggestions(null);setInspection(null);setResult(null);setDestination('');setError('');
  }
  async function openDirectory(path,{allowRelocate=true}={}){
    setBusy(true);setOpening(true);setError('');setRootSuggestions(null);
    try{
      await flushDesktopDrafts();
      const response=await inspectAndOpenProject({directory:path,request:api,relocateDestination:allowRelocate&&relocate?movePath.trim():undefined});
      if(response.action==='choose-root'){
        setRootSuggestions(response.inspection);setBusy(false);setOpening(false);return;
      }
      if(response.action==='migrate'){
        setMode('migrate');setDirectory(path);setDestination('');setResult(null);setInspection(response.inspection);setBusy(false);setOpening(false);return;
      }
      if(response.action==='restore'){
        setMode('restore');setDirectory(path);setDestination('');setResult(null);setInspection(response.inspection);setBusy(false);setOpening(false);
        return;
      }
      setOpenPath(response.directory);setRelocate(false);
      window.location.assign(localProjectUrl(response.url,window.location.href));
    }catch(error){setError(error.message);setBusy(false);setOpening(false);}
  }
  async function checkReceived(){
    if(busy||!directory.trim())return;
    setBusy(true);setChecking(true);setError('');setInspection(null);setRootSuggestions(null);
    try{
      const response=await api('/projects/inspect-folder',{method:'POST',body:{directory:directory.trim()}});
      if(response.kind==='project-root-suggestions'){setRootSuggestions(response);return;}
      if(response.valid!==true)throw new Error('The folder did not pass inspection.');
      if(response.kind!=='prepared-transfer')throw new Error('This is a working project folder. Use the Open tab.');
      setInspection(response);
    }catch(error){setError(error.message);}finally{setBusy(false);setChecking(false);}
  }
  async function closeProject(){
    if(busy)return;
    setBusy(true);setClosing(true);setError('');
    try{
      await flushDesktopDrafts();
      const response=await api('/project/close',{method:'POST',body:{}});
      if(response.state!=='closed')throw new Error('The project did not confirm a clean close. Keep its folder in place.');
      const launcher=new URL(localProjectUrl(response.launcher_url,window.location.href));if(project?.path)launcher.searchParams.set('closed_project',project.path);window.location.assign(launcher.href);
    }catch(error){setError(error.message);setBusy(false);setClosing(false);}
  }
  async function submit(event){
    event.preventDefault();if(busy||!directory.trim()||!destination.trim()||(mode==='restore'&&!inspection))return;
    setBusy(true);setError('');setResult(null);
    try{
      requestController.current=new AbortController();
      const response=await runProjectTransfer({mode,directory:directory.trim(),destination:destination.trim(),request:api,signal:requestController.current.signal});
      setResult(response);onTransferComplete?.({mode,...response});
    }catch(error){setError(`${error.message} Check the destination before retrying an interrupted transfer.`);}
    finally{setBusy(false);}
  }
  async function copyPath(){
    try{await navigator.clipboard.writeText(project.path);setCopied(true);}catch{setError('Could not copy the path. Select the folder path and copy it.');}
  }
  function tabKeys(event,index){
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)||busy)return;
    event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?visibleTasks.length-1:(index+(event.key==='ArrowRight'?1:-1)+visibleTasks.length)%visibleTasks.length;
    chooseMode(visibleTasks[next].mode);dialog.current?.querySelector(`#project-task-${visibleTasks[next].mode}`)?.focus();
  }
  const preparing=mode==='prepare',needsClose=preparing&&project?.database_kind==='native-mysql'&&directory.trim()===project.path;
  const progress=closing?'Closing project…':checking?'Checking portable copy…':opening?'Opening project…':preparing?'Preparing and verifying copy…':migrating?'Creating and verifying desktop copy…':'Restoring and verifying project…';
  return createPortal(<dialog ref={dialog} className="project-folder-dialog" aria-labelledby="project-folder-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
    <header><div className="project-folder-heading"><span className="project-folder-symbol"><FolderOpen size={23}/></span><div><small>PROJECTS</small><h2 id="project-folder-title">Project folder</h2></div></div><button autoFocus className="icon-button" aria-label="Close project folders" disabled={busy} onClick={onClose}><X size={18}/></button></header>
    {project&&<section className="project-folder-current" aria-label="Current project"><span className="project-folder-current-icon"><FolderOpen size={20}/></span><div className="project-folder-current-info"><strong>{project.name||'Current project'}</strong><span className="project-folder-state"><i/>Open here</span><code>{project.path||'Folder unavailable'}</code></div><div className="project-folder-current-actions">{project.path&&<button className="icon-button" onClick={copyPath} disabled={busy} aria-label={copied?'Project path copied':'Copy project path'} title={copied?'Copied':'Copy path'}>{copied?<Check size={15}/>:<Copy size={15}/>}</button>}{onFiles&&<button className="icon-button" disabled={busy} title="View project files" aria-label="View project files" onClick={()=>{onClose();onFiles();}}><Files size={16}/></button>}{project.database_kind==='native-mysql'&&!needsClose&&<button disabled={busy} onClick={closeProject}><LogOut size={14}/> Close project</button>}</div></section>}
    <nav className="project-folder-tabs" role="tablist" aria-label="Project action">{visibleTasks.map(({mode:value,label,icon:Icon},index)=><button key={value} id={`project-task-${value}`} role="tab" aria-selected={mode===value} aria-controls="project-folder-task" tabIndex={mode===value?0:-1} disabled={busy} onKeyDown={event=>tabKeys(event,index)} onClick={()=>chooseMode(value)}><Icon size={19}/><span>{label}</span></button>)}</nav>
    <section id="project-folder-task" className="project-folder-task" role="tabpanel" aria-labelledby={`project-task-${mode}`}>
      <div className="project-folder-task-title"><h3>{mode==='open'?'Add a project':preparing?'Make a portable copy':migrating?'Create a desktop copy':'Receive a portable copy'}</h3><p>{mode==='open'?'Browse to its top folder, wherever it lives.':preparing?'Everything your colleague needs, in one folder.':migrating?'This project uses an older database setup. Choose a separate folder for a copy that runs with the desktop app’s built-in database.':'Check the received top folder, then restore locally.'}</p></div>
      {migrating&&<p className="project-folder-warning">The original project and database stay in place. Docker is only used to read the existing source database during copying; the desktop copy runs without Docker. {availableMigration?'The existing source database must be running, with its project session closed.':'Prepare a portable copy in the source installation, then use Receive here.'}</p>}
      {mode!=='open'&&<div className="project-folder-contents" aria-label="Portable project contents">{contents.map(({label,icon:Icon})=><span key={label} title={label==='Saved queries'?'Protocols, saved searches and layouts':label}><Icon size={19}/><small>{label}</small></span>)}</div>}
      {mode==='open'?<form onSubmit={event=>{event.preventDefault();if(!busy&&openPath.trim()&&(!relocate||movePath.trim()))openDirectory(openPath.trim());}}>
        <label htmlFor="open-project-path">Top project folder</label><FolderPathInput id="open-project-path" required value={openPath} disabled={busy} onChange={value=>{setOpenPath(value);setError('');setRootSuggestions(null);}} onBusyChange={setBrowsing} purpose="existing" title="Open project folder" placeholder="/Users/you/Research/Spike response study"/><small className="project-folder-input-hint">Usually named for your project, with the project files directly inside. Choose this folder, not its parent or an inner folder.</small>
        <details className="project-folder-organize"><summary>Optional: move before opening <ChevronRight size={13}/></summary><label className="project-folder-checkbox"><input type="checkbox" checked={relocate} disabled={busy} onChange={event=>{setRelocate(event.target.checked);if(event.target.checked&&!movePath&&preferredRoot&&openPath.trim())setMovePath(`${preferredRoot.replace(/\/$/,'')}/${openPath.trim().replace(/\/$/,'').split('/').pop()}`);}}/> Move to another folder</label>{relocate&&<><label htmlFor="project-move-path">New folder</label><FolderPathInput id="project-move-path" required value={movePath} disabled={busy} onChange={setMovePath} onBusyChange={setBrowsing} purpose="new" title="Move destination" suggestedName={openPath.trim().replace(/\/$/,'').split('/').pop()} placeholder={preferredRoot?`${preferredRoot}/my-project`:'/absolute/path/to/new-folder'}/><small>Closed projects only · destination must be new · same disk</small></>}</details>
        <footer><span><ShieldCheck size={14}/> Checked before opening</span><button type="submit" className="primary" disabled={busy||!openPath.trim()||(relocate&&!movePath.trim())}>{relocate?'Move & open':'Open project'}<ArrowRight size={15}/></button></footer>
      </form>:result?<section className="project-folder-success" role="status"><span className="project-folder-result-icon"><CheckCircle2 size={28}/></span><strong>{preparing?'Portable copy ready':migrating?'Desktop copy ready':'Project restored'}</strong><code>{result.directory}</code><p>{preparing?'Send this entire folder → recipient chooses Add new project.':migrating?'Verified copy ready. The original project and source database are unchanged.':'Recordings, saved work and history are ready.'}</p>{result.registry_warning&&<p className="project-folder-warning">{result.registry_warning}</p>}{!preparing&&<button className="primary" disabled={busy} onClick={()=>openDirectory(result.directory,{allowRelocate:false})}>{migrating?'Open desktop copy':'Open restored project'} <ArrowRight size={15}/></button>}</section>:<form onSubmit={submit} aria-busy={busy}>
        <label htmlFor="existing-project-folder">{preparing?'Top project folder to share':migrating?'Original project folder':'Received top folder'}</label><div className="project-folder-input-row"><FolderPathInput id="existing-project-folder" required value={directory} disabled={busy||migrating} onChange={value=>{setDirectory(value);setResult(null);setInspection(null);setError('');setRootSuggestions(null);}} onBusyChange={setBrowsing} purpose="existing" title={preparing?'Project folder to share':'Received portable copy'} placeholder="/absolute/path/to/project"/>{!preparing&&!migrating&&<button type="button" disabled={busy||!directory.trim()||!!inspection} onClick={checkReceived}><ShieldCheck size={15}/>{inspection?'Checked':'Check copy'}</button>}</div>
        {needsClose&&<div className="project-folder-close-note"><LogOut size={16}/><span>Close this project before sharing.</span><button type="button" disabled={busy} onClick={closeProject}>Close project<ArrowRight size={14}/></button></div>}
        {inspection&&<div className="project-folder-inspection" role="status"><span className="project-folder-inspection-icon"><ShieldCheck size={21}/></span><div><strong>{inspection.project?.name||'Project'}</strong><span><Check size={13}/> Files verified{Number.isFinite(inspection.source_count)?` · ${inspection.source_count} recording${inspection.source_count===1?'':'s'}`:''}</span></div></div>}
        {inspection?.warnings?.map((warning,index)=><p key={index} className="project-folder-warning">{warning}</p>)}
        {((preparing&&!needsClose)||(!migrating&&inspection)||(migrating&&availableMigration))&&<><label htmlFor="project-transfer-destination">{preparing?'Portable copy destination':migrating?'New desktop project folder':'New local project folder'}</label><FolderPathInput id="project-transfer-destination" required value={destination} disabled={busy} onChange={value=>{setDestination(value);setResult(null);}} onBusyChange={setBrowsing} purpose="new" title={preparing?'Portable copy destination':migrating?'New desktop project folder':'Restored project folder'} suggestedName={preparing?`${directory.trim().replace(/\/$/,'').split('/').pop()||'Project'} shared`:inspection?.project?.name} placeholder="/absolute/path/to/new-folder"/><small className="project-folder-input-hint">Browse to its parent folder, then name the new folder.</small><footer><span><ShieldCheck size={14}/>{preparing?'Verification included':'Verified on restore'}</span><button type="submit" className="primary" disabled={busy||needsClose||!directory.trim()||!destination.trim()}>{preparing?'Prepare copy':migrating?'Create desktop copy':'Restore project'}<ArrowRight size={15}/></button></footer></>}
      </form>}
      {rootSuggestions&&<div className="project-folder-root-suggestions" role="region" aria-label="Choose the project root"><p>{rootSuggestions.message||'Choose the folder containing the project files.'}</p>{rootSuggestions.candidates?.filter(candidate=>typeof candidate.path==='string').map(candidate=><button key={candidate.path} type="button" disabled={busy} onClick={()=>chooseRoot(candidate.path)}><FolderOpen size={20}/><span><strong>{candidate.name||'Project'}{candidate.kind==='prepared-transfer'&&<small>Portable copy</small>}</strong><code>{candidate.path}</code></span><span className="project-folder-use-root">Use this folder<ArrowRight size={14}/></span></button>)}</div>}
    </section>
    {working&&<div className="project-folder-progress" role="status"><LoaderCircle size={16} className="spin"/><span>{progress}<small>Keep this window open.</small></span></div>}
    {error&&<p className="project-folder-error" role="alert">{error}</p>}
    <div className="project-folder-bottom"><span>{copied?'Project path copied':'Your project · your files'}</span><button disabled={busy} onClick={onClose}>Done</button></div>
  </dialog>,document.body);
}
