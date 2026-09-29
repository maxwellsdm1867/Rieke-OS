import {useEffect,useState} from 'react';
import {api} from './api.js';
import {epochPageRequest} from './epochBrowserSource.js';

export function useEpochBrowserPage(source,page,revision=0){
  const request=JSON.stringify(epochPageRequest(source,page));
  const [nonce,setNonce]=useState(0),[state,setState]=useState({data:null,loading:true,error:null});
  const key=JSON.stringify([request,revision,nonce]);
  useEffect(()=>{
    const controller=new AbortController(),{path,options}=JSON.parse(request);
    setState({data:null,loading:true,error:null,key});
    api(path,{...options,signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({data,loading:false,error:null,key});}).catch(error=>{if(!controller.signal.aborted)setState({data:null,loading:false,error:error.message,key});});
    return()=>controller.abort();
  },[key,request]);
  return {...(state.key===key?state:{data:null,loading:true,error:null}),reload:()=>setNonce(value=>value+1)};
}
