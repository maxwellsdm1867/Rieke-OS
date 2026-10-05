// Presentation only: keep recorded labels and UUID identity intact.
export function recordedCellType(cell={}) {
  const value=cell.cell_type || cell.type;
  return value!=null && String(value).trim() ? String(value) : 'Unclassified';
}
export function isUnclassifiedType(type) {
  return /^(unclassified|unknown|not recorded|unknown cell type)$/i.test(type.trim());
}
export function distinctCells(cells=[]) {
  const seen=new Set();
  return cells.filter(cell=>{
    const id=cell.cell_uuid || cell.uuid;
    if(!id)return true;
    if(seen.has(id))return false;
    seen.add(id);return true;
  });
}
// Match only the established RGC categories, never infer type from cell labels.
export function cellTypeColor(type) {
  const key=String(type || '').trim().replace(/^RGC\\/i,'').replace(/[ _-]+/g,'-').toLowerCase();
  return ({'on-midget':'var(--cell-on-midget)','off-midget':'var(--cell-off-midget)',
    'on-parasol':'var(--cell-on-parasol)','off-parasol':'var(--cell-off-parasol)'})[key] || 'var(--ink-muted)';
}
