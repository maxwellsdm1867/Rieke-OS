import {selectionDecisions,saveWorkbenchDecisions,previewWorkbench,workbenchPreviewCounts} from './workbenchAuthority.js';
export function exactSelectedIds(ids){
  if(!Array.isArray(ids)||!ids.length||ids.length>1000||ids.some(id=>typeof id!=='string'||!id)||new Set(ids).size!==ids.length)throw Error('Choose between 1 and 1,000 distinct incoming epochs.');
  return Object.freeze([...ids]);
}
export function selectedReview(context,selection){
  const ids=exactSelectedIds(selection),draft=context?.draft;
  if(!draft||draft.decisions_truncated!==false||!Array.isArray(draft.decisions)||draft.decisions_total!==draft.decisions.length)throw Error('The complete review draft is unavailable. Refresh before merging or exporting.');
  const decisions=new Map(draft.decisions.map(value=>[value.epoch_uuid,value]));
  if(decisions.size!==draft.decisions.length)throw Error('The review draft contains duplicate decisions. Refresh before continuing.');
  return {ids,unreviewed:ids.filter(id=>!decisions.get(id)?.reviewed),excluded:ids.filter(id=>decisions.get(id)?.excluded)};
}
// Capture UUID intent before any save. Only explicit review can add reviewed
// flags. Exclusions and the separate acceptance/recovery protocol stay intact.
export async function prepareSelectedIncoming({root,context,ids,review=false},request,onCommitted=()=>{}){
  const check=selectedReview(context,ids);
  if(check.excluded.length)throw Error(`${check.excluded.length} selected epochs are excluded. Adjust the selection or explicitly change those exclusions before continuing.`);
  if(check.unreviewed.length&&!review)throw Error('Review the selected epochs before continuing.');
  const previous=context.draft.decisions.filter(value=>value.selected).map(value=>value.epoch_uuid);
  const decisions=selectionDecisions(previous,check.ids).map(value=>review&&value.selected?{...value,reviewed:true}:value);
  const saved=await saveWorkbenchDecisions({root,context,decisions,selectionMode:'selected'},request,onCommitted);
  const preview=await previewWorkbench(root,saved,'selected',request,onCommitted);
  workbenchPreviewCounts(preview);
  if(preview.selected_epoch_count!==check.ids.length)throw Error('The preview does not include every selected epoch. Refresh and inspect the selection; no merge or export was submitted.');
  return preview;
}
// Bounded exact browsing predicate: never a saved draft decision.
export function selectedViewFilters(filters,selection){
  const ids=exactSelectedIds(selection),parts=[];
  for(let offset=0;offset<ids.length;offset+=64)parts.push({field:'epoch',operator:'in',value:ids.slice(offset,offset+64)});
  const selected=parts.length===1?parts[0]:{any:parts};
  const original=typeof filters?.metadata_predicate==='string'?JSON.parse(filters.metadata_predicate):filters?.metadata_predicate;
  const predicate=original?{all:[original,selected]}:selected;
  function size(node,depth=1){const children=node.all||node.any||(node.not?[node.not]:[]),sizes=children.map(child=>size(child,depth+1));return {count:1+sizes.reduce((sum,child)=>sum+child.count,0),depth:Math.max(depth,...sizes.map(child=>child.depth))};}
  const bound=size(predicate);
  if(bound.count>128||bound.depth>8)throw Error('This filter is too complex to add View selected. Simplify it first.');
  return {...filters,metadata_predicate:JSON.stringify(predicate)};
}
