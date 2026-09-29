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
