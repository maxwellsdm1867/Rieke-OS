import {useEffect,useRef,useState} from 'react';
import {createSummaryController,summaryRequestKey} from './requestedSummaries.js';
import {summaryApi} from './summaryApi.js';

export function useRequestedSummaries(request,{enabled=true,adapter=summaryApi}={}){
  const key=summaryRequestKey(request),controller=useRef(null);
  const [state,setState]=useState({status:'idle',result:null,error:null}),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    if(!enabled){setState({status:'idle',result:null,error:null,key});return;}
    const client=createSummaryController({adapter,onState:setState});controller.current=client;
    client.start(JSON.parse(key));return()=>{client.dispose();if(controller.current===client)controller.current=null;};
  },[key,enabled,adapter,attempt]);
  // Suppress old-scope statistics at render, before effect cleanup runs.
  const visible=!enabled?{status:'idle',result:null,error:null}:state.key===key?state:{status:'pending',result:null,error:null};
  return {...visible,cancel:()=>controller.current?.cancel(),retry:()=>setAttempt(value=>value+1)};
}
