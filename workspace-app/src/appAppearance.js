import {useEffect,useState} from 'react';
import {api} from './api.js';
import {desktopBridge} from './desktopLifecycle.js';
export const iconSource=icon=>icon==='rieke'?'/rieke-emblem.png':'/disco-icon.png';
export function applyBrowserIcon(icon,documentObject=globalThis.document){
 const favicon=documentObject?.querySelector?.('link[rel="icon"]');
 if(!favicon)return false;
 favicon.setAttribute('href',iconSource(icon));
 return true;
}
export function useAppAppearance(){
 const [icon,setIcon]=useState('disco'),[open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{applyBrowserIcon(icon);},[icon]);
 useEffect(()=>{let alive=true;api('/app/appearance').then(async result=>{if(!alive)return;setIcon(result.icon);await desktopBridge()?.applyAppIcon?.(result.icon);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[]);
 async function choose(next){if(busy||next===icon)return;setBusy(true);setError('');try{const result=await api('/app/appearance',{method:'POST',body:{icon:next}});setIcon(result.icon);await desktopBridge()?.applyAppIcon?.(result.icon);}catch(e){setError(e.message);}finally{setBusy(false);}}
 return{icon,source:iconSource(icon),open,setOpen,busy,error,choose};
}
