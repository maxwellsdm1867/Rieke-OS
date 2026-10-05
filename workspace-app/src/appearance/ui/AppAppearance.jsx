import {useEffect,useId,useRef} from 'react';
import {Check,Moon,Palette,Sun,X} from 'lucide-react';
import {iconSource} from '../appAppearance.js';
import {THEMES} from '../appearanceThemes.js';
import './AppAppearance.css';

function ThemeMiniature({palette,icon,half}){
 return <span className={`theme-miniature ${half?`theme-system-${half}`:''}`} data-palette={palette}>
  <span className="theme-mini-rail"><img src={iconSource(icon)} alt=""/></span><span className="theme-mini-sidebar"><i/><i/><i/></span><span className="theme-mini-content"><i/><span/><span/></span>
  {half&&<span className={`theme-time-icon theme-time-${half}`}>{half==='day'?<Sun size={14}/>:<Moon size={14}/>}</span>}
 </span>;
}


export function ThemePicker({appearance}){
 const name=useId();
 const errorStatus=appearance.errorPhase==='save'?'Your previous appearance is restored. The change was not saved.':appearance.errorPhase==='icon'?'Theme saved. The Dock or taskbar icon could not be updated.':'Saved appearance could not be loaded. You can try choosing a theme.';
 return <fieldset className="theme-picker" aria-busy={appearance.busy||appearance.loading}><legend>Color theme</legend><p className="theme-picker-help">Choose the workspace that feels right for you.</p><div className="theme-options">
  {THEMES.map(theme=><label key={theme.id} className={`theme-option ${appearance.theme===theme.id?'is-selected':''}`}>
   <input type="radio" name={name} value={theme.id} checked={appearance.theme===theme.id} disabled={appearance.loading} aria-disabled={appearance.busy||undefined} onChange={()=>{if(!appearance.busy)appearance.chooseTheme(theme.id);}}/>
   <span className={`theme-preview ${theme.id==='system'?'theme-system-preview':''}`} aria-hidden="true">
    {theme.id==='system'?<><ThemeMiniature palette="light" icon="disco" half="day"/><ThemeMiniature palette="dark" icon="disco" half="night"/></>:<ThemeMiniature palette={theme.id} icon={theme.icon}/>}
   </span>
   <span className="theme-option-name">{theme.name}{theme.id==='light'&&<small>Default</small>}<span className="theme-selection">{appearance.theme===theme.id&&<Check size={13}/>}</span></span>
   <span className="theme-option-description">{theme.description}</span>
  </label>)}
 </div><p className="appearance-save-note" role="status">{appearance.busy?'Saving appearance…':appearance.loading?'Loading appearance…':appearance.error?errorStatus:'Applies immediately. Remembered across projects.'}</p></fieldset>;
}

export function AppearanceButton({appearance,sidebar=false,compact=false}){
 const name=THEMES.find(theme=>theme.id===appearance.theme)?.name||'Light';
 return <button className={`appearance-entry ${compact?'appearance-rail-button':sidebar?'nav-item':''}`} onClick={()=>appearance.setOpen(true)} aria-label="Appearance" title={`Appearance · ${name}`} aria-haspopup="dialog" aria-expanded={appearance.open}><Palette size={17}/>{!compact&&<><span>Appearance</span><small>{name}</small></>}</button>;
}

export default function AppAppearance({appearance}){
 const dialog=useRef(null);
 useEffect(()=>{if(appearance.open)dialog.current?.showModal();},[appearance.open]);
 if(!appearance.open)return null;
 return <dialog ref={dialog} className="app-appearance" aria-labelledby="app-appearance-title" onCancel={event=>{event.preventDefault();appearance.setOpen(false);}}>
  <header><div><span className="appearance-eyebrow">MAKE IT YOURS</span><h2 id="app-appearance-title">Appearance</h2></div><button autoFocus className="icon-button" onClick={()=>appearance.setOpen(false)} aria-label="Close appearance"><X size={19}/></button></header>
  <ThemePicker appearance={appearance}/>
  <div className="appearance-about"><img src={appearance.source} alt={appearance.icon==='rieke'?'Classic Rieke emblem':'Disco ball'} width="56" height="56"/><div><strong>{appearance.theme==='fred'?'A little lab tradition':'Disco'}</strong><p>{appearance.theme==='fred'?'The Rieke emblem, in familiar purple.':'Data Inspection, Selection, Comparison Operations'}</p><small>A Rieke Lab OS</small></div></div>
  {appearance.error&&<p className="appearance-error" role="alert">{appearance.error}</p>}
 </dialog>;
}
