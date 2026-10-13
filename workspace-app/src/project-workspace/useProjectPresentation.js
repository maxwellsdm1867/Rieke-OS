import {useEffect,useState} from 'react';
import {api} from '../api.js';

// A disk snapshot is display-only. It never enters the canonical resource cache
// or restores server capabilities, a request owner, or mutation authority.
export function validProjectPresentation(value,projectId,projectPath){
  return !!value&&value.available===true&&value.format==='disco-project-presentation'&&value.version===1&&
    value.presentation_only===true&&value.project_uuid===projectId&&value.project_path===projectPath&&
    typeof value.observed_at==='string'&&!!value.overview&&typeof value.overview==='object'&&
    value.overview.project?.project_uuid===projectId&&Array.isArray(value.overview.cells)&&
    Array.isArray(value.overview.protocols)&&Array.isArray(value.overview.sources);
}

export default function useProjectPresentation(projectId,projectPath,{enabled=false}={}){
  const identity=JSON.stringify([projectId,projectPath]);
  const [state,setState]=useState(null);
  useEffect(()=>{
    if(!enabled||!projectId||!projectPath)return;
    const controller=new AbortController();
    api('/project/presentation',{signal:controller.signal}).then(value=>{
      if(!controller.signal.aborted&&validProjectPresentation(value,projectId,projectPath))setState({identity,value});
    }).catch(()=>{}); // Disposable cache absence/failure cannot block opening.
    return()=>controller.abort();
  },[enabled,projectId,projectPath,identity]);
  return state?.identity===identity?state.value:null;
}
