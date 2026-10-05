import {useEffect,useId,useRef,useState} from 'react';
import {MoreHorizontal} from 'lucide-react';

export default function InspectorActions({actions,selectionHelp=true}){
  const [open,setOpen]=useState(false),root=useRef(null),trigger=useRef(null),id=useId();
  useEffect(()=>{
    if(!open)return;
    const outside=event=>{if(!root.current?.contains(event.target))setOpen(false);};
    const escape=event=>{if(event.key==='Escape'){event.preventDefault();setOpen(false);trigger.current?.focus();}};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
  },[open]);
  return <div ref={root} className="inspector-more" data-epoch-arrows="ignore" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setOpen(false);}}>
    <button ref={trigger} aria-expanded={open} aria-controls={id} onClick={()=>setOpen(value=>!value)}><MoreHorizontal size={16}/> More</button>
    {open&&<div id={id} className="inspector-more-panel" role="group" aria-label="More inspection actions">{actions.filter(Boolean).map(({label,icon:Icon,run,disabled})=><button key={label} disabled={disabled} onClick={()=>{setOpen(false);trigger.current?.focus();run();}}>{Icon&&<Icon size={15}/>} {label}</button>)}<div className="inspector-shortcuts"><strong>Epoch navigation</strong><span>Tab / Shift+Tab · next / previous</span><span>W / S · previous / next</span><small>In the epoch browser only. Fields keep normal typing and Tab behavior.</small>{selectionHelp&&<><strong>Tag multiple epochs</strong><span>⌘/Ctrl-click to toggle epochs; Shift-click to select a range, including across pages. Tags follow your selection in the right panel. Select a cell to edit its tags.</span></>}</div></div>}
  </div>;
}
