// Bounded cell lists: a response with an integer cells_total carries one window
// of cells (cells_next is the next cells_after, or null at the end). Without
// cells_total the server returned the complete list (old behaviour).
export const CELL_WINDOW=200;

/** The window facts of a cell-list response, or null for a complete list. */
export function cellWindowOf(data){
  if(!Array.isArray(data?.cells)||!Number.isSafeInteger(data.cells_total)||data.cells_total<0)return null;
  const next=data.cells_next;
  if(next!==null&&next!==undefined&&(!Number.isSafeInteger(next)||next<=0))throw Error('The cell list window is invalid. Refresh the list.');
  return {total:data.cells_total,next:next??null};
}

/** Append a later window, keeping first-appearance order and each cell once. */
export function appendCellWindow(cells,more){
  const seen=new Set((cells||[]).map(cell=>cell.cell_uuid));
  return [...(cells||[]),...(more||[]).filter(cell=>!seen.has(cell.cell_uuid)&&seen.add(cell.cell_uuid))];
}
