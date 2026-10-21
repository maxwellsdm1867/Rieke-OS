import {useEffect,useRef,useState} from 'react';
import {summaryApi} from '../requested-summaries/summaryApi.js';
import {queryCountsResult} from './queryCounts.js';

// Polls the one counts job a pending query names (existing summary-job poll
// and cancel routes). A different job (the query changed) cancels the previous
// one if it is still pending. Hiding or leaving the view does not cancel: the
// job is shared with the result pages, finishes once and is reused on return.
export function useQueryCounts(requestId,{adapter=summaryApi,pollMs=250}={}){
  const [state,setState]=useState({id:null,status:'idle'});
  const open=useRef(null);
  useEffect(()=>{
    if(open.current&&open.current!==requestId){const previous=open.current;open.current=null;Promise.resolve().then(()=>adapter.cancel(previous)).catch(()=>{});}
    if(!requestId)return;
    open.current=requestId;
    const controller=new AbortController();let timer=null;
    const settle=next=>{if(open.current===requestId)open.current=null;setState({id:requestId,...next});};
    async function poll(){
      try{
        const receipt=await adapter.poll(requestId,controller.signal);
        if(controller.signal.aborted)return;
        if(receipt?.status==='pending'){timer=setTimeout(poll,pollMs);return;}
        if(receipt?.status==='ready')settle({status:'ready',result:queryCountsResult(receipt,requestId)});
        else settle({status:['stale','failed','cancelled'].includes(receipt?.status)?receipt.status:'failed',error:receipt?.error||'Exact counts are unavailable.'});
      }catch(error){if(!controller.signal.aborted)settle({status:'failed',error:error.message});}
    }
    poll();
    return()=>{controller.abort();clearTimeout(timer);};
  },[requestId,adapter,pollMs]);
  return requestId?(state.id===requestId?state:{status:'pending'}):{status:'idle'};
}
