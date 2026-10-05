// Presentation hints only: never retained rows, membership or mutation receipts.
export const INSPECTION_BRANCH_LIMIT=128;
export function inspectionNavigation(saved,scope,pageSize=60){
  const valid=saved?.scope===scope;
  const dates=valid&&Array.isArray(saved.dates)?saved.dates.filter(value=>typeof value==='string'&&value.length<=128).slice(-INSPECTION_BRANCH_LIMIT):[];
  const cells=valid&&Array.isArray(saved.cells)?saved.cells.filter(value=>typeof value==='string'&&value.length<=128).slice(-INSPECTION_BRANCH_LIMIT):[];
  const offsets=Object.fromEntries(cells.map(id=>[id,Number.isSafeInteger(saved.offsets?.[id])&&saved.offsets[id]>=0?Math.floor(saved.offsets[id]/pageSize)*pageSize:0]));
  return {scope,dates,cells,offsets,scrollTop:valid&&Number.isFinite(saved.scrollTop)?Math.max(0,saved.scrollTop):0};
}
export function inspectionPageOffset(offset,count,pageSize=60){return Math.min(offset||0,Math.floor(Math.max(0,(count||0)-1)/pageSize)*pageSize);}
export function toggleInspectionBranch(values,key,open){return [...values.filter(value=>value!==key),...(open?[key]:[])].slice(-INSPECTION_BRANCH_LIMIT);}

// Two ready layout frames, with a fresh membership/page predicate on BOTH.
// The caller cancels this operation on scope changes and newer user intent.
export function restoreInspectionScroll({pane,top,ready,requestFrame=requestAnimationFrame,cancelFrame=cancelAnimationFrame,observe,onRestored}){
  let frame=null,stopped=false,settled=0,disconnect=()=>{};
  const stop=()=>{stopped=true;if(frame!==null)cancelFrame(frame);frame=null;disconnect();};
  const schedule=()=>{if(!stopped&&frame===null)frame=requestFrame(tick);};
  const tick=()=>{
    frame=null;if(stopped)return;
    // Pending/error states sleep until membership or child DOM changes. A
    // failed request must not leave a 60Hz loop running for the life of a tab.
    if(!ready()){settled=0;return;}
    if(++settled<2){schedule();return;}
    pane.scrollTop=Math.min(Math.max(0,top),Math.max(0,pane.scrollHeight-pane.clientHeight));
    stop();onRestored?.(pane.scrollTop);
  };
  const watch=observe||((changed)=>{
    const observer=new MutationObserver(changed);
    observer.observe(pane,{subtree:true,childList:true,attributes:true});
    return()=>observer.disconnect();
  });
  disconnect=watch(()=>{settled=0;schedule();});
  schedule();return stop;
}
