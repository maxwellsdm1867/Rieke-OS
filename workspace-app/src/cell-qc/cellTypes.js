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
// Exact presentation aliases only; never infer a type from a cell name or candidate label.
export function cellTypePresentation(type) {
  const parts=String(type || '').trim().toLowerCase().split(/[\\/]+/);
  const key=parts.pop().trim().replace(/[ _-]+/g,'-');
  const prefix=parts.join('/');
  const ganglion=/^(on|off)-(midget|parasol)$/.test(key);
  if(ganglion && (!prefix || prefix==='rgc'))return {shape:key.endsWith('midget')?'midget':'ganglion',polarity:key.split('-')[0],color:`var(--cell-${key.split('-')[0]})`};
  const bipolarKey=key.replace(/-cells?$/,'');
  const bipolar=['bipolar','bc'].includes(prefix) && /^(on|off)$/.test(bipolarKey)?`${bipolarKey}-bipolar`:bipolarKey;
  if(/^(on|off)-bipolar$/.test(bipolar) && (!prefix || prefix==='bipolar' || prefix==='bc'))
    return {shape:'bipolar',polarity:bipolar.split('-')[0],color:`var(--cell-${bipolar.split('-')[0]})`};
  if((bipolar==='bipolar' && !prefix))return {shape:'bipolar',color:'var(--ink-muted)'};
  if(!prefix && /^(horizontal(-cells?)?|hc)$/.test(key))return {shape:'horizontal',color:'var(--cell-outer)'};
  const receptor=key.replace(/-cells?$/,'').replace(/s$/,'');
  if(['cone','rod'].includes(receptor) && (!prefix || prefix==='photoreceptor' || prefix==='photoreceptors'))
    return {shape:receptor,color:'var(--cell-outer)'};
  return {shape:'generic',color:'var(--ink-muted)'};
}
export function cellTypeColor(type) {
  return cellTypePresentation(type).color;
}
