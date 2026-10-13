import {useEffect,useRef,useState} from 'react';
import {useRetainedView} from '../retainedWorkspaceViews.js';
import {api} from '../api.js';

// Older services keep their original catalog contract. Only route absence
// permits fallback; generation/validation failures remain visible failures.
export function useFieldRegistry(revision=0,fallbackPath='/explore/predicate-fields'){
  const [state,setState]=useState({data:null,loading:true,error:null}),[attempt,setAttempt]=useState(0);
  const view=useRetainedView(),identity=view?.identity,completed=useRef(null);
  const key=JSON.stringify([revision,fallbackPath,attempt,identity]);
  useEffect(()=>{
    if(view&&completed.current===key)return;
    const controller=new AbortController();let live=true;
    setState({key,data:null,loading:true,error:null});
    async function load(){
      try{
        let data,legacy=false;
        try{data=await api('/explore/field-registry',{signal:controller.signal});}
        catch(error){if(controller.signal.aborted)throw error;if(![404,405].includes(error.status))throw error;legacy=true;data=await api(fallbackPath,{signal:controller.signal});}
        if(!Array.isArray(data.fields))throw Error('Invalid metadata field registry.');
        if(live){completed.current=key;setState({key,data,loading:false,error:null,supportsSummaries:!legacy});}
      }catch(error){if(live){completed.current=null;setState({key,data:null,loading:false,error:error.message,supportsSummaries:false});}}
    }
    load();return()=>{live=false;controller.abort();};
  },[key]);
  return {...(state.key===key?state:{data:null,loading:true,error:null,supportsSummaries:false}),reload:()=>setAttempt(value=>value+1)};
}
