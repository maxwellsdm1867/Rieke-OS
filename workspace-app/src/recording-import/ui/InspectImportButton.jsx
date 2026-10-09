import {useId,useLayoutEffect,useRef,useState} from 'react';
import {ArrowRight,GitMerge} from 'lucide-react';

// Inspection and merge have distinct controls. A hold grants single-use merge
// intent; early release and the trailing click never inspect or merge.
export default function InspectImportButton({onInspect,onMerge,disabled=false,identity}){
  const hintId=useId(),timer=useRef(null),pressed=useRef(null),latest=useRef(null),[holding,setHolding]=useState(false);
  function clear(){clearTimeout(timer.current);timer.current=null;pressed.current=null;setHolding(false);}
  useLayoutEffect(()=>{latest.current={onMerge,disabled,identity};});
  useLayoutEffect(()=>{clear();return()=>{clearTimeout(timer.current);timer.current=null;pressed.current=null;latest.current=null;};},[identity,disabled,!!onMerge]);
  function start(event,key='pointer'){
    if(disabled||!onMerge||pressed.current||event.repeat||event.button!==undefined&&event.button!==0)return;
    pressed.current=key;setHolding(true);const owner=identity;
    timer.current=setTimeout(()=>{timer.current=null;if(!pressed.current||latest.current?.identity!==owner||latest.current?.disabled)return;setHolding(false);latest.current.onMerge?.();},1000);
  }
  return <>
    <button type="button" className="primary" disabled={disabled} onClick={()=>{clear();onInspect?.();}}>Inspect in Workbench <ArrowRight size={15}/></button>
    {onMerge&&<div className="import-merge-control">
      <button type="button" className={`import-hold-merge${holding?' is-holding':''}`} disabled={disabled} aria-label="Hold to merge" aria-describedby={hintId} title="Hold for one second to merge this recording's eligible additions" onPointerDown={start} onPointerUp={clear} onPointerLeave={clear} onPointerCancel={clear} onBlur={clear} onKeyDown={event=>{if([' ','Enter'].includes(event.key)){event.preventDefault();start(event,event.key);}else if(event.key==='Escape')clear();}} onKeyUp={event=>{if([' ','Enter'].includes(event.key)){event.preventDefault();if(pressed.current===event.key)clear();}}} onClick={event=>event.preventDefault()}><GitMerge size={15}/><span>Hold to merge</span></button>
      <small id={hintId}>Hold for 1 second</small>
    </div>}
  </>;
}
