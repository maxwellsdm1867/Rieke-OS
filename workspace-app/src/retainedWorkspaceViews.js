import {Activity,createContext,createElement,useCallback,useContext,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {useAnnotationProfile} from './annotations/annotationProfile.js';
import {hasPendingDesktopWrites,registerUnmountGuard} from './desktopLifecycle.js';

const ViewContext=createContext(null);
export const RETAINED_VIEW_LIMIT=8;
const destinationKey=route=>JSON.stringify([route.page,route.page==='protocol'?route.protocol:route.page==='cell-qc'?route.cell_uuid:null]);

// Presentation lifetime is separate from server receipts. Each entry keeps its
// own route and callbacks; current actor/revision props still flow from App.
export function RetainedWorkspaceViews({route,projectId,projectPath,presentation,render,limit=RETAINED_VIEW_LIMIT}){
  const projectScope=JSON.stringify([projectId,projectPath]);
  const profile=useAnnotationProfile();
  const actor=profile.loading?'loading':profile.error?'unavailable':profile.profileUuid||'browse-only';
  const sequence=useRef(0);
  const [stored,setStored]=useState(()=>({projectScope,entries:[]}));
  let entries=stored.projectScope===projectScope?stored.entries:[];
  const sameDestination=entry=>destinationKey(entry.route)===destinationKey(route);
  const existing=entries.find(entry=>sameDestination(entry)&&entry.route.key===route.key)||
    (route.retainedViewKey?entries.find(entry=>sameDestination(entry)&&entry.route.key===route.retainedViewKey):null);
  let identity=existing?.identity;
  if(!existing||stored.projectScope!==projectScope||entries.at(-1)!==existing||existing.route!==route){
    const next=existing?{...existing,route}:{identity:`view-${++sequence.current}`,route,version:1,protection:new Map(),guards:new Map(),activity:{active:true},values:{}};
    identity=next.identity;
    entries=[...entries.filter(entry=>entry!==existing),next];
    while(entries.length>limit){
      if(hasPendingDesktopWrites())break;
      const removable=entries.findIndex(entry=>entry!==next&&![...entry.guards.values()].some(Boolean)&&![...entry.protection.values()].some(value=>value.dirty||value.busy));
      if(removable<0)break; // A dirty/busy view is never silently discarded.
      entries.splice(removable,1);
    }
    setStored({projectScope,entries});
  }
  return entries.map(entry=>createElement(RetainedDestination,{key:entry.identity+':'+entry.version,entry,
    active:entry.identity===identity,identity:JSON.stringify([projectScope,actor]),presentation,render}));
}

function RetainedDestination({entry,active,identity,presentation,render}){
  const ownRoute=entry.route;
  const remember=useCallback(value=>presentation.remember(ownRoute,value),[presentation,ownRoute.page,ownRoute.key,ownRoute.protocol]);
  useLayoutEffect(()=>registerUnmountGuard(()=>[...entry.guards.values()].find(Boolean)||null),[entry.guards]);
  if(entry.activity.active!==active||entry.activity.routeKey!==ownRoute.key)entry.activity.token={};
  entry.activity.active=active;entry.activity.routeKey=ownRoute.key;
  const token=entry.activity.token;
  const whenCurrent=callback=>(...args)=>entry.activity.active&&entry.activity.token===token?callback(...args):false;
  const context={active,identity,presentation,route:ownRoute,protection:entry.protection,guards:entry.guards,activity:entry.activity};
  const pending=hasPendingDesktopWrites()||[...entry.protection.values()].some(value=>value.busy);
  return createElement(ViewContext.Provider,{value:context},
    createElement(Activity,{mode:active||pending?'visible':'hidden'},
      createElement('div',{'data-workspace-view':entry.route.key,'data-workspace-active':String(active),
        className:'retained-workspace-view',hidden:!active,inert:!active?true:undefined},render(entry.route,{active,remember,values:entry.values,whenCurrent}))));
}

export function useRetainedView(){return useContext(ViewContext);}

export function useRetainedModal(dialog,open=true){
  const view=useContext(ViewContext),visible=view?.active!==false;
  useLayoutEffect(()=>{
    if(!visible||!open)return;
    const node=dialog.current;node?.showModal?.();
    return()=>node?.close?.();
  },[dialog,visible,open]);
}

export function RetainedWorkspacePanel({name,visible,children}){
  const owner=useContext(ViewContext),[visited,setVisited]=useState(visible);
  const activity=useRef({active:visible});activity.current.active=visible;activity.current.parent=owner?.activity;
  if(visible&&!visited)setVisited(true);
  if(!visible&&!visited)return null;
  const pending=hasPendingDesktopWrites()||[...(owner?.protection.values()||[])].some(value=>value.busy);
  return createElement(ViewContext.Provider,{value:owner?{...owner,active:owner.active&&visible,activity:activity.current}:null},
    createElement(Activity,{mode:visible||pending?'visible':'hidden'},
      createElement('div',{'data-retained-panel':name,'data-retained-panel-active':String(visible),
        className:'retained-workspace-panel',hidden:!visible,inert:!visible?true:undefined},children)));
}

// Retain the last protected state while Activity disconnects effects. A later
// successful save/render clears it. The entry owns the map and its destruction;
// hiding an unsaved editor cannot accidentally make that editor evictable.
export function useRetainedViewProtection(protectedState){
  const view=useContext(ViewContext),token=useRef({});
  if(view)view.protection.set(token.current,typeof protectedState==='object'?{dirty:!!protectedState.dirty,busy:!!protectedState.busy}:{dirty:!!protectedState,busy:false});
  useLayoutEffect(()=>{
    if(!view)return;
    const {protection,activity}=view,identity=token.current;
    return()=>{for(let current=activity;current;current=current.parent)if(!current.active)return;protection.delete(identity);};
  },[view?.protection,view?.activity]);
}

// Only completed presentation reads may skip an Activity effect restart. Scoped
// pages, deletion plans and all custom request owners keep their original
// freshness path. This is deliberately not a generic GET cache. The canonical
// main protocol browse descriptor and epoch pages are retained on tab return
// when path and revision are unchanged: every write they enable still carries
// its query revision and binding version and fails closed at action time.
export function retainablePresentationRead(path){
  return typeof path==='string'&&(
    /^\/protocols\/[^/?]+\?projection=browse$/.test(path)||
    /^\/protocols\/[^/?]+\/epochs\?/.test(path)||
    /^\/(?:events|exports|search-presets|explore\/revisions)(?:\?|$)/.test(path)||
    /^\/(?:metadata\/fields|explore\/predicate-fields)$/.test(path)||
    /^\/cells\/[^/?]+\/qc(?:\?|$|\/(?:response|response-summary)(?:\?|$))/.test(path)
  );
}

// Portals escape the hidden panel DOM. Keep their state mounted, but carry the
// originating panel visibility into the shared header (including pending writes).
export function RetainedPortal({target,children}){
  const view=useContext(ViewContext),active=view?.active!==false;
  return createPortal(createElement('div',{'data-retained-portal-active':String(active),
    hidden:!active,inert:!active?true:undefined,style:{display:active?'contents':'none'}},children),target);
}
