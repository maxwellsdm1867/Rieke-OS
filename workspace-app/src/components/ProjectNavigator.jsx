import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,ChevronDown,FolderOpen,LoaderCircle,RefreshCw,Plus} from 'lucide-react';
import './ProjectNavigator.css';

function initials(name){
  const words=String(name || '').trim().split(/[\s_-]+/).filter(Boolean);
  return words.length>1?words.slice(0,3).map(word=>Array.from(word)[0]).join('').toUpperCase():Array.from(words[0] || '?').slice(0,3).join('').toUpperCase();
}
export function projectColor(identity){let hash=0;for(const char of String(identity||''))hash=(Math.imul(hash,31)+char.charCodeAt(0))|0;return {background:`hsl(${Math.abs(hash)%360} 32% 85%)`,color:`hsl(${Math.abs(hash)%360} 30% 25%)`};}
function currentProject(projects,identity){return projects.find(project=>project.uuid===identity) || projects.find(project=>project.current);}
export function ProjectRail({projects=[],currentProjectUuid,onSelect,onAddProject,loading=false,disabled=false}){
  return <nav className="project-rail-list" aria-label="Research projects">{projects.map(project=>{
    const active=project.uuid===currentProjectUuid;
    return <button key={project.uuid} className={`project-rail-item ${active?'current':''}`} title={`${project.name}${project.available?'':' · unavailable'}`} aria-label={`${project.name}${active?', current project':''}${project.available?'':', unavailable'}`} aria-current={active?'page':undefined} disabled={disabled||!project.available} onClick={()=>{if(!active)onSelect?.(project);}}><span style={projectColor(project.uuid)}>{initials(project.name)}</span></button>;
  })}{onAddProject&&<button className="project-rail-add" disabled={disabled} onClick={onAddProject} title="Add project" aria-label="Add project"><Plus size={21}/></button>}{loading&&!projects.length&&<span className="project-rail-loading" role="status" aria-label="Loading projects"><LoaderCircle size={17} className="spin"/></span>}</nav>;
}
export default function ProjectNavigator({projects=[],currentProjectUuid,onSelect,onAddProject,loading=false,disabled=false,error=null,onRetry}){
  const current=currentProject(projects,currentProjectUuid);
  const [open,setOpen]=useState(false),[active,setActive]=useState(0),[position,setPosition]=useState(null);
  const button=useRef(null),menu=useRef(null),listId=useId();
  function close(){setOpen(false);button.current?.focus();}
  function choose(project){if(!project?.available||disabled)return;if(project.uuid!==currentProjectUuid)onSelect?.(project);close();}
  function move(direction){
    const available=projects.map((project,index)=>project.available?index:null).filter(index=>index!==null);
    if(!available.length)return;
    const current=available.indexOf(active),next=current<0?(direction>0?0:available.length-1):(current+direction+available.length)%available.length;
    setActive(available[next]);
  }
  useEffect(()=>{setOpen(false);},[currentProjectUuid]);
  useEffect(()=>{
    if(!open)return;
    setActive(Math.max(0,projects.findIndex(project=>project.uuid===currentProjectUuid)));
    function place(){const box=button.current.getBoundingClientRect();const width=Math.min(365,window.innerWidth-24);setPosition({left:Math.max(12,Math.min(box.left,window.innerWidth-width-12)),top:box.bottom+7,width,maxHeight:Math.max(140,window.innerHeight-box.bottom-23)});}
    place();const click=event=>{if(!button.current?.contains(event.target)&&!menu.current?.contains(event.target))setOpen(false);};
    document.addEventListener('pointerdown',click);window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
    return()=>{document.removeEventListener('pointerdown',click);window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
  },[open]);
  useEffect(()=>{if(open&&position)menu.current?.querySelector('[role="listbox"]')?.focus();},[open,!!position]);
  useEffect(()=>{if(open)menu.current?.querySelector(`[data-project-index="${active}"]`)?.scrollIntoView({block:'nearest'});},[active,open]);
  return <div className="project-navigator"><button ref={button} className="project-navigator-trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls={open?listId:undefined} disabled={disabled} onKeyDown={event=>{if(event.key==='ArrowDown'){event.preventDefault();setOpen(true);}}} onClick={()=>setOpen(value=>!value)}><span className="project-nav-monogram" style={projectColor(current?.uuid)}>{current?initials(current.name):<FolderOpen size={18}/>}</span><span className="project-nav-label"><small>PROJECT</small><strong>{current?.name || (loading?'Loading projects…':'Choose project')}</strong></span>{loading?<LoaderCircle size={15} className="spin"/>:<ChevronDown size={15}/>}</button>
    {open&&position&&createPortal(<div ref={menu} className="project-navigator-menu" style={position} tabIndex={-1} onKeyDown={event=>{
      if(event.key==='Escape'){event.preventDefault();close();}
      else if(event.target.getAttribute('role')!=='listbox'){return;}
      else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();move(event.key==='ArrowDown'?1:-1);}
      else if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(projects[active]);}
      else if(event.key==='Tab'){button.current?.focus();setOpen(false);}
    }}><div className="project-menu-heading"><span>Research projects</span>{onRetry&&<button onClick={onRetry} disabled={loading} aria-label="Refresh project list"><RefreshCw size={13}/></button>}</div>
      {error&&<p className="project-menu-error" role="alert">{error}</p>}
      <div role="listbox" tabIndex={-1} id={listId} aria-label="Choose research project" aria-activedescendant={projects[active]?`${listId}-${active}`:undefined}>{projects.map((project,index)=><button id={`${listId}-${index}`} data-project-index={index} key={project.uuid} role="option" aria-selected={project.uuid===currentProjectUuid} aria-disabled={!project.available||disabled} tabIndex={-1} className={`project-menu-item ${active===index?'focused':''}`} onMouseMove={()=>setActive(index)} onClick={()=>choose(project)}><span className="project-nav-monogram" style={projectColor(project.uuid)}>{initials(project.name)}</span><span><strong>{project.name}</strong><small title={project.path}>{project.path}</small>{!project.available&&<em>{project.unavailable_reason || 'Project manifests unavailable'}</em>}</span>{project.uuid===currentProjectUuid&&<Check size={15}/>}</button>)}</div>
      {!projects.length&&!loading&&<p className="project-menu-empty">No validated recording projects were returned.</p>}{loading&&<p className="project-menu-empty" role="status">Checking project manifests…</p>}
      <p className="project-menu-note">{onAddProject&&<button className="project-menu-add" disabled={disabled} onClick={()=>{close();onAddProject();}}><Plus size={15}/> Add project</button>}Each project has its own catalog, protocol workspaces and activity.</p>
    </div>,document.body)}
  </div>;
}
