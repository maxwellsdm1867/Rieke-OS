import {useEffect,useRef,useState} from 'react';
import {useRetainedView} from '../retainedWorkspaceViews.js';
import {api} from '../api.js';

// Older services keep their original catalog contract. Only route absence
// permits fallback; generation/validation failures remain visible failures.
// The registry route takes no path, so fallbackPath (which callers may vary with
// splits/scope) is part of the request identity only after a legacy service
// answered through it. A refresh under the same view identity keeps showing the
// last completed registry with loading=true; errors and identity changes clear it.
export function useFieldRegistry(revision=0,fallbackPath='/explore/predicate-fields'){
  const [state,setState]=useState({data:null,loading:true,error:null}),[attempt,setAttempt]=useState(0),[legacyMode,setLegacyMode]=useState(false);
  const view=useRetainedView(),identity=view?.identity,active=view?.active!==false,completed=useRef(null),latest=useRef(state);
  latest.current=state;
  const keyFor=legacy=>JSON.stringify([revision,legacy?fallbackPath:null,attempt,identity]);
  const key=keyFor(legacyMode);
  useEffect(()=>{
    if(!active)return;
    if(completed.current===key&&latest.current.key===key)return;
    const controller=new AbortController();let live=true;
    setState(previous=>({key,identity,data:previous.identity===identity?previous.data:null,loading:true,error:null,supportsSummaries:previous.identity===identity?previous.supportsSummaries:false}));
    async function load(){
      try{
        let data,legacy=false;
        try{data=await api('/explore/field-registry',{signal:controller.signal});}
        catch(error){if(controller.signal.aborted)throw error;if(![404,405].includes(error.status))throw error;legacy=true;data=await api(fallbackPath,{signal:controller.signal});}
        if(!Array.isArray(data.fields))throw Error('Invalid metadata field registry.');
        if(live){const done=keyFor(legacy);completed.current=done;setLegacyMode(legacy);setState({key:done,identity,data,loading:false,error:null,supportsSummaries:!legacy});}
      }catch(error){if(live){completed.current=null;setState({key,identity,data:null,loading:false,error:error.message,supportsSummaries:false});}}
    }
    load();return()=>{live=false;controller.abort();};
  },[key,active]);
  const visible=state.key===key?state:state.identity===identity&&state.data?{...state,loading:true,error:null}:{data:null,loading:true,error:null,supportsSummaries:false};
  return {...visible,reload:()=>setAttempt(value=>value+1)};
}
