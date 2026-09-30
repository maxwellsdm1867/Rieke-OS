import {useEffect,useRef,useState} from 'react';
import {FolderOpen,LoaderCircle,RefreshCw,Plus,X} from 'lucide-react';
import {api} from '../api.js';
import {reorderIds} from '../ordering.js';
import {startPointerDrag} from '../pointerDrag.js';
import {orderedProjectRecords,projectKey} from '../projectNavigation.js';
import './ProjectNavigator.css';

function initials(name){
 const words=String(name||'').trim().split(/[\s_-]+/).filter(Boolean);
 return words.length>1?words.slice(0,3).map(word=>Array.from(word)[0]).join('').toUpperCase():Array.from(words[0]||'?').slice(0,3).join('').toUpperCase();
}
export function projectColor(){return {background:'hsl(274 35% 89%)',color:'hsl(274 30% 30%)'};}
function currentProject(projects,identity){return projects.find(project=>project.current)||projects.find(project=>project.uuid===identity);}
export function ProjectRail({projects=[],currentProjectUuid,onSelect,onAddProject,onReorder,loading=false,disabled=false}){
 const [order,setOrder]=useState(null),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const [dragging,setDragging]=useState(null),[dropSpot,setDropSpot]=useState(null),[announcement,setAnnouncement]=useState('');
 const visible=orderedProjectRecords(projects,order),ids=visible.map(projectKey);
 const currentIds=useRef(ids),cancelDrag=useRef(null),suppressClick=useRef(false);currentIds.current=ids;
 useEffect(()=>()=>cancelDrag.current?.(),[]);
 async function save(next){
  if(saving||disabled||next===currentIds.current)return;
  const before=order;setOrder(next);setSaving(true);setError('');
  try{const result=await api('/projects/order',{method:'POST',body:{paths:next}});setOrder(result.projects.map(projectKey));onReorder?.();setAnnouncement('Project order saved.');}
  catch(error){setOrder(before);setError(error.message);onReorder?.();}
  finally{setSaving(false);}
 }
 function pointerStart(event,project){
  suppressClick.current=false;cancelDrag.current?.();
  const root=event.currentTarget.closest('.project-rail-list'),source=projectKey(project);
  cancelDrag.current=startPointerDrag(event,{
   getTarget:event=>{const row=root.ownerDocument.elementFromPoint(event.clientX,event.clientY)?.closest('[data-project-path]');if(!row||!root.contains(row))return null;const box=row.getBoundingClientRect();return {id:row.dataset.projectPath,placement:event.clientY<box.top+box.height/2?'before':'after'};},
   onStart:()=>{suppressClick.current=true;setDragging(source);},onTarget:setDropSpot,
   onDrop:target=>save(reorderIds(currentIds.current,source,target.id,target.placement)),
   onCancel:()=>setAnnouncement('Reordering cancelled.'),onFinish:()=>{cancelDrag.current=null;setDragging(null);setDropSpot(null);},
  });
 }
 return <><nav className="project-rail-list" aria-label="Research projects">{visible.map((project,index)=>{
  const key=projectKey(project),active=(project.current??project.uuid===currentProjectUuid);
  return <button key={key} data-project-path={key} className={`project-rail-item ${active?'current':''} ${!project.available?'unavailable':''} ${dragging===key?'project-drag-source':''} ${dragging&&dropSpot?.id===key&&dragging!==key?`project-drop-${dropSpot.placement}`:''}`} title={`${project.name}${project.available?'':' · unavailable'}${project.path?'\n'+project.path:''}\nDrag to rearrange`} aria-label={`${project.name}${active?', current project':''}${project.available?'':', unavailable'}`} aria-description="Click to open. Drag to rearrange, or use Alt and Up or Down." aria-current={active?'page':undefined} disabled={disabled||saving||!project.available} onPointerDown={event=>pointerStart(event,project)} onKeyDown={event=>{if(event.altKey&&['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const target=ids[index+(event.key==='ArrowUp'?-1:1)];if(target)save(reorderIds(ids,key,target,event.key==='ArrowUp'?'before':'after'));}else if(['Enter',' '].includes(event.key))suppressClick.current=false;}} onClick={()=>{if(suppressClick.current){suppressClick.current=false;return;}if(!active)onSelect?.(project);}}><span style={projectColor()}>{initials(project.name)}</span></button>;
 })}{onAddProject&&<button className="project-rail-add" disabled={disabled||saving} onClick={onAddProject} title="Add project" aria-label="Add project"><Plus size={21}/></button>}{loading&&!projects.length&&<span className="project-rail-loading" role="status" aria-label="Loading projects"><LoaderCircle size={17} className="spin"/></span>}<span className="project-rail-status" role="status">{announcement}</span></nav>{error&&<div className="project-order-error" role="alert">Project order could not be saved: {error}<button onClick={()=>{setError('');onReorder?.();}} aria-label="Dismiss project order error"><X size={14}/></button></div>}</>;
}
export default function ProjectNavigator({projects=[],currentProjectUuid,loading=false,disabled=false,error=null,onRetry,onAddProject,onNewProject}){
 const current=currentProject(projects,currentProjectUuid);
 return <header className="project-navigator"><strong className="project-nav-title">{current?.name||(loading?'Loading projects…':'Choose a project')}</strong>{error&&<span className="project-nav-error" role="alert">Project list unavailable{onRetry&&<button onClick={onRetry} aria-label="Refresh project list"><RefreshCw size={14}/></button>}</span>}<div className="project-nav-actions" role="group" aria-label="Project actions">{onAddProject&&<button disabled={disabled} onClick={onAddProject} title="Open an existing project folder or a portable copy you received"><FolderOpen size={15}/> Add new project</button>}{onNewProject&&<button disabled={disabled} onClick={onNewProject} title="Create an empty project and its managed files"><Plus size={15}/> Start a brand new project</button>}</div></header>;
}
