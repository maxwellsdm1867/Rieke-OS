import {useRef,useState} from 'react';
import {appendCellWindow,cellWindowOf} from './cellWindows.js';

// Holds a windowed cell list for one scope: accept(firstResponse) installs the
// first window, more() requests the next one through load(cellsAfter). A late
// window from an earlier scope is ignored. `window` feeds CellsWindow.
export function useCellWindows(scopeKey,load){
  const [state,setState]=useState({scope:null,cells:null,total:null,next:null,loading:false,error:null});
  const current=useRef(scopeKey);current.current=scopeKey;
  const view=state.scope===scopeKey?state:{scope:scopeKey,cells:null,total:null,next:null,loading:false,error:null};
  function accept(data){
    if(!Array.isArray(data?.cells))return;
    const window=cellWindowOf(data);
    setState(old=>{
      // Later epoch pages repeat the first window; keep windows already loaded.
      const kept=window&&old.scope===scopeKey&&old.cells&&old.total===window.total&&old.cells.length>data.cells.length&&data.cells.every((cell,index)=>old.cells[index]?.cell_uuid===cell.cell_uuid);
      return kept?old:{scope:scopeKey,cells:data.cells,total:window?.total??data.cells.length,next:window?.next??null,loading:false,error:null};
    });
  }
  async function more(){
    const scope=scopeKey,after=view.next;
    if(!after||view.loading||state.scope!==scope)return;
    setState(old=>({...old,loading:true,error:null}));
    try{
      const data=await load(after);
      if(current.current!==scope)return;
      if(!Array.isArray(data?.cells))throw Error('The next cells could not be loaded. Refresh the list.');
      const window=cellWindowOf(data);
      setState(old=>old.scope!==scope?old:{...old,cells:appendCellWindow(old.cells,data.cells),total:window?.total??old.total,next:window?.next??null,loading:false,error:null});
    }catch(error){if(current.current===scope)setState(old=>old.scope!==scope?old:{...old,loading:false,error:error.message});}
  }
  return {cells:view.cells,accept,more,
    window:view.cells&&view.total!=null?{loaded:view.cells.length,total:view.total,loading:view.loading,error:view.error,onMore:more}:null};
}
