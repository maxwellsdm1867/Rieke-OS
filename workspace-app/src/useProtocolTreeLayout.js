import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api.js';
import {createTreeLayoutSaver} from './treeLayoutPersistence.js';

export default function useProtocolTreeLayout(id,initial){
  const initialOrder=useRef(initial).current;
  const [order,setOrder]=useState(Array.isArray(initialOrder)?initialOrder:['date','cell','block']);
  const [load,setLoad]=useState({ready:false,error:null}),[attempt,setAttempt]=useState(0);
  const [save,setSave]=useState({status:'saved',version:0});
  const saver=useRef(null);
  useEffect(()=>{
    let mounted=true;
    const controller=new AbortController();
    setLoad({ready:false,error:null});
    api(`/protocols/${id}/tree-layout`,{signal:controller.signal}).then(result=>{
      if(!mounted)return;
      if(!Array.isArray(result.split_order)||!Number.isInteger(result.version))throw new Error('Invalid saved tree layout.');
      saver.current=createTreeLayoutSaver({version:result.version,splitOrder:result.split_order,
        write:body=>api(`/protocols/${id}/tree-layout`,{method:'PUT',body}),
        onState:value=>{if(mounted)setSave(value);}});
      setOrder(initialOrder!=null?(Array.isArray(initialOrder)?initialOrder:initialOrder.split(',').map(s=>s.trim()).filter(Boolean)):result.split_order);
      setSave({status:'saved',version:result.version});setLoad({ready:true,error:null});
    }).catch(error=>{if(mounted)setLoad({ready:false,error:error.message});});
    return()=>{mounted=false;controller.abort();};
  },[id,attempt,initialOrder]);
  const remember=useCallback(fields=>{setOrder(old=>JSON.stringify(old)===JSON.stringify(fields)?old:[...fields]);saver.current?.remember(fields);},[]);
  return {order,remember,...load,save,retrySave:()=>saver.current?.retry(),reload:()=>setAttempt(value=>value+1)};
}
