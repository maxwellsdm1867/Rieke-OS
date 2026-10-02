import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api.js';
import {requireWorkbenchQueue,workbenchRoot} from './workbenchAuthority.js';
export default function useWorkbenchQueue(protocolId,revision,provided){
  const [state,setState]=useState({data:provided??null,loading:provided===undefined,error:null}),[nonce,setNonce]=useState(0);
  const controller=useRef(null),generation=useRef(0),requested=useRef({protocolId,revision,nonce,provided});
  const reload=useCallback(()=>setNonce(value=>value+1),[]);
  useEffect(()=>{
    requested.current={protocolId,revision,nonce,provided};
    if(provided!==undefined){setState({data:provided,loading:false,error:null});return;}
    controller.current?.abort();
    const token=++generation.current,cancel=new AbortController();controller.current=cancel;
    setState(previous=>({...previous,loading:true,error:null}));
    api(`${workbenchRoot(protocolId)}?limit=20`,{signal:cancel.signal}).then(value=>{if(!cancel.signal.aborted&&token===generation.current)setState({data:requireWorkbenchQueue(value),loading:false,error:null});}).catch(error=>{if(!cancel.signal.aborted&&token===generation.current)setState(previous=>({...previous,loading:false,error:error.message}));});
    return()=>{cancel.abort();generation.current++;};
  },[protocolId,revision,nonce,provided]);
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
    }catch(error){if(!cancel.signal.aborted&&token===generation.current)setState(value=>({...value,loading:false,error:error.message}));}
  }
  useEffect(()=>()=>controller.current?.abort(),[]);
  const refreshPending=requested.current.protocolId!==protocolId||requested.current.revision!==revision||requested.current.nonce!==nonce||requested.current.provided!==provided;
  return {...state,loading:state.loading||refreshPending,reload,more};
}
