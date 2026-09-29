import {useLayoutEffect,useRef} from 'react';
import {LoaderCircle,AlertTriangle} from 'lucide-react';
import './StableContent.css';
import {useNavigationLoading,useDelayedLoading} from './NavigationLoading.jsx';

// Keep committed content mounted during navigation. It is deliberately inert:
// old metadata must never be actionable as if it belonged to the new selection.
export default function StableContent({data,loading,error,retry,children,label='Loading selected epoch',className='',scope='',blocked=false}){
  const committed=useRef(null);
  const ready=!!data&&!loading&&!error&&!blocked;
  useLayoutEffect(()=>{if(ready)committed.current={scope,children};else if(!loading&&!error&&!blocked)committed.current=null;},[ready,scope,children,loading,error,blocked]);
  const previous=committed.current?.scope===scope?committed.current.children:null;
  const waiting=!!loading||!!error||blocked;
  const coordinated=useNavigationLoading(loading&&!error);
  const showLoading=useDelayedLoading(loading&&!coordinated);
  return <div className={`stable-content ${className}`} aria-busy={!!loading}>
    <div className="stable-content-body" inert={waiting?'':undefined} aria-hidden={waiting?true:undefined}>
      {waiting?(previous||<div className="stable-content-placeholder"/>):children}
    </div>
    {(error||showLoading)&&<div className={`stable-content-notice ${error?'failed':''}`} role={error?'alert':'status'}>
      {error?<AlertTriangle size={15}/>:<LoaderCircle size={15}/>}
      <span>{error||label}{previous&&!error?' · previous view':''}</span>
      {error&&retry&&<button onClick={retry}>Retry</button>}
    </div>}
  </div>;
}
