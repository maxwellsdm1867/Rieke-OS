import {useLayoutEffect,useState} from 'react';

// The server uses exactly the painter's floating physical plot width. Hidden
// canvases wait for their first real measurement; no guessed/rounded width reads.
export function useTraceViewport(canvas,enabled){
 const [physicalWidth,setPhysicalWidth]=useState(null);
 useLayoutEffect(()=>{
  if(!enabled){setPhysicalWidth(null);return;}
  let resolution=null,ratio=null;
  const unwatch=()=>{if(resolution?.removeEventListener)resolution.removeEventListener('change',changedResolution);else resolution?.removeListener?.(changedResolution);};
  const watch=()=>{const next=window.devicePixelRatio||1;if(next===ratio)return;unwatch();ratio=next;resolution=window.matchMedia?.(`(resolution: ${ratio}dppx)`);if(resolution?.addEventListener)resolution.addEventListener('change',changedResolution);else resolution?.addListener?.(changedResolution);};
  const measure=()=>{const width=canvas.current?.getBoundingClientRect().width||0;const next=width>0?Math.max(1,width-103)*(window.devicePixelRatio||1):null;setPhysicalWidth(previous=>previous===next?previous:next);watch();};
  function changedResolution(){measure();}

  measure();const observer=new ResizeObserver(measure);if(canvas.current)observer.observe(canvas.current);
  window.addEventListener('resize',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure);unwatch();};
 },[canvas,enabled]);
 return enabled?physicalWidth:null;
}
