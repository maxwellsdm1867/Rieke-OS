export function recordingDate(record={}){
  const value=record.date || record.start_time || '';
  const date=String(value).match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  return date || 'Date not recorded';
}
export function datedCellLabel(record={},cellRow=false){
  const label=record.cell_label || (cellRow?record.label:undefined) || 'Cell label not recorded';
  const date=recordingDate(record);
  return String(label).startsWith(`${date} · `)?String(label):`${date} · ${label}`;
}
