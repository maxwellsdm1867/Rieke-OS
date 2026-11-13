import {useState,useSyncExternalStore} from 'react';
import {createPortal} from 'react-dom';
import {mutationUndo} from '../mutationUndo.js';
import './UndoControls.css';
// Isolate undo availability notifications from the scientific workspace.
const removalKey=state=>state.removal?JSON.stringify([state.project,state.removal.protocolUuid,state.removal.revisionUuid]):null;
export default function UndoControls({onUndo}){
 useSyncExternalStore(mutationUndo.subscribe,mutationUndo.version);
 const [dismissed,setDismissed]=useState(null);
 const state=mutationUndo.view(),key=removalKey(state);
 const disabled=!state.count||state.busy||!!state.pending;
 const undoRemoval=()=>{
  const current=mutationUndo.view();
  if(key!==removalKey(current)||current.busy||current.pending)return;
  onUndo();
 };
 return <><button disabled={disabled} onClick={onUndo} title="Undo last tag, analysis inclusion or pinned membership edit (Cmd+Z / Ctrl+Z)">Undo edit</button>{state.message&&<span role="status" className="undo-status">{state.message}</span>}
  {key&&key!==dismissed&&createPortal(<aside className="pin-removal-notice" aria-label="Pinned protocol removal">
   <span role="status">{state.busy?'Restoring epochs…':`Removed ${state.removal.count.toLocaleString()} ${state.removal.count===1?'epoch':'epochs'} from pin`}</span>
   <button className="primary" disabled={disabled} onClick={undoRemoval} title="Restore these epochs to their pinned protocol">Undo</button>
   <button className="quiet pin-removal-dismiss" aria-label="Dismiss removal notice" onClick={()=>setDismissed(key)} title="Dismiss notice">×</button>
  </aside>,document.body)}
 </>;
}
