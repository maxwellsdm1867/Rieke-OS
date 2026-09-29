import {createContext,useCallback,useContext,useEffect,useRef,useState} from 'react';
import {LoaderCircle} from 'lucide-react';
import {scheduleLoadingNotice} from '../loadingNotice.js';
import './NavigationLoading.css';

const LoadingContext=createContext(null);
// One indicator spans list, metadata and samples. Short handoffs between their
// requests should neither flash the indicator nor restart its grace period.
export function NavigationLoadingProvider({children}){
  const requests=useRef(new Set());
  const [busy,setBusy]=useState(false);
  const report=useCallback((id,pending)=>{
    if(pending)requests.current.add(id);else requests.current.delete(id);
    setBusy(requests.current.size>0);
  },[]);
  return <LoadingContext.Provider value={{report,busy}}>{children}</LoadingContext.Provider>;
}
export function useNavigationLoading(pending){
  const context=useContext(LoadingContext),report=context?.report;
  const id=useRef(Symbol('navigation request'));
  useEffect(()=>{report?.(id.current,!!pending);return()=>report?.(id.current,false);},[report,pending]);
  return !!context;
}
export function useDelayedLoading(pending){
  const [visible,setVisible]=useState(false);
  useEffect(()=>scheduleLoadingNotice(pending,setVisible),[pending]);
  return visible;
}
export function NavigationLoadingNotice(){
  const context=useContext(LoadingContext);
  const visible=useDelayedLoading(context?.busy);
  return <div className="navigation-loading-slot" role="status" aria-live="polite" aria-atomic="true">
    {visible&&<span title="The previous view stays visible and inactive until the selected epoch is ready."><LoaderCircle size={13}/> Updating epoch…</span>}
  </div>;
}
