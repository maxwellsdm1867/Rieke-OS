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
  return [...dates.values()].sort((a,b)=>a.date.localeCompare(b.date));
}
export function epochTagOverview(epoch){
  return [
    ...(epoch.annotations?.cell_tags||[]).map(item=>`Cell: ${item.tag}`),
    ...(epoch.annotations?.epoch_tags||[]).map(item=>`Epoch: ${item.tag}`),
    ...(epoch.curation?.tags||[]).map(tag=>`Dataset: ${tag}`),
  ].join(' · ')||'No tags';
}
