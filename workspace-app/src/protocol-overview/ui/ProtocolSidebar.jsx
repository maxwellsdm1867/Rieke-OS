import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowUp, ArrowDown, ChevronRight, GripVertical, Pin, PinOff, Settings2, Archive, Undo2, Pencil } from 'lucide-react';
import { api, humanize } from "../../api.js";
import { moveShortcut,moveProtocolPreference,protocolShortcutGroups,protocolShortcutSection } from "../../ordering.js";
import { startPointerDrag } from "../../pointerDrag.js";
import './ProtocolSidebar.css';
import {pendingReviewBadge} from "../../incoming-workbench/incomingReview.js";
import {useProjectPreference} from "../../project-preferences/useProjectPreference.js";

const sectionNames = { pinned: 'Pinned', main: 'Protocols', support: 'Typing & backtracking' };
export default function ProtocolSidebar({ projectId, protocols, activeId, onNavigate, suggestions=[],workbenchCounts=[],suggestionsError,onRetrySuggestions, onChanged }) {
  const projectPreferences=useProjectPreference(projectId,'protocol_shortcuts');
  const preferences=projectPreferences.value;
  const [organizing, setOrganizing] = useState(false);
  const [openSections, setOpenSections] = useState({pinned:true,main:true,support:false});
  const [renaming,setRenaming]=useState(null),[renameBusy,setRenameBusy]=useState(false),[renameError,setRenameError]=useState('');
  const [dragging, setDragging] = useState(null);
  const [dropSpot, setDropSpot] = useState(null);
  const [announcement, setAnnouncement] = useState('');
  const cancelDrag = useRef(null), currentGroups=useRef(null),helpId = useId();
  useEffect(()=>()=>cancelDrag.current?.(),[]);
  const handles=useRef(new Map()),focusAfterMove=useRef(null);
  useEffect(()=>{
    if(focusAfterMove.current){handles.current.get(focusAfterMove.current)?.focus();focusAfterMove.current=null;}
  },[preferences]);
  useEffect(() => {
    setOpenSections({pinned:true,main:true,support:false});setRenaming(null);setRenameError('');
    setDragging(null);setDropSpot(null);cancelDrag.current?.();cancelDrag.current=null;focusAfterMove.current=null;
  }, [projectId]);
  const section = p => protocolShortcutSection(p,preferences);
  const groups=useMemo(()=>protocolShortcutGroups(protocols,preferences),[protocols,preferences]);
  const byId=new Map(protocols.map(protocol=>[protocol.protocol_uuid,protocol]));
  const grouped=Object.fromEntries(Object.entries(groups).map(([section,ids])=>[section,ids.map(id=>byId.get(id))]));
  currentGroups.current=groups;
  function commitMove(sourceId, target, targetId=null, placement='before') {
    if(projectPreferences.loading)return;
    const before=currentGroups.current;
    const nextGroups=moveShortcut(before,sourceId,target,targetId,placement);
    if(nextGroups===before)return;
    focusAfterMove.current=sourceId;
    projectPreferences.update(previous=>moveProtocolPreference(previous,protocols,sourceId,target,targetId,placement)).catch(()=>{});
    const name=humanize(protocols.find(p=>p.protocol_uuid===sourceId)?.name || 'Protocol');
    setAnnouncement(`${name} moved to ${sectionNames[target]}, position ${nextGroups[target].indexOf(sourceId)+1}.`);
  }
  function reorder(items,index,direction) {
    if(index+direction<0 || index+direction>=items.length)return;
    commitMove(items[index].protocol_uuid,section(items[index]),items[index+direction].protocol_uuid,direction>0?'after':'before');
  }
  function clearDrag() {cancelDrag.current?.();cancelDrag.current=null;setDragging(null);setDropSpot(null);}
  function pointerStart(event,p) {
    cancelDrag.current?.();
    const root=event.currentTarget.closest('.protocol-shortcuts');
    function targetAt(event) {
      const hit=root?.ownerDocument.elementFromPoint(event.clientX,event.clientY);
      if(!hit || !root.contains(hit))return null;
      const section=hit.closest('[data-shortcut-section]');
      if(!section || !root.contains(section))return null;
      const row=hit.closest('[data-protocol-shortcut]');
      if(!row)return {group:section.dataset.shortcutSection,id:null,placement:'before'};
      const box=row.getBoundingClientRect();
      return {group:section.dataset.shortcutSection,id:row.dataset.protocolShortcut,
        placement:event.clientY<box.top+box.height/2?'before':'after'};
    }
    cancelDrag.current=startPointerDrag(event,{
      getTarget:targetAt,onStart:()=>setDragging(p.protocol_uuid),
      onTarget:target=>setDropSpot(previous=>previous?.group===target?.group&&previous?.id===target?.id&&previous?.placement===target?.placement?previous:target),
      onDrop:target=>commitMove(p.protocol_uuid,target.group,target.id,target.placement),
      onCancel:()=>setAnnouncement('Reordering cancelled. Your shortcuts are unchanged.'),
      onFinish:()=>{cancelDrag.current=null;setDragging(null);setDropSpot(null);},
    });
  }
  async function rename(event) {
    event.preventDefault();if(renameBusy||!renaming?.name.trim())return;
    setRenameBusy(true);setRenameError('');
    try {
      await api(`/protocols/${renaming.id}/display-name`,{method:'POST',body:{name:renaming.name.trim(),expected_name:renaming.original}});
      setRenaming(null);onChanged?.();
    } catch(error) {setRenameError(error.message);} finally {setRenameBusy(false);}
  }
  function rows(items) {
    return items.map((p,index)=>{
      const name=humanize(p.name),group=section(p),id=p.protocol_uuid;
      const suggestion=suggestions.find(item=>item.protocol_uuid===id);
      const reviewSummary=workbenchCounts.find(item=>item.protocol_uuid===id),reviewBadge=pendingReviewBadge(suggestion,reviewSummary);
      return <div className={`protocol-shortcut ${dragging===id?'shortcut-drag-source':''} ${dragging&&dropSpot?.id===id&&dragging!==id?`shortcut-drop-${dropSpot.placement}`:''}`} key={id}
        data-protocol-shortcut={id}>
        <div className="shortcut-mainline">
          {organizing&&<button className="shortcut-drag-handle" ref={node=>{if(node)handles.current.set(id,node);else handles.current.delete(id);}} onPointerDown={event=>pointerStart(event,p)}
            aria-label={`Reorder ${name}`} aria-describedby={helpId} title="Drag to reorder or change section · Alt + ↑ / ↓"
            onKeyDown={event=>{if(event.altKey&&['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();reorder(items,index,event.key==='ArrowUp'?-1:1);}}}><GripVertical size={14}/></button>}
          <button className={`nav-item protocol-nav ${activeId===id?'active':''}`} onClick={()=>onNavigate(id)} aria-current={activeId===id?'page':undefined} title={name}>
            {group==='pinned'?<Pin size={12}/>:<span className="nav-protocol-dot"/>}<span>{name}</span>{reviewBadge&&<small className="shortcut-update-badge" title="Distinct incoming cells awaiting review in the authoritative cumulative queue. Open Workbench to review. If the count is unavailable, a generic Review notice is shown.">{reviewBadge}</small>}
          </button>
        </div>
        {renaming?.id===id&&<form className="shortcut-rename" onSubmit={rename}>
          <input aria-label="Pinned protocol name" maxLength={120} value={renaming.name} disabled={renameBusy} onChange={event=>setRenaming(value=>({...value,name:event.target.value}))}/>
          <button disabled={renameBusy||!renaming.name.trim()}>Save</button><button type="button" disabled={renameBusy} onClick={()=>{setRenaming(null);setRenameError('');}}>Cancel</button>
          {renameError&&<p role="alert">{renameError}</p>}
        </form>}
        {organizing&&<div className="protocol-shortcut-actions" role="group" aria-label={`Organize ${name}`}>
          {group==='pinned'&&<button disabled={renameBusy} title="Rename pinned protocol" aria-label={`Rename ${name}`} onClick={()=>{setRenaming({id,name:p.name,original:p.name});setRenameError('');}}><Pencil size={13}/></button>}
          <button title={group==='pinned'?'Unpin':'Pin to top'} aria-label={`${group==='pinned'?'Unpin':'Pin'} ${name}`} onClick={()=>commitMove(id,group==='pinned'?'main':'pinned')}>{group==='pinned'?<PinOff size={13}/>:<Pin size={13}/>}</button>
          <button title={group==='support'?'Show in protocols':'Move to typing & backtracking'} aria-label={`${group==='support'?'Show':'Tuck away'} ${name}`} onClick={()=>commitMove(id,group==='support'?'main':'support')}>{group==='support'?<Undo2 size={13}/>:<Archive size={13}/>}</button>
          <button title="Move up" aria-label={`Move ${name} up`} disabled={index===0} onClick={()=>reorder(items,index,-1)}><ArrowUp size={13}/></button>
          <button title="Move down" aria-label={`Move ${name} down`} disabled={index===items.length-1} onClick={()=>reorder(items,index,1)}><ArrowDown size={13}/></button>
        </div>}
      </div>;
    });
  }
  function sectionRows(group) {
    const items=grouped[group];
    if(!organizing&&!items.length)return null;
    const revealed=organizing||openSections[group];
    return <div className={`shortcut-section ${organizing?'shortcut-section-organizing':''} ${dragging&&dropSpot?.group===group&&!dropSpot.id?'shortcut-section-target':''}`}
      role="group" aria-label={`${sectionNames[group]} shortcuts`} key={group}
      data-shortcut-section={group}>
      <button className="support-toggle" aria-expanded={revealed} aria-label={`${sectionNames[group]} section`} onClick={()=>setOpenSections(value=>({...value,[group]:!value[group]}))} disabled={organizing}>
        <ChevronRight size={13} className={revealed?'expanded':''}/><span>{sectionNames[group]}</span><small>{items.length}</small>
      </button>
      {revealed&&rows(items)}
      {organizing&&!items.length&&<div className="shortcut-empty-drop">Drop a protocol here</div>}
    </div>;
  }
  return <section className={`protocol-shortcuts ${organizing?'is-organizing':''}`} aria-label="Protocol shortcuts"
    onKeyDown={event=>{if(event.key==='Escape'&&dragging){event.preventDefault();clearDrag();setAnnouncement('Reordering cancelled.');}}}>
    <div className="nav-label protocol-shortcuts-heading"><span>PROTOCOLS</span><button onClick={()=>{setOrganizing(value=>!value);clearDrag();}} aria-label={organizing?'Done organizing protocols':'Organize protocols'} aria-pressed={organizing} title="Pin, reorder or tuck away protocols">{organizing?'Done':<Settings2 size={14}/>}</button></div>
    {organizing&&<p className="shortcut-hint">Drag handles to reorder or move between sections. Saved with this project.</p>}
    <p id={helpId} className="shortcut-visually-hidden">Drag a handle to move a protocol. Use Alt and up or down arrow to reorder, or use the pin, section, and move buttons.</p>
    <div className="shortcut-visually-hidden" role="status" aria-live="polite">{announcement}</div>
    {['pinned','main','support'].map(sectionRows)}
    {suggestionsError&&<p className="shortcut-hint" role="alert">Update suggestions unavailable. <button onClick={onRetrySuggestions}>Retry</button></p>}
    {projectPreferences.loading&&!projectPreferences.error&&<p className="shortcut-hint" role="status">Loading project shortcuts…</p>}
    {projectPreferences.error&&<p className="shortcut-hint" role="status">{projectPreferences.error} <button onClick={()=>projectPreferences.update(previous=>previous).catch(()=>{})}>Retry</button></p>}
  </section>;
}
