import {useId,useRef} from 'react';
import {useRetainedModal} from '../../retainedWorkspaceViews.js';
import '../../annotations/ui/TagExchange.css';

export default function PinnedMembershipRemovalDialog({protocolName,count,stale=false,onConfirm,onClose}){
  const dialog=useRef(null),title=useId();useRetainedModal(dialog);
  const epochs=`${count.toLocaleString()} ${count===1?'epoch':'epochs'}`;
  return <dialog ref={dialog} className="tag-exchange-dialog" aria-labelledby={title} onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2 id={title}>Remove from pinned protocol?</h2></header>
    <div className="tag-exchange-body">
      <p>Remove <strong>{epochs}</strong> from <strong>{protocolName}</strong>?</p>
      <p>The recordings stay in your project. Other protocols and existing exported files remain unchanged.</p>
      <p>You can use Undo afterward to restore these epochs to this pinned protocol.</p>
      {stale&&<p role="alert">The selection or dataset changed. Cancel and review the current epochs before removing them.</p>}
    </div>
    <footer><button onClick={onClose}>Cancel</button><button className="primary" disabled={stale} onClick={onConfirm}>Remove {epochs}</button></footer>
  </dialog>;
}
