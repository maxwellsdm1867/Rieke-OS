import {useEffect,useRef} from 'react';
import {ListChecks,X} from 'lucide-react';
import './TagExchange.css';

export default function SelectionMaskDialog({busy,onClose,children}){
  const dialog=useRef(null);
  useEffect(()=>{const node=dialog.current;node.showModal();return()=>node.close();},[]);
  return <dialog ref={dialog} className="tag-exchange-dialog selection-mask-dialog" aria-labelledby="selection-mask-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
    <header><h2 id="selection-mask-title"><ListChecks size={18}/> Protocol selection mask</h2><button className="icon-button" disabled={busy} aria-label="Close selection mask" onClick={onClose}><X size={18}/></button></header>
    <div className="tag-exchange-body">{children}</div>
    <footer><button disabled={busy} onClick={onClose}>Done</button></footer>
  </dialog>;
}
