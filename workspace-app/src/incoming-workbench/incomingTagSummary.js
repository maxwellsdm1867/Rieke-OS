import {annotationTagColor} from "../annotations/annotationTags.js";

// The existing frozen epoch page is the authority, not Main or a sum of tags.
// Counts describe this bounded page, including inherited cell tags, once per UUID.
export function incomingTagSummary(page){
  if(!Array.isArray(page?.epochs)||!Number.isSafeInteger(page.total)||page.total<0)return null;
  const epochs=new Set(),cells=new Set(),taggedEpochs=new Set(),taggedCells=new Set(),tags=new Map(),cellTags=new Map();
  for(const row of page.epochs){
    if(!row?.epoch_uuid||!row.cell_uuid||!Array.isArray(row.annotations?.cell_tags)||!Array.isArray(row.annotations?.epoch_tags))return null;
    epochs.add(row.epoch_uuid);cells.add(row.cell_uuid);
    for(const kind of ['cell','epoch'])for(const tag of row.annotations[`${kind}_tags`]){
      if(typeof tag.tag!=='string'||!tag.tag)return null;
      let value=tags.get(tag.tag);
      if(!value){value={tag:tag.tag,color:annotationTagColor(tag.tag),epochs:new Set(),cells:new Set(),authors:new Map()};tags.set(tag.tag,value);}
      value.epochs.add(row.epoch_uuid);value.cells.add(row.cell_uuid);
      value.authors.set(JSON.stringify([kind,tag.profile_uuid||null,tag.author_name||null]),{kind,profile_uuid:tag.profile_uuid||null,name:tag.author_name||'Author not recorded'});
      taggedEpochs.add(row.epoch_uuid);taggedCells.add(row.cell_uuid);
      if(kind==='cell'){
        const recorded=cellTags.get(row.cell_uuid)||new Map();
        recorded.set(JSON.stringify([tag.tag,tag.profile_uuid||null,tag.author_name||null]),tag);cellTags.set(row.cell_uuid,recorded);
      }
    }
  }
  if(epochs.size>page.total)return null;
  return {loaded:epochs.size,total:page.total,cells:taggedCells.size,epochs:taggedEpochs.size,
    cellTags:Object.fromEntries([...cellTags].map(([id,values])=>[id,[...values.values()]])),
    tags:[...tags.values()].map(value=>({...value,cells:value.cells.size,epochs:value.epochs.size,authors:[...value.authors.values()]})).sort((a,b)=>b.epochs-a.epochs||a.tag.localeCompare(b.tag))};
}
