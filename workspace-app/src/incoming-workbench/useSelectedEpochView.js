import {useEffect,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createWorkbenchSelection} from './workbenchAuthority.js';
import {selectedViewFilters} from './selectedIncomingWorkflow.js';

// The chosen view is presentation intent. A manifest is a separate, short-lived
// read receipt and must be renewed after a pause or authority change.
export function useSelectedEpochView({projectId,protocolId,context,filters,selected=[],paused=false,disabled=false,request}){
  const instance=useId(),sequence=useRef(0);
  const semanticKey=JSON.stringify([projectId,protocolId,context?.cohort_key?[context.root,context.cohort_key,context.actor]:context,filters,selected]);
  const owner=useMemo(()=>({}),[semanticKey]);
  const authorityKey=JSON.stringify([context,paused,disabled]);
  const authority=useMemo(()=>({}),[owner,authorityKey,request]);
  const [intent,setIntent]=useState(null),[receipt,setReceipt]=useState(null),[failure,setFailure]=useState(null),[retry,setRetry]=useState(0);
  const chosen=intent?.owner===owner?intent:null;
  const current=useRef(null);
  useLayoutEffect(()=>{current.current={owner,authority,intent:chosen};return()=>{current.current=null;};},[owner,authority,chosen]);
  const manifests=context?.selection_manifests===true;
  const admitted=!!chosen&&receipt?.intent===chosen&&receipt.authority===authority;
  const prior=chosen&&receipt?.intent===chosen?receipt:null;
  const pending=!!chosen&&manifests&&!admitted;
  const error=failure?.intent===chosen&&failure.authority===authority?failure.message:null;
  useEffect(()=>{
    if(!chosen||!manifests||paused||disabled||admitted)return;
    const controller=new AbortController();
    const isCurrent=()=>!controller.signal.aborted&&current.current?.owner===owner&&current.current.authority===authority&&current.current.intent===chosen;
    setFailure(null);
    createWorkbenchSelection({root:context.root,context:{...context,draft:{draft_version:0}},ids:selected,signal:controller.signal},request)
      .then(value=>{if(isCurrent())setReceipt({intent:chosen,authority,context,token:value.selection_token});})
      .catch(error=>{if(isCurrent())setFailure({intent:chosen,authority,message:error.message});});
    return()=>controller.abort();
  },[chosen,authority,owner,manifests,paused,disabled,admitted,retry]);
  const toggle=()=>{
    if(current.current?.owner!==owner)return;
    if(chosen){setIntent(null);return;}
    if(paused||disabled||!selected.length)return;
    setIntent({owner,key:`${instance}:${++sequence.current}`});
  };
  return {selected:!!chosen,pending,error,toggle,clear:()=>setIntent(null),retry:()=>setRetry(value=>value+1),
    // While renewal is pending, retain only the old, inert selected presentation.
    // Never combine an old token with a new scope or silently widen to all rows.
    context:prior?{...prior.context,selection_token:prior.token,selection_view_key:chosen.key}:context,
    filters:chosen&&!manifests?selectedViewFilters(filters,selected):filters};
}
