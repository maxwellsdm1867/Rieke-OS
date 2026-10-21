import {useEffect,useState} from 'react';
import {Undo2,X} from 'lucide-react';
import {number} from '../../api.js';
import './MergeUndoToast.css';

// Non-blocking bottom-corner notice after a verified merge. It stays until
// dismissed or replaced by a newer merge; it never auto-hides.
export default function MergeUndoToast({controller,projectId}){
  const [state,setState]=useState(controller.state);
  useEffect(()=>controller.subscribe(setState),[controller]);
  if(!state||state.projectId!==projectId)return null;
  const label=state.phase==='undone'?(state.kind==='review'?'Review reopened':'Merge undone'):state.phase==='error'?state.message:state.phase==='undoing'?state.message:state.kind==='review'?`Finished reviewing ${state.protocolName}; ${number(state.count)} epochs left out.`:`Merged ${number(state.count)} ${state.count===1?'epoch':'epochs'} into ${state.protocolName}.`;
  return <div className="merge-undo-toast" role={state.phase==='error'?'alert':'status'} aria-live="polite">
    <span>{label}</span>
    {state.canUndo&&state.phase==='merged'&&<button onClick={()=>{void controller.undo();}}><Undo2 size={14} aria-hidden="true"/> Undo</button>}
    <button className="icon-button" aria-label="Dismiss merge notice" disabled={state.phase==='undoing'} onClick={()=>controller.dismiss()}><X size={14}/></button>
  </div>;
}
