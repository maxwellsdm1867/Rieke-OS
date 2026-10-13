import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from '../api.js';
import {createTreeLayoutSaver} from './treeLayoutPersistence.js';
import {useRetainedView} from '../retainedWorkspaceViews.js';

/**
 * Bind saved protocol split order to this React mount. Initial order is captured
 * once; readiness/load errors and save status are separate public state.
 * Cleanup aborts the load and fences publication, without clearing the old saver
 * or cancelling accepted writes. See AGENTS.md and the real-hook tests.
 */
export default function useProtocolTreeLayout(id,initial,{enabled=true}={}){
  const initialOrder=useRef(initial).current;
  const [requestedId,setRequestedId]=useState(enabled?id:null);
  const loadEnabled=enabled||requestedId===id;
  useEffect(()=>{if(enabled)setRequestedId(id);},[enabled,id]);
  const [order,setOrder]=useState(Array.isArray(initialOrder)?initialOrder:['date','cell','block']);
  const [load,setLoad]=useState({ready:false,error:null}),[attempt,setAttempt]=useState(0);
  const [save,setSave]=useState({status:'saved',version:0});
  const saver=useRef(null);
  const retained=useRetainedView(),completed=useRef(null),live=useRef(false);
  const identity=JSON.stringify([id,attempt,retained?.identity]),currentIdentity=useRef(identity);currentIdentity.current=identity;
  useEffect(()=>{
    if(!loadEnabled)return;
    live.current=true;
    if(retained&&completed.current===identity)return()=>{live.current=false;};
    let mounted=true;
    const controller=new AbortController();
    setLoad({ready:false,error:null});
    api(`/protocols/${id}/tree-layout`,{signal:controller.signal}).then(result=>{
      if(!mounted)return;
      if(!Array.isArray(result.split_order)||!Number.isInteger(result.version))throw new Error('Invalid saved tree layout.');
      const nextSaver=createTreeLayoutSaver({version:result.version,splitOrder:result.split_order,
        write:body=>api(`/protocols/${id}/tree-layout`,{method:'PUT',body}),
        onState:value=>{if(live.current&&currentIdentity.current===identity&&saver.current===nextSaver)setSave(value);}});
      saver.current=nextSaver;completed.current=identity;
      setOrder(initialOrder!=null?(Array.isArray(initialOrder)?initialOrder:initialOrder.split(',').map(s=>s.trim()).filter(Boolean)):result.split_order);
      setSave({status:'saved',version:result.version});setLoad({ready:true,error:null});
    }).catch(error=>{if(mounted)setLoad({ready:false,error:error.message});});
    return()=>{mounted=false;live.current=false;controller.abort();};
  },[id,attempt,initialOrder,loadEnabled,identity]);
  const remember=useCallback(fields=>{setOrder(old=>JSON.stringify(old)===JSON.stringify(fields)?old:[...fields]);saver.current?.remember(fields);},[]);
  return {order,remember,...load,save,retrySave:()=>saver.current?.retry(),reload:()=>setAttempt(value=>value+1)};
}
