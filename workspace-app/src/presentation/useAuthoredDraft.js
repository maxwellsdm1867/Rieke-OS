import {createContext,createElement,useCallback,useContext,useRef,useState} from 'react';
import {useRetainedView,useRetainedViewProtection} from '../retainedWorkspaceViews.js';
const ShellDraftContext=createContext(null);
const SHELL_ROUTE=Object.freeze({page:'project-shell',key:'project-shell'});
export function AuthoredDraftScope({presentation,children}){return createElement(ShellDraftContext.Provider,{value:{presentation,route:SHELL_ROUTE}},children);}
// Text/options use the existing project checkpoint. Null key is local-only.
// adopt hydrates canonical defaults without creating a draft; clear retires a
// confirmed save while leaving its displayed value alone. Neither grants consent.
export function useAuthoredDraft(key,initialValue){
 const retained=useRetainedView(),shell=useContext(ShellDraftContext),view=retained?.presentation?retained:shell,owner=view?.presentation,route=view?.route;
 const identity=JSON.stringify([route?.page,route?.protocol,route?.cell_uuid,route?.retainedViewKey||route?.key,key]);
 const initial=typeof initialValue==='function'?initialValue():initialValue;
 const read=()=>{try{return key&&owner?.readDraft?owner.readDraft(route,key):undefined;}catch{return undefined;}};
 const initialState=()=>{const saved=read();return {identity,value:saved??initial,baseline:initial,initialProp:initial,edited:saved!==undefined,error:null};};
 const [state,setState]=useState(initialState);let current=state;
 const hydrated=!state.edited?read():undefined;
 if(state.identity!==identity){current=initialState();setState(current);}
 else if(!state.edited&&(hydrated!==undefined||state.initialProp!==initial)){
  current={...state,value:hydrated??initial,baseline:initial,initialProp:initial,edited:hydrated!==undefined};setState(current);
 }
 const latest=useRef();latest.current={...current,owner,route,key};
 useRetainedViewProtection({dirty:!!current.error});
 const change=useCallback(next=>{
  const current=latest.current;if(current.identity!==identity||current.owner!==owner)return;
  const value=typeof next==='function'?next(current.value):next;let error=null;
  if(current.key&&current.owner?.rememberDraft)try{current.owner.rememberDraft(current.route,current.key,value===current.baseline?undefined:value);}catch(failure){error=failure;}
  const updated={...current,value,edited:value!==current.baseline,error};latest.current=updated;setState(updated);
 },[identity,owner]);
 const adopt=useCallback(value=>{const current=latest.current;if(current.identity!==identity||current.owner!==owner||current.edited)return;const updated={...current,value,baseline:value,error:null};latest.current=updated;setState(updated);},[identity,owner]);
 const clear=useCallback(()=>{
  const current=latest.current;let error=null;
  if(key&&owner?.rememberDraft)try{owner.rememberDraft(route,key,undefined);}catch(failure){error=failure;}
  if(current.identity!==identity||current.owner!==owner)return;
  const updated={...current,baseline:current.value,edited:!!error,error};latest.current=updated;setState(updated);
 },[identity,owner,route]);
 return [current.value,change,{edited:current.edited,error:current.error,adopt,clear}];
}
