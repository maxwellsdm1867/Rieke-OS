import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {api} from '../api.js';
import {useRetainedView} from '../retainedWorkspaceViews.js';
import {prepareView} from '../protocol-overview/prepareView.js';

// Visible demand prepares once; failures retain explicit retry. Display
// preparation grants no merge consent or action receipt.
export default function useWorkbenchPreparation(resource,projectId,path,revision){
 const active=useRetainedView()?.active!==false;
 const demand=useMemo(()=>({}),[projectId,path,revision]),attempted=useRef(null);
 const identity=useMemo(()=>({}),[demand,active]);
 const committed=useRef(null),pending=useRef(null),[state,setState]=useState(null);
 useLayoutEffect(()=>{committed.current=identity;return()=>{committed.current=null;if(pending.current){attempted.current=null;pending.current.abort();pending.current=null;}};},[identity]);
 const prepare=async()=>{
  if(!active||!path||resource.loading||committed.current!==identity||pending.current)return;
  attempted.current=demand;
  const controller=new AbortController();pending.current=controller;setState({identity,preparing:true});
  try{
   await prepareView(projectId||demand,'/workbench/prepare',{request:api,signal:controller.signal});
   if(controller.signal.aborted||committed.current!==identity||pending.current!==controller)return;
   resource.reload();setState({identity,preparing:false,awaitingRead:true});
  }catch(error){if(!controller.signal.aborted&&committed.current===identity&&pending.current===controller)setState({identity,preparing:false,error:error.message});}
  finally{if(pending.current===controller)pending.current=null;}
 };
 const automaticPending=active&&!!path&&!resource.loading&&resource.preparation?.status==='pending'&&attempted.current!==demand;
 useEffect(()=>{
  if(!active||!path||resource.loading)return;
  if(resource.preparation?.status==='pending'&&attempted.current!==demand)void prepare();
  else if(resource.data&&!resource.error&&!resource.preparation)attempted.current=null;
 },[active,path,resource.loading,resource.preparation,resource.data,resource.error,demand]);
 const current=state?.identity===identity?state:null;
 return {...resource,prepare,preparing:automaticPending||!!current?.preparing||!!(current?.awaitingRead||resource.preparation)&&resource.loading,prepareError:current?.error||null};
}
