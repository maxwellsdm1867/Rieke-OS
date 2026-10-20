// A position intent survives page fetches. Repeated keys advance the intended
// position, not the last painted row; a late page may only resolve that intent.
export function epochIntentAt(index,total,pageSize=60){
  if(!Number.isInteger(total)||total<=0||!Number.isFinite(index))return null;
  const target=Math.max(0,Math.min(total-1,Math.trunc(index)));
  return {index:target,total,offset:Math.floor(target/pageSize)*pageSize};
}
export function advanceEpochIntent({page,focused,intent,direction,pageSize=60}){
  if(direction!==1&&direction!==-1)return null;
  const local=page?.epochs?.findIndex(row=>row.epoch_uuid===focused)??-1;
  const index=intent?.index??(local<0?null:(page.offset||0)+local);
  if(index===null)return null;
  const total=intent?.total??page?.total;
  // Pending counts: the page knows only whether more rows follow (has_more).
  if(total==null&&page&&Array.isArray(page.epochs)){
    const loadedEnd=(page.offset||0)+page.epochs.length,next=index+direction;
    if(next<0||next>=loadedEnd+(page.has_more===true?1:0))return null;
    return {index:next,total:null,offset:Math.floor(next/pageSize)*pageSize};
  }
  return epochIntentAt(index+direction,total,pageSize);
}
export function epochAtIntent(page,intent){
  if(!page||!intent)return null;
  return page.epochs?.[intent.index-(page.offset||0)]?.epoch_uuid||null;
}
