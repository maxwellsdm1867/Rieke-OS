// Scroll only the epoch list, never the containing workspace or document.
export function epochListScrollTop({scrollTop,height,rowTop,rowBottom,header=36}){
  if(rowTop<header)return Math.max(0,scrollTop+rowTop-header);
  if(rowBottom>height)return Math.max(0,scrollTop+rowBottom-height);
  return scrollTop;
}
export function revealEpochRow(container){
  const row=container?.querySelector('.epoch-row.active');
  if(!row)return;
  const bounds=container.getBoundingClientRect(),item=row.getBoundingClientRect();
  const next=epochListScrollTop({scrollTop:container.scrollTop,height:container.clientHeight,rowTop:item.top-bounds.top,rowBottom:item.bottom-bounds.top});
  if(next!==container.scrollTop)container.scrollTop=next;
}

// Tree panes have their own scroll axes. Never ask the browser to scroll every
// ancestor (scrollIntoView), which can displace the trace and workspace header.
export function revealWithin(container,node,{horizontal=false,vertical=true}={}){
  if(!container||!node)return;
  const bounds=container.getBoundingClientRect(),item=node.getBoundingClientRect();
  if(vertical)container.scrollTop=epochListScrollTop({scrollTop:container.scrollTop,height:container.clientHeight,rowTop:item.top-bounds.top,rowBottom:item.bottom-bounds.top,header:0});
  if(horizontal){
    const left=item.left-bounds.left,right=item.right-bounds.left;
    if(left<0)container.scrollLeft+=left;
    else if(right>container.clientWidth)container.scrollLeft+=right-container.clientWidth;
  }
}
