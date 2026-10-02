import {useLayoutEffect,useRef} from 'react';
import {registerUnmountGuard} from './desktopLifecycle.js';
export function useUnmountGuard(blocked,message){
 const current=useRef(null);current.current=blocked?message:null;
 useLayoutEffect(()=>registerUnmountGuard(()=>current.current),[]);
}
