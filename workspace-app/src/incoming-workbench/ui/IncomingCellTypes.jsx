import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {incomingCellTypes} from '../incomingCellTypes.js';
import {cellTypeColor} from "../../cell-qc/cellTypes.js";
import {number} from '../../api.js';
import NeuronIcon from '../../components/NeuronIcon.jsx';

export default function IncomingCellTypes({cells,count,scope='Frozen proposal',compact=false,trigger}){
  const [open,setOpen]=useState(false),[position,setPosition]=useState({left:0,width:240,maxHeight:240,above:false});
  const root=useRef(null),button=useRef(null),pinned=useRef(false),suppressFocus=useRef(false),id=useId();
  function close(){pinned.current=false;setOpen(false);}
  useLayoutEffect(()=>{
    if(!open||!root.current)return;
    function place(){
      const rect=root.current.getBoundingClientRect(),width=Math.min(240,window.innerWidth-24);
      const below=window.innerHeight-rect.bottom,above=below<180&&rect.top>below;
      setPosition({left:Math.max(12,Math.min(rect.left,window.innerWidth-width-12))-rect.left,width,
        maxHeight:Math.max(0,Math.min(240,(above?rect.top:below)-20)),above});
    }
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
  },[open]);
  useEffect(()=>{
    if(!open)return;
    function outside(event){if(!root.current?.contains(event.target))close();}
    function escape(event){if(event.key!=='Escape')return;event.preventDefault();close();
      if(root.current?.contains(document.activeElement)){suppressFocus.current=true;button.current?.focus();suppressFocus.current=false;}}
    document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',escape,true);
    return()=>{document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',escape,true);};
  },[open]);
  const groups=incomingCellTypes(cells,count);
  const chips=groups?.map(({type,count})=><span className="incoming-type-chip" key={type} role="listitem" tabIndex={0} style={{'--type-color':cellTypeColor(type)}}><NeuronIcon size={13}/><strong>{number(count)}</strong> {type.replace(/^RGC\\/i,'')}</span>);
  const content=<div className={`incoming-cell-types ${compact?'compact':''}`} role="group" aria-label={`${scope} cell types`}>
    {(compact||trigger)&&<span className="incoming-type-summary">{scope} · {groups===null?'unavailable':`${number(count)} ${count===1?'cell':'cells'}`}</span>}
    <div className="incoming-type-chips" role="list" aria-label={`${scope} recorded type counts`}>{groups===null?<span role="listitem">Types unavailable</span>:groups.length?chips:<span role="listitem">0 cells</span>}</div>
  </div>;
  if(!trigger)return content;
  return <div ref={root} className="incoming-cell-type-overview"
    onPointerEnter={event=>{if(event.pointerType!=='touch')setOpen(true);}}
    onPointerLeave={()=>{if(!pinned.current&&!root.current?.contains(document.activeElement))close();}}
    onFocus={event=>{if(!suppressFocus.current&&!event.currentTarget.contains(event.relatedTarget))setOpen(true);}}
    onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))close();}}>
    <button ref={button} type="button" className="incoming-cell-type-trigger" aria-description="Show the recorded cell-type breakdown" aria-expanded={open} aria-controls={id}
      onClick={()=>{if(pinned.current)close();else{pinned.current=true;setOpen(true);}}}>{trigger}</button>
    {open&&<div id={id} className={`incoming-cell-type-card ${position.above?'above':''}`} style={{left:position.left,width:position.width}}>
      <div className="incoming-cell-type-card-body" style={{maxHeight:position.maxHeight}}><strong className="incoming-cell-type-title">Cell types</strong>{content}</div>
    </div>}
  </div>;
}
