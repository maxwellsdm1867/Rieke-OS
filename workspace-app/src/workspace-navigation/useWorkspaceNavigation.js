import {useCallback,useEffect,useRef,useState} from 'react';
import {makeWorkspaceRoute,routeAddress,validWorkspaceRoute} from './workspaceNavigation.js';
const freshKey=()=>crypto.randomUUID();
/**
 * Bind route, history position and monotonically increasing user intent to this
 * mount. Restoration replaces history without granting merge consent; consuming
 * a matching merge request only removes its presentation hint. See AGENTS.md.
 */
export default function useWorkspaceNavigation(){
  const [location,setLocation]=useState(()=>{
    const saved=window.history.state?.riekeWorkspace;
    return saved&&validWorkspaceRoute(saved.route)&&Number.isInteger(saved.index)?saved:{route:makeWorkspaceRoute('overview',{},freshKey()),index:0};
  });
  const intent=useRef(0);
  const current=useRef(location),furthest=useRef(location.index);
  current.current=location;
  useEffect(()=>{
    window.history.replaceState({...window.history.state,riekeWorkspace:current.current},'',routeAddress(current.current.route));
    const receive=event=>{intent.current++;const next=event.state?.riekeWorkspace;if(next&&validWorkspaceRoute(next.route)&&Number.isInteger(next.index)){furthest.current=Math.max(furthest.current,next.index);setLocation(next);}};
    window.addEventListener('popstate',receive);return()=>window.removeEventListener('popstate',receive);
  },[]);
  const go=useCallback((page,details={})=>{
    intent.current++;
    const route=makeWorkspaceRoute(page,details,freshKey()),previous=current.current;
    const next={route,index:previous.index+1};
    window.history.pushState({...window.history.state,riekeWorkspace:next},'',routeAddress(route));
    furthest.current=next.index;current.current=next;setLocation(next);
  },[]);
  const consumeMergeIntent=useCallback(requestId=>{
    const previous=current.current;
    if(previous.route.workbench?.merge_intent?.request_uuid!==requestId)return false;
    const {merge_intent,...workbench}=previous.route.workbench;
    const next={...previous,route:{...previous.route,workbench}};
    window.history.replaceState({...window.history.state,riekeWorkspace:next},'',routeAddress(next.route));
    current.current=next;setLocation(next);return true;
  },[]);
  const restore=useCallback(route=>{
    if(!validWorkspaceRoute(route))return;
    const next={route,index:0};
    current.current=next;furthest.current=0;
    window.history.replaceState({...window.history.state,riekeWorkspace:next},'',routeAddress(route));
    setLocation(next);
  },[]);
  return {intent:()=>intent.current,route:location.route,go,restore,consumeMergeIntent,canBack:location.index>0,canForward:location.index<furthest.current,back:()=>{intent.current++;window.history.back();},forward:()=>{intent.current++;window.history.forward();}};
}
