// Display only facts returned by a successful durable annotation POST. Never
// invent a protocol membership/query revision from an annotation receipt.
const invalid=()=>{throw new Error('The saved annotation response could not be verified. Refresh tags before editing again.');};
const record=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const text=value=>typeof value==='string'&&value.length>0;
const revision=value=>Number.isSafeInteger(value)&&value>=0;
export const RECEIPT_LIMITS={targets:64,bytes:4*1024*1024};

export function confirmAnnotationReceipt(result,request){
  const ids=request?.target_uuids,kind=request?.target_kind,profile=request?.profile_uuid;
  if(!['cell','epoch'].includes(kind)||!text(profile)||!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||ids.some(id=>!text(id))||!record(request.expected_revisions))invalid();
  if(result?.persistence&&result.persistence.database!=='committed')invalid();
  if(!revision(result?.changed)||result.changed>ids.length||!record(result.targets)||Object.keys(result.targets).length!==ids.length)invalid();
  const targets=[];
  for(const id of ids){
    const value=result.targets[id],expected=request.expected_revisions[id];
    if(!revision(expected)||!record(value)||value.target_kind!==kind||value.target_uuid!==id||!record(value.revisions)||!Array.isArray(value.tags)||(value.revisions[profile]??0)<expected)invalid();
    for(const [author,version] of Object.entries(value.revisions))if(!text(author)||!revision(version)||version<1)invalid();
    const seen=new Set();
    for(const chip of value.tags){
      if(!record(chip)||chip.target_kind!==kind||chip.target_uuid!==id||!text(chip.profile_uuid)||!text(chip.author_name)||!text(chip.tag)||!chip.tag.trim()||[...chip.tag].length>255||!revision(chip.revision)||chip.revision<1||chip.revision!==value.revisions[chip.profile_uuid])invalid();
      const key=JSON.stringify([chip.profile_uuid,chip.tag]);if(seen.has(key))invalid();seen.add(key);
    }
    targets.push({target_kind:kind,target_uuid:id,revisions:{...value.revisions},tags:value.tags.map(chip=>({...chip}))});
  }
  return {version:1,targets};
}
export function fastAnnotationReceipt(receipt){return receipt?.version===1&&receipt.targets.length<=20&&JSON.stringify(receipt.targets).length*2<=RECEIPT_LIMITS.bytes;}
export function mergeAnnotationReceipts(previous,receipt,limits=RECEIPT_LIMITS){
  const next=new Map(previous);let bytes=[...next.values()].reduce((sum,item)=>sum+item.bytes,0);
  for(const target of receipt.targets){
    const key=JSON.stringify([target.target_kind,target.target_uuid]),size=JSON.stringify(target).length*2;
    if(next.has(key)){bytes-=next.get(key).bytes;next.delete(key);}
    if(size<=limits.bytes){next.set(key,{target,bytes:size});bytes+=size;}
    while(next.size>limits.targets||bytes>limits.bytes){const first=next.keys().next().value;bytes-=next.get(first).bytes;next.delete(first);}
  }
  return next;
}
export function applyAnnotationReceipts(epoch,store){
  if(!epoch?.annotations||!store.size)return epoch;
  const original=epoch.annotations,annotations={...original,revisions:{...original.revisions}};let changed=false;
  for(const kind of ['cell','epoch']){
    const id=kind==='cell'?epoch.cell_uuid:epoch.epoch_uuid,target=store.get(JSON.stringify([kind,id]))?.target;
    if(!target)continue;
    let chips=original[`${kind}_tags`]||[],versions=original.revisions?.[kind]||{};
    for(const [profile,version] of Object.entries(target.revisions)){
      if(version<(versions[profile]??0))continue;
      chips=[...chips.filter(chip=>chip.profile_uuid!==profile),...target.tags.filter(chip=>chip.profile_uuid===profile)];
      versions={...versions,[profile]:version};changed=true;
    }
    annotations[`${kind}_tags`]=chips;annotations.revisions[kind]=versions;
  }
  if(!changed)return epoch;
  annotations.effective_tags=[...(annotations.cell_tags||[]),...(annotations.epoch_tags||[])];
  return {...epoch,annotations};
}
export function annotationFilterNeedsRefresh(filters={}){return ['tag','tagged','tag_predicate'].some(key=>Object.hasOwn(filters,key));}
