import {useLayoutEffect,useMemo,useRef,useState} from 'react';
import {api} from '../api.js';
import {useRetainedView} from '../retainedWorkspaceViews.js';

// Explicit display preparation; it grants no merge consent or action receipt.
export default function useWorkbenchPreparation(resource,projectId,path,revision){
 const active=useRetainedView()?.active!==false;
 const identity=useMemo(()=>({}),[projectId,path,revision,active]);
 const committed=useRef(null),pending=useRef(null),[state,setState]=useState(null);
 useLayoutEffect(()=>{committed.current=identity;return()=>{committed.current=null;pending.current?.abort();pending.current=null;};},[identity]);
 const prepare=async()=>{
  if(!active||!path||resource.loading||committed.current!==identity||pending.current)return;
  const controller=new AbortController();pending.current=controller;setState({identity,preparing:true});
  try{
   await api('/workbench/prepare',{method:'POST',body:{},signal:controller.signal});
   if(controller.signal.aborted||committed.current!==identity||pending.current!==controller)return;
   resource.reload();setState({identity,preparing:false,awaitingRead:true});
  }catch(error){if(!controller.signal.aborted&&committed.current===identity&&pending.current===controller)setState({identity,preparing:false,error:error.message});}
  finally{if(pending.current===controller)pending.current=null;}
 };
 const current=state?.identity===identity?state:null;
 return {...resource,prepare,preparing:!!current?.preparing||!!(current?.awaitingRead||resource.preparation)&&resource.loading,prepareError:current?.error||null};
}
