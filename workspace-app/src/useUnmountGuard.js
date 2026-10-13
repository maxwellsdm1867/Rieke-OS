import {useLayoutEffect,useRef} from 'react';
import {registerUnmountGuard} from './desktopLifecycle.js';
import {useRetainedView} from './retainedWorkspaceViews.js';
export function useUnmountGuard(blocked,message){
 const current=useRef(null),token=useRef({}),view=useRetainedView();current.current=blocked?message:null;
 if(view)view.guards.set(token.current,current.current);
 useLayoutEffect(()=>{
  if(!view)return registerUnmountGuard(()=>current.current);
  const {guards,activity}=view,identity=token.current;
  return()=>{for(let current=activity;current;current=current.parent)if(!current.active)return;guards.delete(identity);};
 },[view?.guards,view?.activity]);
}
