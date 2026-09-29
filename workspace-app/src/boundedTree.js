// Paging changes presentation only. A selected item outside the page is shown
// once as an additional pinned row, without replacing any page members.
export function boundedTreePage(items,offset=0,limit=60,pinned=null){
  const total=items.length,pageSize=Math.max(1,Math.floor(limit));
  const start=Math.min(Math.max(0,Math.floor(offset/pageSize)*pageSize),Math.max(0,Math.floor((total-1)/pageSize)*pageSize));
  const end=Math.min(total,start+pageSize),page=items.slice(start,end);
  const pinnedOutside=!!pinned&&!page.includes(pinned)&&items.includes(pinned);
  return {items:pinnedOutside?[...page,pinned]:page,offset:start,end,total,pinnedOutside,hasPrevious:start>0,hasNext:end<total};
}
export function inspectionTreeFocus(index,epochUuid){
  const branches=new Set(),childOf=new Map();
  let node=index.epochNodes?.get(epochUuid);
  while(node){branches.add(node);const parent=index.parents?.get(node);if(parent)childOf.set(parent,node);node=parent;}
  return {branches,childOf,epoch:index.epochs?.get(epochUuid)};
}

// Group first, then page the grouped sequence: every cell remains reachable,
// including types that span pages. Counts describe the complete input scope.
export function groupedCellPage(cells,offset=0,limit=60){
  const groups=new Map();
  for(const cell of cells){
    const type=cell.cell_type||cell.type||'Unknown cell type';
    if(!groups.has(type))groups.set(type,[]);
    groups.get(type).push(cell);
  }
  const ordered=[...groups.values()].flat();
  const page=boundedTreePage(ordered,offset,limit);
  const visible=new Map();
  for(const cell of page.items){
    const type=cell.cell_type||cell.type||'Unknown cell type';
    if(!visible.has(type))visible.set(type,{type,cells:[],total:groups.get(type).length});
    visible.get(type).cells.push(cell);
  }
  return {...page,groups:[...visible.values()]};
}
