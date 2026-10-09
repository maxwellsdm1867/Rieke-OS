import {useLayoutEffect,useRef,useState} from 'react';

// A hold is single-use intent. Cancelled presses and the click following a hold
// cannot also trigger inspection; keyboard activation has the same threshold.
export default function InspectImportButton({onInspect,onMerge,disabled=false,identity}){
  const timer=useRef(null),consumed=useRef(false),pressed=useRef(null),latest=useRef(null),[holding,setHolding]=useState(false);
  function clear(){clearTimeout(timer.current);timer.current=null;pressed.current=null;setHolding(false);}
  useLayoutEffect(()=>{
    latest.current={onInspect,onMerge,disabled,identity};
  });
  useLayoutEffect(()=>{clear();consumed.current=false;return()=>{clearTimeout(timer.current);timer.current=null;pressed.current=null;latest.current=null;};},[identity,disabled,!!onMerge]);
  function cancel(){consumed.current=!!pressed.current||consumed.current;clear();}
  function start(event,key='pointer'){
    if(disabled||pressed.current||event.repeat||event.button!==undefined&&event.button!==0)return;
    consumed.current=false;pressed.current=key;
    if(!onMerge)return;
    setHolding(true);const owner=identity;
    timer.current=setTimeout(()=>{timer.current=null;if(!pressed.current||latest.current?.identity!==owner||latest.current?.disabled)return;consumed.current=true;setHolding(false);latest.current.onMerge?.();},1000);
  }
  return <button disabled={disabled} title={onMerge?"Click to inspect in Workbench. Hold for 1 second to merge this recording's eligible additions.":'Inspect in Workbench'} aria-label={onMerge?'Inspect in Workbench; hold 1 second to merge':'Inspect in Workbench'} onPointerDown={start} onPointerUp={clear} onPointerLeave={cancel} onPointerCancel={cancel} onBlur={cancel} onKeyDown={event=>{if([' ','Enter'].includes(event.key)){event.preventDefault();start(event,event.key);}else if(event.key==='Escape')cancel();}} onKeyUp={event=>{if([' ','Enter'].includes(event.key)){event.preventDefault();const active=pressed.current===event.key;clear();if(active&&!consumed.current)onInspect?.();consumed.current=true;}}} onClick={()=>{if(consumed.current){consumed.current=false;return;}onInspect?.();}}> {holding?'Hold to merge…':'Inspect in Workbench'}{onMerge&&<small> · hold 1s to merge</small>}</button>;
}
