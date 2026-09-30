import {recordingDate} from './recordingIdentity.js';

// Build the overview from the full cell summary, never an epoch page.
export function inspectionDates(cells=[]){
  const dates=new Map();
  for(const cell of cells){
    const date=recordingDate(cell);
    if(!dates.has(date))dates.set(date,{date,cells:[],epochs:0});
    const group=dates.get(date);
    group.cells.push(cell);
    group.epochs+=cell.epochs||0;
  }
  // A date and label can repeat across acquisitions. Preserve scientific
  // labels while giving otherwise indistinguishable rows a unique identity
  // qualifier. Compare adjacent sorted UUIDs rather than every pair of cells.
  for(const group of dates.values()){
    const labels=new Map(),qualifiers=new Map();
    for(const cell of group.cells){
      const label=cell.label||cell.cell_label||'Unlabeled cell';
      if(!labels.has(label))labels.set(label,new Set());
      if(typeof cell.cell_uuid==='string')labels.get(label).add(cell.cell_uuid);
    }
    const common=(left='',right='')=>{let size=0;while(size<left.length&&size<right.length&&left[size]===right[size])size++;return size;};
    for(const ids of labels.values()){
      if(ids.size<2)continue;
      const ordered=[...ids].sort();
      ordered.forEach((id,index)=>{
        const size=Math.max(8,common(id,ordered[index-1])+1,common(id,ordered[index+1])+1);
        qualifiers.set(id,id.slice(0,size)+(size<id.length?'…':''));
      });
    }
    group.cells=group.cells.map(cell=>qualifiers.has(cell.cell_uuid)?{...cell,identity_qualifier:qualifiers.get(cell.cell_uuid)}:cell);
  }
  return [...dates.values()].sort((a,b)=>a.date.localeCompare(b.date));
}
export function epochTagOverview(epoch){
  return [
    ...(epoch.annotations?.cell_tags||[]).map(item=>`Cell: ${item.tag}`),
    ...(epoch.annotations?.epoch_tags||[]).map(item=>`Epoch: ${item.tag}`),
    ...(epoch.curation?.tags||[]).map(tag=>`Dataset: ${tag}`),
  ].join(' · ')||'No tags';
}
