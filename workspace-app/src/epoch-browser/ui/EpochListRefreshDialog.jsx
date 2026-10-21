import {useId,useRef} from 'react';
import {useRetainedModal} from '../../retainedWorkspaceViews.js';
import '../../annotations/ui/TagExchange.css';

export default function EpochListRefreshDialog({message,onRefresh,onClose}){
  const dialog=useRef(null),title=useId();useRetainedModal(dialog);
  return <dialog ref={dialog} className="tag-exchange-dialog" aria-labelledby={title} onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2 id={title}>Refresh epoch list</h2></header>
    <div className="tag-exchange-body"><p>{message}</p><p>Refresh the list to continue. Your saved query will stay the same.</p></div>
    <footer><button onClick={onClose}>Later</button><button className="primary" onClick={onRefresh}>Refresh epoch list</button></footer>
  </dialog>;
}
