export function columnAncestorPages(page,{anchor=false,columnPositions=[]}={}){
  return page.path.map((_,depth)=>{
    const recorded=page.ancestors?.[depth]?.parent_offset;
    if(anchor&&(!Number.isSafeInteger(recorded)||recorded<0))throw new Error('The selected epoch’s ancestor page could not be located. Refresh the tree.');
    const preferred=anchor?recorded:columnPositions[depth]?.offset??recorded??0;
    return {depth,path:page.path.slice(0,depth),offset:Number.isSafeInteger(preferred)&&preferred>=0?preferred:0,revision:page.revision};
  });
}
export function canReuseColumn(page,target){
  return !!page&&page.revision===target.revision&&page.offset===target.offset&&JSON.stringify(page.path)===JSON.stringify(target.path);
}
export function columnSelectionNeedsAnchor(columns,selected,pending=false){
  if(!selected)return false;
  const leaf=columns.at(-1);
  return pending||leaf?.kind!=='epochs'||!leaf.epochs?.some(epoch=>epoch.epoch_uuid===selected);
}

// Closing a column returns to its parent page without selecting scientific data.
export function columnBranchNavigation(page,item,expandedKey){
 const opening=expandedKey!==item.key;
 return {opening,path:opening?item.path:page.path,offset:opening?0:page.offset};
}

// Horizontal gestures belong to the whole column strip, including at its edges.
// Leave ordinary vertical gestures to the column under the pointer.
export function columnWheelDelta({deltaX=0,deltaY=0,shiftKey=false,deltaMode=0},width){
 const horizontal=shiftKey?(deltaX||deltaY):Math.abs(deltaX)>Math.abs(deltaY)?deltaX:0;
 return horizontal*(deltaMode===1?16:deltaMode===2?width:1);
}
