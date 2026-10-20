import {useEffect,useRef} from 'react';
import './CellsWindow.css';
// A bounded cell list: the next window loads when its marker scrolls into view.
export default function CellsWindow({loaded,total,loading=false,error=null,onMore}){
  const marker=useRef(null),more=Number.isInteger(total)&&loaded<total;
  useEffect(()=>{
    if(!more||loading||error||typeof IntersectionObserver==='undefined'||!marker.current)return;
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))onMore();},{root:marker.current.closest('.tree-scroll'),rootMargin:'200px 0px'});
    observer.observe(marker.current);return()=>observer.disconnect();
  },[more,loading,error,loaded]);
  return <div ref={marker} className="inspection-cells-window" role="status">
    <span>{Number.isInteger(total)?`${loaded.toLocaleString()} of ${total.toLocaleString()} cells`:`${loaded.toLocaleString()} cells`}</span>
    {error?<><span role="alert">{error}</span><button onClick={onMore}>Retry</button></>:more&&<button disabled={loading} onClick={onMore}>{loading?'Loading cells…':'Load more cells'}</button>}
  </div>;
}

