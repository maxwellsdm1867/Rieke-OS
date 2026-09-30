export function annotationGroups(annotations={}){
  return {cell:Array.isArray(annotations.cell_tags)?annotations.cell_tags:[],epoch:Array.isArray(annotations.epoch_tags)?annotations.epoch_tags:[]};
}
export function annotationIndicator(record={},level=null){
  const groups=annotationGroups(record.annotations),cell=level==='epoch'?[]:groups.cell,epoch=level==='cell'?[]:groups.epoch,dataset=level==='cell'?[]:Array.isArray(record.curation?.tags)?record.curation.tags:[];
  const shared=cell.length+epoch.length;
  return {count:shared+dataset.length,cell:cell.length,epoch:epoch.length,dataset:dataset.length,
    title:[...cell.map(item=>`Cell: ${item.tag} · ${item.author_name||'Author not recorded'}`),...epoch.map(item=>`Epoch: ${item.tag} · ${item.author_name||'Author not recorded'}`),...dataset.map(tag=>`Dataset: ${tag}`)].join('\n')};
}
export function annotationChange({epoch,targetKind,profileUuid,annotations,tag,remove=false}){
  if(!['cell','epoch'].includes(targetKind)||!profileUuid)throw new Error('Choose a local profile before editing annotations.');
  const uuid=targetKind==='cell'?epoch?.cell_uuid:epoch?.epoch_uuid;
  if(!uuid||typeof tag!=='string'||!tag.trim())throw new Error('A recording identity and tag are required.');
  const revision=annotations?.revisions?.[targetKind]?.[profileUuid]??0;
  if(!Number.isSafeInteger(revision)||revision<0)throw new Error('Reload annotations before editing.');
  return {target_kind:targetKind,target_uuids:[uuid],profile_uuid:profileUuid,tags_add:remove?[]:[tag.trim()],tags_remove:remove?[tag]:[],expected_revisions:{[uuid]:revision}};
}
export function canRemoveAnnotation(chip,profileUuid){return !!profileUuid&&chip?.profile_uuid===profileUuid;}
export function annotationPredicate(scope,tag){
  if(!['cell','epoch','effective'].includes(scope)||typeof tag!=='string')throw new Error('Unknown annotation filter.');
  return {all:[{field:`annotations/${scope}/tags`,operator:'contains',value:tag}]};
}
export function bulkAnnotationChange({targetUuids,profileUuid,read,tag}){
  const ids=[...new Set(targetUuids)];if(!ids.length||ids.length>1000||!profileUuid||!tag.trim())throw new Error('Choose 1–1,000 epochs and a local profile.');
  const expected={};for(const uuid of ids){const row=read?.targets?.[uuid];if(!row||row.target_kind!=='epoch'||row.target_uuid!==uuid)throw new Error('Selected epoch annotations could not be verified.');const revision=row.revisions?.[profileUuid]??0;if(!Number.isSafeInteger(revision)||revision<0)throw new Error('Reload selected annotations before editing.');expected[uuid]=revision;}
  return {target_kind:'epoch',target_uuids:ids,profile_uuid:profileUuid,tags_add:[tag.trim()],tags_remove:[],expected_revisions:expected};
}

// Await the save receipt and retain the epoch if saving failed or focus changed.
export async function navigateAfterTagSave({draft,save,isCurrent,navigate,direction}){
  if(draft.trim()&&!await save(draft.trim()))return false;
  if(!isCurrent())return false;
  navigate(direction);return true;
}


// Colors are stable by tag text, independent of author or current row order.
export function compactAnnotationTags(record={},level='epoch'){
  const groups=annotationGroups(record.annotations),rows=level==='cell'?groups.cell:groups.epoch;
  const tags=new Map();
  for(const row of rows){
    const authors=tags.get(row.tag)||[];
    authors.push(row.author_name||'Author not recorded');tags.set(row.tag,authors);
  }
  if(level==='epoch')for(const tag of record.curation?.tags||[])tags.set(tag,[...(tags.get(tag)||[]),'Dataset tag']);
  return [...tags].map(([tag,authors])=>{
    return {tag,color:annotationTagColor(tag),title:`${tag} · ${[...new Set(authors)].join(', ')}`};
  });
}

export function annotationTagColor(tag){let hash=0;for(const char of tag)hash=(hash*31+char.codePointAt(0))>>>0;return hash%6;}
