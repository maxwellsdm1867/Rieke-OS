import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {api} from '../api.js';
import {useWorkspaceRequestScope} from '../workspaceRequest.js';
import {useRetainedView} from '../retainedWorkspaceViews.js';
import {selectedSummaryIds} from '../incoming-workbench/incomingSelectionSummary.js';
import {readSelectedEpochCellCount} from './selectedEpochCellCount.js';

export function useSelectedEpochCellCount({projectId,scope,selected,readContext=null,paused=false,request:providedRequest=api,settleMs=250}){
  const port=useWorkspaceRequestScope(),view=useRetainedView(),request=port?.request??providedRequest;
  const chain=[];for(let activity=view?.activity;activity;activity=activity.parent)chain.push({activity,token:activity.token});
  const active=view?.active!==false&&chain.every(({activity})=>activity.active!==false);
  const ids=useMemo(()=>selectedSummaryIds(selected),[selected]),idsKey=JSON.stringify(ids);
  const key=JSON.stringify([projectId,scope,readContext,port?.identity,view?.identity,view?.route?.key,idsKey]);
  const identity=useMemo(()=>({}),[key,request,active,paused]),current=useRef(null);
  const [state,setState]=useState(null);
  useLayoutEffect(()=>{current.current=identity;return()=>{current.current=null;};},[identity]);
  useEffect(()=>{
    if(!active||paused||!ids?.length)return;
    const controller=new AbortController();
    const isCurrent=()=>!controller.signal.aborted&&current.current===identity&&chain.every(({activity,token})=>activity.active!==false&&activity.token===token);
    const timer=setTimeout(()=>{
      readSelectedEpochCellCount({selected:ids,readContext,request,signal:controller.signal}).then(count=>{
        if(isCurrent())setState({identity,count});
      }).catch(error=>{if(isCurrent())setState({identity,error:error.message});});
    },settleMs);
    return()=>{clearTimeout(timer);controller.abort();};
  },[identity,active,paused,settleMs]);
  if(ids?.length===0)return {count:0,loading:false,error:null};
  if(!ids)return {count:null,loading:false,error:'The selected epoch identities could not be verified.'};
  const shown=active&&!paused&&state?.identity===identity?state:null;
  return {count:shown?.count??null,loading:active&&!paused&&!shown,error:shown?.error??null};
}
