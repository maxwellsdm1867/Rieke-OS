import {useLayoutEffect,useMemo,useRef,useState} from 'react';
import {appendCellWindow,cellWindowOf} from './cellWindows.js';

// One list per exact caller scope. Layout cleanup retires requests on Activity
// hide as well as unmount; object lifetimes fence A/B/A returns and late replies.
export function useCellWindows(scopeKey,load,{enabled=true}={}){
  const scope=useMemo(()=>({key:scopeKey}),[scopeKey]);
  const [state,setState]=useState({scope:null,cells:null,total:null,next:null,loading:false,error:null});
  const current=useRef(scope);current.current=scope;
  const active=useRef(null),flight=useRef(null);
  useLayoutEffect(()=>{
    const lifetime={scope,enabled};active.current=lifetime;
    setState(old=>old.loading?{...old,loading:false}:old);
    return()=>{active.current=null;flight.current?.abort();flight.current=null;};
  },[scope,enabled]);
  const view=state.scope===scope?state:{scope,cells:null,total:null,next:null,loading:false,error:null};
  function accept(data){
    if(current.current!==scope||!Array.isArray(data?.cells))return;
    const window=cellWindowOf(data);
    setState(old=>{
      if(old.scope===scope&&old.cells?.length===data.cells.length&&old.total===(window?.total??data.cells.length)&&old.next===(window?.next??null)&&old.cells.every((cell,index)=>cell===data.cells[index]))return old;
      // Offset/anchor pages can repeat the first window at the same receipt.
      const kept=window&&old.scope===scope&&old.cells&&old.total===window.total&&old.cells.length>data.cells.length&&data.cells.every((cell,index)=>old.cells[index]?.cell_uuid===cell.cell_uuid);
      return kept?old:{scope,cells:data.cells,total:window?.total??data.cells.length,next:window?.next??null,loading:false,error:null};
    });
  }
  async function more(){
    const lifetime=active.current,after=view.next;
    if(!enabled||!lifetime?.enabled||lifetime.scope!==scope||current.current!==scope||after==null||flight.current||state.scope!==scope)return;
    const controller=new AbortController();flight.current=controller;
    const valid=()=>active.current===lifetime&&current.current===scope&&flight.current===controller&&!controller.signal.aborted;
    setState(old=>({...old,loading:true,error:null}));
    try{
      const data=await load(after,{signal:controller.signal});
      if(!valid())return;
      const window=cellWindowOf(data,after);
      if(!window||window.total!==view.total)throw Error('The cell list changed. Refresh the list.');
      const cells=appendCellWindow(view.cells,data.cells);
      if(cells.length!==after+data.cells.length)throw Error('The cell list changed. Refresh the list.');
      setState(old=>old.scope!==scope?old:{...old,cells,total:window.total,next:window.next,loading:false,error:null});
    }catch(error){if(valid())setState(old=>old.scope!==scope?old:{...old,loading:false,error:error.message});}
    finally{if(flight.current===controller)flight.current=null;}
  }
  return {cells:view.cells,accept,more,
    window:view.cells&&view.total!=null?{loaded:view.cells.length,total:view.total,loading:view.loading,error:view.error,disabled:!enabled,onMore:more}:null};
}
