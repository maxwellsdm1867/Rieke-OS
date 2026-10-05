import {useWorkspaceRequestScope} from '../workspaceRequest.js';
import {useEffect,useRef,useState} from 'react';
import {api} from '../api.js';
import {epochPageRequest} from './epochBrowserSource.js';

export function useEpochBrowserPage(source,page,revision=0,reads=null){
  const owner=useWorkspaceRequestScope();
  const request=JSON.stringify(epochPageRequest(owner?{...source,pageSize:owner.pageSize}:source,page));
  const [nonce,setNonce]=useState(0),[state,setState]=useState({data:null,loading:true,error:null});
  const transport=reads?.load||owner?.request||api,refresh=reads?.reload;
  const attempt=useRef({nonce:0});
  const key=JSON.stringify([request,revision,nonce]);
  useEffect(()=>{
    // Only the explicit retry bypasses the pool. Preserve that decision across
    // effect replay, but ordinary later page/scope navigation shares again.
    if(attempt.current.key!==key||attempt.current.owner!==owner||attempt.current.transport!==transport||attempt.current.refresh!==refresh){
      attempt.current={key,owner,transport,refresh,nonce,fresh:nonce!==attempt.current.nonce};
    }
    const send=attempt.current.fresh&&refresh?refresh:transport;
    const controller=new AbortController(),{path,options}=JSON.parse(request);
    setState({data:null,loading:true,error:null,key,owner,transport});
    send(path,{...options,signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({data,loading:false,error:null,key,owner,transport});}).catch(error=>{if(!controller.signal.aborted)setState({data:null,loading:false,error:error.message,key,owner,transport});});
    return()=>controller.abort();
  },[key,request,owner,transport,refresh]);
  return {...(state.key===key&&state.owner===owner&&state.transport===transport?state:{data:null,loading:true,error:null}),reload:()=>setNonce(value=>value+1)};
}
