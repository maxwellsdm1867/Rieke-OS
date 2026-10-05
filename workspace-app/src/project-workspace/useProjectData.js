import {useEffect,useRef,useState} from 'react';
import {api} from '../api.js';

// Render the project shell first, then fill the restored view. One in-flight
// load serves the most recent chosen view; failures remain local to the project.
export default function useProjectData(registry,onReady){
  const [loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const pending=useRef(null),nextAction=useRef(null);
  const resumed=useRef(null);
  const ready=!!registry&&!registry.launcher&&(loaded||!registry.project_data||registry.project_data.status==='ready');
  async function open(action){
    if(ready){action?.();return;}
    if(action)nextAction.current=action;
    if(pending.current)return pending.current;
    setBusy(true);setError('');
    pending.current=api('/project/activate',{method:'POST',body:{retry:true}}).then(result=>{
      if(result.status!=='ready')throw new Error('Project data did not finish opening.');
      setLoaded(true);onReady?.();nextAction.current?.();
    }).catch(failure=>setError(failure.message)).finally(()=>{pending.current=null;setBusy(false);});
    return pending.current;
  }
  useEffect(()=>{
    const project=registry?.current_project_uuid;
    if(!project||ready||resumed.current===project||!registry.project_data)return;
    // Two frames let the shell paint before requesting scientific services.
    let second;
    const first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{
      resumed.current=project;void open();
    });});
    return()=>{cancelAnimationFrame(first);if(second)cancelAnimationFrame(second);};
  },[registry?.current_project_uuid,ready]);
  return {ready,busy,error,open,retry:()=>open(nextAction.current)};
}
