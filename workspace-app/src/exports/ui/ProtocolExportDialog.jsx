import {useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {Download,X} from 'lucide-react';
import './ExportSelectionDialog.css';

export default function ProtocolExportDialog({children,footer,onClose,busy}){
  const dialog=useRef(null);
  useEffect(()=>{const element=dialog.current;element.showModal();return()=>element.close();},[]);
  return createPortal(<dialog ref={dialog} className="export-selection-dialog protocol-export-dialog" aria-labelledby="protocol-export-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}><header><h2 id="protocol-export-title"><Download size={17}/> Export protocol</h2><button className="icon-button" disabled={busy} onClick={onClose} aria-label="Close protocol export"><X size={17}/></button></header><div className="protocol-export-body">{children}</div>{footer}</dialog>,document.body);
}
