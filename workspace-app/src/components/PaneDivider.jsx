import {useEffect,useRef} from 'react';

export default function PaneDivider({label,value,min,max,onChange,onCommit,reverse=false,className='',style}){
  const drag=useRef(null),frame=useRef(null),latest=useRef(value);
  const clamp=value=>Math.round(Math.max(min,Math.min(max,value)));
  useEffect(()=>()=>{if(frame.current!==null)cancelAnimationFrame(frame.current);},[]);
  function move(event){
    if(!drag.current)return;
    latest.current=clamp(drag.current.value+(event.clientX-drag.current.x)*(reverse?-1:1));
    if(frame.current===null)frame.current=requestAnimationFrame(()=>{frame.current=null;onChange(latest.current);});
  }
  function finish(event){
    if(!drag.current)return;
    if(event.type!=='pointercancel')move(event);drag.current=null;
    if(frame.current!==null){cancelAnimationFrame(frame.current);frame.current=null;}
    onChange(latest.current);onCommit?.(latest.current);
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  }
  return <div role="separator" aria-label={label} aria-orientation="vertical" aria-valuemin={min} aria-valuemax={Math.round(max)} aria-valuenow={value} aria-valuetext={`${value} pixels`} tabIndex={0} className={`pane-divider ${className}`} style={style} title={`${label}: drag, or use Left/Right arrow keys. Home/End set limits.`}
    onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();event.currentTarget.setPointerCapture(event.pointerId);drag.current={x:event.clientX,value};latest.current=value;}}
    onPointerMove={move} onPointerUp={finish} onPointerCancel={finish}
    onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=clamp(event.key==='Home'?min:event.key==='End'?max:value+(event.key==='ArrowLeft'?-1:1)*(reverse?-1:1)*(event.shiftKey?40:10));onChange(next);onCommit?.(next);}}><span/></div>;
}
