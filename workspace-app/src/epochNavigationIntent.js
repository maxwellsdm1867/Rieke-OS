// A position intent survives page fetches. Repeated keys advance the intended
// position, not the last painted row; a late page may only resolve that intent.
export function epochIntentAt(index,total,pageSize=60){
  if(!Number.isInteger(total)||total<=0||!Number.isFinite(index))return null;
  const target=Math.max(0,Math.min(total-1,Math.trunc(index)));
  return {index:target,total,offset:Math.floor(target/pageSize)*pageSize};
}
export function advanceEpochIntent({page,focused,intent,direction}){
  if(direction!==1&&direction!==-1)return null;
  const local=page?.epochs?.findIndex(row=>row.epoch_uuid===focused)??-1;
  const index=intent?.index??(local<0?null:(page.offset||0)+local);
  return index===null?null:epochIntentAt(index+direction,intent?.total??page?.total);
}
export function epochAtIntent(page,intent){
  if(!page||!intent)return null;
  return page.epochs?.[intent.index-(page.offset||0)]?.epoch_uuid||null;
}
