import {useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import './ProjectSetupDialog.css';

export default function ProjectSetupDialog({onClose,busy=false,children}){
  const dialog=useRef(null),busyRef=useRef(busy),closeRef=useRef(onClose);
  busyRef.current=busy;closeRef.current=onClose;
  useEffect(()=>{
    const element=dialog.current,previousFocus=document.activeElement;
    element.showModal();
    return()=>{element.close();if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});};
  },[]);
  function containTab(event){
    if(event.key!=='Tab')return;
    const controls=[...dialog.current.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex]:not([tabindex="-1"]):not(:disabled)')].filter(element=>element.getClientRects().length);
    const first=controls[0],last=controls.at(-1),active=document.activeElement;
    if(!first){event.preventDefault();dialog.current.focus();}
    else if(event.shiftKey&&(active===first||active===dialog.current)){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&active===last){event.preventDefault();first.focus();}
  }
  return createPortal(<dialog ref={dialog} className="project-setup-dialog" aria-label="Project setup" aria-busy={busy} tabIndex={-1} onKeyDown={containTab} onCancel={event=>{event.preventDefault();if(!busyRef.current)closeRef.current?.();}}>
    {children}
  </dialog>,document.body);
}
