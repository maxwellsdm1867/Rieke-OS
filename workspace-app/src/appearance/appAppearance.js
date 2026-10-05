import {useEffect,useRef,useState} from 'react';
import {api} from '../api.js';
import {desktopBridge} from '../desktopLifecycle.js';
import {applyTheme,cacheAppearance,normalizeAppearance,readCachedAppearance,watchSystemTheme} from './appearanceThemes.js';
export const iconSource=icon=>icon==='rieke'?'/rieke-emblem.png':'/disco-icon.png';
export function applyBrowserIcon(icon,documentObject=globalThis.document){
 const favicon=documentObject?.querySelector?.('link[rel="icon"]');
 if(!favicon)return false;
 favicon.setAttribute('href',iconSource(icon));
 return true;
}
export function useAppAppearance({request=api}={}){
 const [value,setValue]=useState(readCachedAppearance),[open,setOpen]=useState(false),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[errorPhase,setErrorPhase]=useState(null);
 const writing=useRef(false);
 useEffect(()=>{applyTheme(value);applyBrowserIcon(value.icon);return watchSystemTheme(value,()=>applyTheme(value));},[value]);
 useEffect(()=>{let alive=true;request('/app/appearance').then(async result=>{
  if(!alive)return;const next=normalizeAppearance(result);setValue(next);cacheAppearance(next);
  try{await desktopBridge()?.applyAppIcon?.(next.icon);}catch(e){if(alive){setError(e.message);setErrorPhase('icon');}}
 }).catch(e=>{if(alive){setError(e.message);setErrorPhase('load');}}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[request]);
 async function chooseTheme(theme){
  if(writing.current||loading||theme===value.theme)return;
  const previous=value,next=normalizeAppearance({theme});writing.current=true;setBusy(true);setError('');setErrorPhase(null);setValue(next);
  try{
   const saved=normalizeAppearance(await request('/app/appearance',{method:'POST',body:{theme:next.theme}}));setValue(saved);cacheAppearance(saved);
   // A Dock/taskbar failure must not undo a theme that the server already saved.
   try{await desktopBridge()?.applyAppIcon?.(saved.icon);}catch(e){setError(e.message);setErrorPhase('icon');}
  }
  catch(e){setValue(previous);setError(e.message);setErrorPhase('save');}
  finally{writing.current=false;setBusy(false);}
 }
 return{...value,source:iconSource(value.icon),open,setOpen,busy,loading,error,errorPhase,chooseTheme,
  choose:icon=>chooseTheme(icon==='rieke'?'fred':value.theme==='fred'?'light':value.theme)};
}
