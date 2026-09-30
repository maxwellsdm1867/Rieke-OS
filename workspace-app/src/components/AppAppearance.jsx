import {useEffect,useRef} from 'react';
import {X} from 'lucide-react';
import {iconSource} from '../appAppearance.js';
import './AppAppearance.css';
export default function AppAppearance({appearance}){
 const dialog=useRef(null);
 useEffect(()=>{if(appearance.open)dialog.current?.showModal();},[appearance.open]);
 if(!appearance.open)return null;
 return <dialog ref={dialog} className="app-appearance" aria-labelledby="app-appearance-title" onCancel={event=>{event.preventDefault();appearance.setOpen(false);}}><header><h2 id="app-appearance-title">Disco</h2><button autoFocus className="icon-button" onClick={()=>appearance.setOpen(false)} aria-label="Close About Disco"><X size={17}/></button></header><img src={appearance.source} alt="Disco application icon" width="96" height="96"/><p><strong>Data Inspection, Selection, Comparison Operations</strong></p><p>A Rieke Lab OS</p><details><summary>A little lab tradition</summary><p>Choose the classic Rieke emblem or return to the disco ball.</p><div className="app-icon-choices">{[['disco','Disco ball'],['rieke','Rieke emblem']].map(([value,label])=><button key={value} disabled={appearance.busy} aria-pressed={appearance.icon===value} onClick={()=>appearance.choose(value)}><img src={iconSource(value)} alt="" width="48" height="48"/>{label}</button>)}</div><p className="app-icon-note">The installed application keeps the default disco ball. Your choice updates the workspace and supported Dock or taskbar appearance.</p></details>{appearance.error&&<p role="alert">{appearance.error}</p>}</dialog>;
}
