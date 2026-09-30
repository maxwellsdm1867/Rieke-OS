import {useCallback,useEffect,useRef,useState} from 'react';
import {makeWorkspaceRoute,routeAddress,validWorkspaceRoute} from './workspaceNavigation.js';
const freshKey=()=>crypto.randomUUID();
export default function useWorkspaceNavigation(){
  const [location,setLocation]=useState(()=>{
    const saved=window.history.state?.riekeWorkspace;
    return saved&&validWorkspaceRoute(saved.route)&&Number.isInteger(saved.index)?saved:{route:makeWorkspaceRoute('overview',{},freshKey()),index:0};
  });
  const current=useRef(location),furthest=useRef(location.index);
  current.current=location;
  useEffect(()=>{
    window.history.replaceState({...window.history.state,riekeWorkspace:current.current},'',routeAddress(current.current.route));
    const receive=event=>{const next=event.state?.riekeWorkspace;if(next&&validWorkspaceRoute(next.route)&&Number.isInteger(next.index)){furthest.current=Math.max(furthest.current,next.index);setLocation(next);}};
    window.addEventListener('popstate',receive);return()=>window.removeEventListener('popstate',receive);
  },[]);
  const go=useCallback((page,details={})=>{
    const route=makeWorkspaceRoute(page,details,freshKey()),previous=current.current;
    const next={route,index:previous.index+1};
    window.history.pushState({...window.history.state,riekeWorkspace:next},'',routeAddress(route));
    furthest.current=next.index;current.current=next;setLocation(next);
  },[]);
  const restore=useCallback(route=>{
    if(!validWorkspaceRoute(route))return;
    const next={route,index:0};
    current.current=next;furthest.current=0;
    window.history.replaceState({...window.history.state,riekeWorkspace:next},'',routeAddress(route));
    setLocation(next);
  },[]);
  return {route:location.route,go,restore,canBack:location.index>0,canForward:location.index<furthest.current,back:()=>window.history.back(),forward:()=>window.history.forward()};
}
