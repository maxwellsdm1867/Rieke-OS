import {useCallback,useLayoutEffect,useMemo,useState} from 'react';
import {useRetainedView} from '../retainedWorkspaceViews.js';
import {traceCacheRevision} from './traceReadContext.js';
import {geometryEligible,readTraceGeometry,traceDisplayPath} from './traceDisplayGeometry.js';

// Measure and dispatch under one committed geometry lifetime. The
// exact current canvas width is read before each new owner or width request;
// there is no render-time I/O or dimension guess from another view.
export function usePreparedTraceGeometry({canvas,enabled,requestEnabled=true,identity,owner,request,epochUuid,sourceSha256,stream,readContext}){
 const [state,setState]=useState(null),[nonce,setNonce]=useState(0);
 const reload=useCallback(()=>setNonce(value=>value+1),[]);
 const active=useRetainedView()?.active!==false;
 const readKey=JSON.stringify([identity,epochUuid,sourceSha256,stream?.uuid,stream?.sample_count,stream?.sample_rate,stream?.units,traceCacheRevision(0,readContext)]);
 const lifetime=useMemo(()=>({}),[canvas,enabled,requestEnabled,readKey,owner,request,nonce,active]);
 useLayoutEffect(()=>{
  if(!active||!enabled)return;
  let alive=true,width,controller=null,resolution=null,ratio=null;
  const unwatch=()=>{if(resolution?.removeEventListener)resolution.removeEventListener('change',changedResolution);else resolution?.removeListener?.(changedResolution);};
  const watch=()=>{const next=window.devicePixelRatio||1;if(next===ratio)return;unwatch();ratio=next;resolution=window.matchMedia?.(`(resolution: ${ratio}dppx)`);if(resolution?.addEventListener)resolution.addEventListener('change',changedResolution);else resolution?.addListener?.(changedResolution);};
  const measure=()=>{
   if(!alive)return;
   const measured=canvas.current?.getBoundingClientRect().width||0;
   const next=measured>0?Math.max(1,measured-103)*(window.devicePixelRatio||1):null;
   watch();if(next===width)return;
   width=next;controller?.abort();controller=new AbortController();
   const signal=controller.signal,useGeometry=requestEnabled&&geometryEligible(stream?.sample_count,width);
   const path=useGeometry?traceDisplayPath(epochUuid,stream,readContext,width):null;
   const captured={lifetime,signal,physicalWidth:width,useGeometry,path,revision:JSON.stringify([identity,width])};
   const publish=value=>{if(alive&&!signal.aborted)setState({...captured,...value});};
   if(!path){publish({data:null,loading:false,error:null});return;}
   let pending;
   try{
    if(typeof request!=='function')throw Error('Prepared trace request authority is unavailable.');
    pending=readTraceGeometry(request,path,{signal},{epochUuid,sourceSha256,stream,readContext,physicalWidth:width});
   }catch(error){pending=Promise.reject(error);}
   // Fetch starts before the width publication schedules another render.
   publish({data:null,loading:true,error:null});
   Promise.resolve(pending).then(data=>publish({data,loading:false,error:null}),error=>publish({data:null,loading:false,error:error.message}));
  };
  function changedResolution(){measure();}
  measure();const observer=new ResizeObserver(measure);if(canvas.current)observer.observe(canvas.current);
  window.addEventListener('resize',measure);
  return()=>{alive=false;controller?.abort();observer.disconnect();window.removeEventListener('resize',measure);unwatch();};
 },[lifetime]);
 const current=active&&state?.lifetime===lifetime&&state.signal&&!state.signal.aborted;
 return {...(current?state:{physicalWidth:null,useGeometry:false,path:null,revision:JSON.stringify([identity,null]),data:null,loading:enabled&&requestEnabled,error:null}),reload};
}
