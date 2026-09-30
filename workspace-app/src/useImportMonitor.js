import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api.js';
import {isImportPending,importMonitorDelay,shouldRefreshImportCompletion,completedImportToReview} from './importProgress.js';
import {importCompletionKey} from './protocolSuggestions.js';
// This lightweight endpoint has its own timeout; parsing/export requests do not.
// A failed read retains the last confirmed state and never retries an import POST.
export default function useImportMonitor(revision,onCompleted,watchingRequest=false,enabled=true){
  const [state,setState]=useState({data:null,loading:true,error:null,observedAt:null});
  const [nonce,setNonce]=useState(0),callback=useRef(onCompleted),previous=useRef(null),recovering=useRef(false),previousJobs=useRef(null);
  callback.current=onCompleted;
  const reload=useCallback(()=>setNonce(value=>value+1),[]);
  useEffect(()=>{
    if(!enabled){setState({data:null,loading:false,error:null,observedAt:null});return;}
    const controller=new AbortController();let timedOut=false;
    setState(value=>({...value,loading:true}));
    const timeout=setTimeout(()=>{timedOut=true;controller.abort();},8000);
    api('/jobs',{signal:controller.signal}).then(data=>{
      if(controller.signal.aborted)return;
      if(!Array.isArray(data.jobs))throw new Error('Import monitor returned an invalid job list.');
      setState({data,loading:false,error:null,observedAt:Date.now()});
    }).catch(error=>{
      if(controller.signal.aborted&&!timedOut)return;
      setState(value=>({...value,loading:false,error:timedOut?'Import monitor did not respond within 8 seconds. Job state remains unconfirmed.':error.message}));
    }).finally(()=>clearTimeout(timeout));
    return()=>{clearTimeout(timeout);controller.abort();};
  },[revision,nonce,enabled]);
  const pending=(state.data?.jobs || []).some(isImportPending);
  const delay=!enabled?null:importMonitorDelay({loading:state.loading,pending,error:state.error,watching:watchingRequest});
  useEffect(()=>{if(delay===null)return;const timer=setTimeout(reload,delay);return()=>clearTimeout(timer);},[delay,reload,state.observedAt,state.error]);
  const completed=importCompletionKey(state.data?.jobs || []);
  useEffect(()=>{
    if(state.error){recovering.current=true;return;}
    if(!state.data||state.error||state.loading)return;
    const refresh=shouldRefreshImportCompletion(previous.current,completed,watchingRequest,recovering.current);
    recovering.current=false;
    previous.current=completed;
    const reviewJob=completedImportToReview(previousJobs.current,state.data.jobs,watchingRequest);
    previousJobs.current=state.data.jobs;
    if(refresh)callback.current(reviewJob);
  },[completed,state.data,state.error,state.loading,watchingRequest]);
  return {...state,reload,connectionError:state.error};
}
