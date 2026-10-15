import {useCallback,useLayoutEffect,useState} from 'react';

// Captured display reads start during commit, before unrelated passive metadata
// effects. This owner has no cache, prefetch or mutation authority. Loading is
// derived from the exact read identity, so dispatch never waits for another
// state update or microtask. Generic resource scheduling remains unchanged.
export function usePreparedTraceRead(path,revision,requestPort){
 const [state,setState]=useState(null),[nonce,setNonce]=useState(0);
 const reload=useCallback(()=>setNonce(value=>value+1),[]);
 const request=requestPort?.request;
 useLayoutEffect(()=>{
  if(!path){setState(previous=>previous===null?previous:null);return;}
  const controller=new AbortController();
  const publish=value=>{if(!controller.signal.aborted)setState({...value,path,revision,nonce,requestPort,request,signal:controller.signal});};
  let pending;
  try{
   if(typeof request!=='function')throw Error('Prepared trace request authority is unavailable.');
   pending=request(path,{signal:controller.signal});
  }catch(error){pending=Promise.reject(error);}
  Promise.resolve(pending).then(data=>publish({data,loading:false,error:null}),error=>publish({data:null,loading:false,error:error.message}));
  return()=>controller.abort();
 },[path,revision,nonce,requestPort,request]);
 // Cleanup retires completed results too: A-B-A and Activity reconnects must
 // not resurrect an earlier request with the same path/owner tuple.
 const current=state?.signal&&!state.signal.aborted&&state.path===path&&state.revision===revision&&state.nonce===nonce&&state.requestPort===requestPort&&state.request===request;
 return {...(current?state:{data:null,loading:!!path,error:null,path,revision}),reload};
}
