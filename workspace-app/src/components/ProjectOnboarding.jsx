import {useEffect,useState} from 'react';
import {Activity,ArrowRight,Check,ChevronDown,Database,Download,FolderOpen,GitBranch,History,LoaderCircle,Plus,Folder,MapPin,Tags,X} from 'lucide-react';
import {api} from '../api.js';
import {projectColor} from './ProjectNavigator.jsx';
import './ProjectOnboarding.css';
import FolderPathInput from './FolderPathInput.jsx';

const folderName=path=>String(path||'').replace(/\/+$/,'').split('/').pop()||path;
const shortPath=path=>{const parts=String(path||'').split('/').filter(Boolean);return parts.length>2?`…/${parts.slice(-2).join('/')}`:path;};
const contents=[{Icon:Activity,label:'Recordings'},{Icon:Database,label:'Database'},{Icon:GitBranch,label:'Saved queries'},{Icon:Tags,label:'Tags'},{Icon:History,label:'History'},{Icon:Download,label:'Exports'}];
function ProjectContents({creating=false}){
  return <div className={`onboarding-contents ${creating?'is-preview':''}`} aria-label={creating?'Managed folders created automatically':'Contents that stay with your project'}>
    <span className="onboarding-contents-caption">{creating?<><Plus size={12} aria-hidden="true"/> Created automatically</>:<><Folder size={13} aria-hidden="true"/> Travels with your project</>}</span>
    <div>{contents.map(({Icon,label})=><span key={label}><Icon size={17} aria-hidden="true"/>{label}</span>)}</div>
  </div>;
}

export default function ProjectOnboarding({registry,onSelect,onCreated,onCancel,onWorkspaceChanged,onOpenProject,onNewProject,onBusyChange,createOnly=false,modal=false,titleId,loading=false,error=null}){
  const [creating,setCreating]=useState(createOnly),[name,setName]=useState(''),[directory,setDirectory]=useState(''),[working,setBusy]=useState(false),[browsing,setBrowsing]=useState(false),[failure,setFailure]=useState(''),[created,setCreated]=useState(null);
  const [selectedRegistry,setSelectedRegistry]=useState(null),[rootEditing,setRootEditing]=useState(false),[rootPath,setRootPath]=useState(registry?.managed_root||''),[rootMessage,setRootMessage]=useState('');
  const busy=working||browsing;
  const currentRegistry=selectedRegistry||registry;
  const projects=currentRegistry?.projects||[];
  const recent=projects.filter(item=>item.uuid===currentRegistry?.last_project_uuid),last=projects.find(item=>item.path===currentRegistry?.last_project_path)||(recent.length===1?recent[0]:null);
  useEffect(()=>{
    if(!onCancel||modal)return;
    function cancel(event){if(event.key==='Escape'&&!busy&&!loading){event.preventDefault();onCancel();}}
    document.addEventListener('keydown',cancel);
    return()=>document.removeEventListener('keydown',cancel);
  },[onCancel,busy,loading,modal]);
  useEffect(()=>{onBusyChange?.(busy||loading);},[busy,loading,onBusyChange]);
  useEffect(()=>{if(selectedRegistry&&registry?.managed_root===selectedRegistry.managed_root&&registry?.workspace_initialized===selectedRegistry.workspace_initialized)setSelectedRegistry(null);},[registry,selectedRegistry]);
  async function chooseRoot(event){
    event.preventDefault();if(busy||!rootPath.trim())return;setBusy(true);setFailure('');setRootMessage('');
    try{const result=await api('/workspace',{method:'POST',body:{directory:rootPath.trim()}});setSelectedRegistry(result);setRootPath(result.managed_root);setRootEditing(false);setCreating(false);setCreated(null);setRootMessage(`${result.projects.length} project${result.projects.length===1?'':'s'} available.`);onWorkspaceChanged?.();}
    catch(error){setFailure(error.message);}finally{setBusy(false);}
  }
  async function create(event){
    event.preventDefault();if(busy||!name.trim()||!directory.trim())return;
    setBusy(true);setFailure('');
    try{const result=await api('/projects',{method:'POST',body:{name:name.trim(),...(directory.trim()?{project_directory:directory.trim()}:{})}});if(!result.project?.uuid)throw new Error('The server did not return a project identity. Refresh the project list before retrying.');setCreated({...result.project,registry_warning:result.registry_warning});await onCreated?.(result.project);}
    catch(error){setFailure(error.message);}finally{setBusy(false);}
  }
  return <section className={`project-onboarding ${createOnly?'creation-only':''} ${modal?'project-onboarding-modal':''}`} aria-label="Project setup">
    <header><div><small>RIEKE OS</small><h1 id={titleId}>{created?'Project ready':creating?'New project':'Your projects'}</h1></div><img className="onboarding-app-icon" src="/rieke-os-icon.png" alt="Rieke OS app icon" title="Rieke OS" width="48" height="48"/>{onCancel&&<button className="icon-button" onClick={onCancel} disabled={busy||loading} aria-label="Close project setup"><X size={19}/></button>}</header>
    {(error||failure)&&<div className="onboarding-error" role="alert">{failure||error}</div>}
    {created?<div className="onboarding-created" role="status"><span className="onboarding-ready-icon"><Check size={25} aria-hidden="true"/></span><div><strong>{created.name}</strong><span title={created.path} aria-label={`Project folder: ${created.path}`}>{shortPath(created.path)}</span></div><p role={loading?'status':undefined}>{loading?<><LoaderCircle size={15} className="spin"/> Opening project…</>:'Ready to add recordings.'}</p>{created.registry_warning&&<p className="onboarding-registry-warning">{created.registry_warning}</p>}<div className="onboarding-actions"><button disabled={loading} className="primary" onClick={()=>onSelect?.(created)}>Open project <ArrowRight size={15}/></button>{!createOnly&&<button disabled={busy||loading} onClick={()=>{if(onCancel)onCancel();else{setCreated(null);setCreating(false);setFailure('');}}}>Cancel</button>}</div></div>:creating?<form className="onboarding-create-form" onSubmit={create}>
      <label><span className="onboarding-step-label"><b aria-hidden="true">1</b> Project name</span><small>Shown in the app</small><input autoFocus required maxLength={120} value={name} disabled={busy} onChange={event=>setName(event.target.value)} placeholder="Spike response study"/></label>
      <div className="onboarding-field"><label htmlFor="new-project-directory"><span className="onboarding-step-label"><b aria-hidden="true">2</b> Choose the top project folder</span><small>Browse to a new or empty folder, anywhere.</small></label><FolderPathInput id="new-project-directory" required value={directory} disabled={busy} onChange={setDirectory} onBusyChange={setBrowsing} purpose="create" title="New project folder" suggestedName={name.trim()} placeholder="/Users/you/Research/Spike response study"/><small>A matching folder name is easier to recognize; other names work too.</small></div>
      <div className="onboarding-folder-preview"><div className="onboarding-location"><FolderOpen size={21} aria-hidden="true"/><span><strong title={name.trim()||directory.trim()}>{name.trim()||folderName(directory.trim())||'Your project'}</strong><small title={directory.trim()} aria-label={directory.trim()?`Project folder: ${directory.trim()}`:undefined}>{directory.trim()?`Folder · ${shortPath(directory.trim())}`:'Choose a folder above'}</small></span></div><ProjectContents creating/></div>
      <footer><button type="button" disabled={busy||loading} onClick={()=>onCancel?onCancel():setCreating(false)}>Cancel</button><button type="submit" className="primary" disabled={busy||loading||!name.trim()||!directory.trim()}>{working?<><LoaderCircle size={15} className="spin"/> Creating project…</>:<>Create & open <ArrowRight size={15}/></>}</button></footer>
    </form>:<>
      <div className="onboarding-main-actions">{onOpenProject&&<button className="onboarding-action-card" disabled={loading||busy} onClick={onOpenProject}><span className="onboarding-action-icon"><FolderOpen size={27} aria-hidden="true"/></span><span><strong>Add new project</strong><small>Existing project root or portable copy</small></span><ArrowRight size={17} aria-hidden="true"/></button>}<button className="onboarding-action-card" disabled={loading||busy} onClick={()=>onNewProject?onNewProject():setCreating(true)}><span className="onboarding-action-icon"><Plus size={27} aria-hidden="true"/></span><span><strong>Start a brand new project</strong><small>Empty project</small></span><ArrowRight size={17} aria-hidden="true"/></button></div>
      <ProjectContents/>
      <div className="onboarding-list-heading"><h2>Your project roots</h2><span>{projects.length}</span></div>
      {loading&&<p className="onboarding-loading" role="status"><LoaderCircle size={15} className="spin"/> Opening project…</p>}
      <div className="onboarding-project-list">{projects.map(project=><button key={project.path||project.uuid} disabled={loading||!project.available} onClick={()=>onSelect?.(project)} aria-label={`${project.available?'Open':'Unavailable'} ${project.name}, ${project.path}`}><span className="onboarding-project-icon" style={projectColor(project.uuid)}><Folder size={21} aria-hidden="true"/></span><span className="onboarding-project-info"><strong>{project.name}{project.path===last?.path&&<em>Recent</em>}</strong><small title={project.path} aria-label={`Project folder: ${project.path}`}>{shortPath(project.path)}</small>{!project.available&&<small className="onboarding-unavailable">{project.unavailable_reason||'Needs attention before opening'}</small>}</span><ArrowRight className="onboarding-project-open" size={17} aria-hidden="true"/></button>)}</div>
      {!projects.length&&!loading&&<div className="onboarding-empty"><span><Folder size={25} aria-hidden="true"/><Plus size={12} aria-hidden="true"/></span><div><strong>No projects yet</strong><small>Choose a project root or start fresh above.</small></div></div>}
      <div className="onboarding-root"><MapPin size={15} aria-hidden="true"/>{registry?.launcher?<button className="onboarding-root-toggle" disabled={busy||loading} aria-expanded={rootEditing} aria-controls="onboarding-root-form" onClick={()=>{setRootPath(currentRegistry?.managed_root||'');setRootEditing(value=>!value);}}><span>Preferred location <small>Optional</small></span><strong title={currentRegistry?.managed_root}>{folderName(currentRegistry?.managed_root)||'Choose folder'}</strong><ChevronDown size={15} className={rootEditing?'expanded':''} aria-hidden="true"/></button>:<span title={currentRegistry?.managed_root}>Preferred location · {folderName(currentRegistry?.managed_root)||'Loading…'}</span>}</div>
      {rootEditing&&<form id="onboarding-root-form" className="onboarding-root-form" onSubmit={chooseRoot}><div className="onboarding-field"><label htmlFor="preferred-projects-directory">Preferred projects folder</label><FolderPathInput id="preferred-projects-directory" autoFocus value={rootPath} disabled={busy} onChange={setRootPath} onBusyChange={setBrowsing} purpose="existing" title="Preferred projects folder" placeholder="/absolute/path/to/research-workspace"/></div><button className="primary" disabled={busy||!rootPath.trim()}>{working?<><LoaderCircle size={14} className="spin"/> Checking…</>:'Use folder'}</button></form>}
      {rootMessage&&<p className="onboarding-root-message" role="status"><Check size={14} aria-hidden="true"/>{rootMessage}</p>}
    </>}
  </section>;
}
