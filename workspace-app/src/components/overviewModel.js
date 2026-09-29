// Overview quantities are derived from source cells, never by summing overlapping cohorts.
export function overviewModel(data) {
  const cells = data.cells || [];
  const dates = new Map(), types = new Map();
  for (const cell of cells) {
    const date = cell.date || 'Not recorded';
    const group = dates.get(date) || {date, cells:0, epochs:0, duration:0};
    group.cells += 1; group.epochs += cell.epochs ?? cell.epoch_count ?? 0;
    if(typeof cell.duration_seconds!=='number'||!Number.isFinite(cell.duration_seconds)||cell.duration_seconds<0)group.duration=null;
    else if(group.duration!==null)group.duration+=cell.duration_seconds;
    dates.set(date,group);
    const type = cell.cell_type || cell.type || 'Unclassified';
    types.set(type,(types.get(type)||0)+1);
  }
  return {
    dates:[...dates.values()].sort((a,b)=>a.date.localeCompare(b.date)),
    dateCount:[...dates.keys()].filter(key=>key!=='Not recorded').length,
    unknownDateCells:dates.get('Not recorded')?.cells || 0,
    types:[...types].map(([type,count])=>({type,count})).sort((a,b)=>b.count-a.count||a.type.localeCompare(b.type)),
    totalCells:cells.length,
  };
}
