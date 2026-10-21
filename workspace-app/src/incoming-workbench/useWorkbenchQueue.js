import {useCallback,useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {useAnnotationProfile} from '../annotations/annotationProfile.js';
import {protocolWorkbenchVersion,subscribeWorkbenchChanges} from './mergeUndo.js';
import {api} from '../api.js';
import {requireWorkbenchQueue,workbenchRoot} from './workbenchAuthority.js';
import useWorkbenchPreparation from './useWorkbenchPreparation.js';
export default function useWorkbenchQueue(protocolId,revision,provided,projectId){
  const profile=useAnnotationProfile(),actor=profile.profileUuid||'';
  const mutation=useSyncExternalStore(subscribeWorkbenchChanges,()=>protocolWorkbenchVersion(projectId,protocolId),()=>0);
  // A provided summary predates an author switch. Read our own actor-specific
  // queue thereafter; the parent summary cannot certify its author.
  const supplied=useRef({actor,mutation,retired:false});
  if(actor&&supplied.current.actor&&actor!==supplied.current.actor||mutation!==supplied.current.mutation)supplied.current.retired=true;
  if(actor)supplied.current.actor=actor;
  if(provided!==null&&supplied.current.retired)provided=undefined;
  const dataOwner=JSON.stringify([projectId,protocolId,actor]);
  const owner=JSON.stringify([dataOwner,mutation]);
  const [state,setState]=useState({data:provided??null,loading:provided===undefined,error:null}),[nonce,setNonce]=useState(0);
  const controller=useRef(null),generation=useRef(0),requested=useRef({projectId,protocolId,revision,nonce,provided,owner,dataOwner});
  const reload=useCallback(()=>setNonce(value=>value+1),[]);
  // An Activity reconnect (tab return) with the same protocol, revision and
  // reload nonce keeps the completed queue: nothing it shows can have changed
  // locally, and merges/finish still check queue_revision at action time.
  const completed=useRef(null);
  useEffect(()=>{
    const priorDataOwner=requested.current.dataOwner;
    requested.current={projectId,protocolId,revision,nonce,provided,owner,dataOwner};
    if(profile.loading){completed.current=null;setState(previous=>({...previous,data:null,loading:true,error:null}));return;}
    if(provided!==undefined){setState({data:provided,loading:false,error:null});return;}
    const done=completed.current;
    if(done&&done.owner===owner&&done.projectId===projectId&&done.protocolId===protocolId&&done.revision===revision&&done.nonce===nonce)return;
    controller.current?.abort();
    const token=++generation.current,cancel=new AbortController();controller.current=cancel;
    setState(previous=>({...previous,...(priorDataOwner!==dataOwner?{data:null}:{}),loading:true,error:null}));
    api(`${workbenchRoot(protocolId)}?limit=20`,{signal:cancel.signal}).then(value=>{if(!cancel.signal.aborted&&token===generation.current){const data=requireWorkbenchQueue(value);completed.current={projectId,protocolId,revision,nonce,owner};setState({data,loading:false,error:null});}}).catch(error=>{if(!cancel.signal.aborted&&token===generation.current)setState(previous=>({...previous,...(error.preparation?{data:null}:{}),loading:false,error:error.message,preparation:error.preparation||null}));});
    completed.current=null;
    return()=>{cancel.abort();generation.current++;};
  },[projectId,protocolId,revision,nonce,provided,owner,profile.loading]);
  async function more(){
    if(state.loading||!state.data?.next_cursor||provided!==undefined)return;
    const token=generation.current,cancel=new AbortController();controller.current=cancel;
    setState(value=>({...value,loading:true,error:null}));
    try{
      const next=requireWorkbenchQueue(await api(`${workbenchRoot(protocolId)}?limit=20&cursor=${encodeURIComponent(state.data.next_cursor)}`,{signal:cancel.signal}));
      if(cancel.signal.aborted||token!==generation.current)return;
      if(next.queue_revision!==state.data.queue_revision)throw new Error('The queue changed while paging. Refresh before reviewing another proposal.');
      const candidates=[...new Map([...state.data.candidates,...next.candidates].map(item=>[item.candidate_revision_uuid,item])).values()];
      setState({data:{...next,candidates},loading:false,error:null});
    }catch(error){if(!cancel.signal.aborted&&token===generation.current)setState(value=>({...value,...(error.preparation?{data:null}:{}),loading:false,error:error.message,preparation:error.preparation||null}));}
  }
  useEffect(()=>()=>controller.current?.abort(),[]);
  const ownerChanged=requested.current.owner!==owner,dataOwnerChanged=requested.current.dataOwner!==dataOwner;
  const refreshPending=ownerChanged||requested.current.projectId!==projectId||requested.current.protocolId!==protocolId||requested.current.revision!==revision||requested.current.nonce!==nonce||requested.current.provided!==provided;
  return useWorkbenchPreparation({...state,...(dataOwnerChanged?{data:null,error:null}:{}),ownerKey:owner,loading:state.loading||refreshPending||profile.loading,reload,more},projectId,workbenchRoot(protocolId),JSON.stringify([revision,owner]));
}
