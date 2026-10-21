import {useEffect,useRef} from 'react';
import './CellsWindow.css';
// A bounded cell list: the next window loads when its marker scrolls into view.
export default function CellsWindow({loaded,total,loading=false,error=null,disabled=false,onMore}){
  const marker=useRef(null),more=Number.isInteger(total)&&loaded<total;
  const latest=useRef(null),entered=useRef(false);latest.current={loading,error,onMore};
  useEffect(()=>{
    if(disabled||!more||typeof IntersectionObserver==='undefined'||!marker.current)return;
    const observer=new IntersectionObserver(entries=>{
      const inside=entries.some(entry=>entry.isIntersecting),fresh=inside&&!entered.current;entered.current=inside;
      if(fresh&&!latest.current.loading&&!latest.current.error)latest.current.onMore();
    },{root:marker.current.closest('.tree-scroll'),rootMargin:'200px 0px'});
    observer.observe(marker.current);return()=>{observer.disconnect();entered.current=false;};
  },[more,disabled]);
  return <div ref={marker} className="inspection-cells-window" role="status">
    <span>{Number.isInteger(total)?`${loaded.toLocaleString()} of ${total.toLocaleString()} cells`:`${loaded.toLocaleString()} cells`}</span>
    {error?<><span role="alert">{error}</span><button disabled={disabled} onClick={onMore}>Retry</button></>:more&&<button disabled={disabled||loading} onClick={onMore}>{loading?'Loading cells…':'Load more cells'}</button>}
  </div>;
}

