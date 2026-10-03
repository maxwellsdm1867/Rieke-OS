// Presentation hints only: never retained rows, membership or mutation receipts.
export const INSPECTION_BRANCH_LIMIT=128;
export function inspectionNavigation(saved,scope){
  const valid=saved?.scope===scope;
  const dates=valid&&Array.isArray(saved.dates)?saved.dates.filter(value=>typeof value==='string'&&value.length<=128).slice(-INSPECTION_BRANCH_LIMIT):[];
  const cells=valid&&Array.isArray(saved.cells)?saved.cells.filter(value=>typeof value==='string'&&value.length<=128).slice(-INSPECTION_BRANCH_LIMIT):[];
  const offsets=Object.fromEntries(cells.map(id=>[id,Number.isSafeInteger(saved.offsets?.[id])&&saved.offsets[id]>=0?Math.floor(saved.offsets[id]/60)*60:0]));
  return {scope,dates,cells,offsets,scrollTop:valid&&Number.isFinite(saved.scrollTop)?Math.max(0,saved.scrollTop):0};
}
export function inspectionPageOffset(offset,count){return Math.min(offset||0,Math.floor(Math.max(0,(count||0)-1)/60)*60);}
export function toggleInspectionBranch(values,key,open){return [...values.filter(value=>value!==key),...(open?[key]:[])].slice(-INSPECTION_BRANCH_LIMIT);}

// Two ready layout frames, with a fresh membership/page predicate on BOTH.
// The caller cancels this operation on scope changes and newer user intent.
export function restoreInspectionScroll({pane,top,ready,requestFrame=requestAnimationFrame,cancelFrame=cancelAnimationFrame,onRestored}){
  let frame,stopped=false,settled=0;
  const tick=()=>{
    if(stopped)return;
    settled=ready()?settled+1:0;
    if(settled<2){frame=requestFrame(tick);return;}
    pane.scrollTop=Math.min(Math.max(0,top),Math.max(0,pane.scrollHeight-pane.clientHeight));
    onRestored?.(pane.scrollTop);
  };
  frame=requestFrame(tick);
  return()=>{stopped=true;cancelFrame(frame);};
}
