import {treeNavigationStart,treeNavigationSnapshot} from './pagedTreeRequest.js';
export const HIERARCHY_PAGE_LIMIT=24;
export const hierarchyKey=path=>JSON.stringify(path);
export function pathContains(parent,child){return parent.length<=child.length&&parent.every((part,index)=>part===child[index]);}
export function validHierarchyPath(path){return Array.isArray(path)&&path.length<=8&&path.every(key=>typeof key==='string'&&/^[0-9a-f]{64}$/.test(key));}
export function mergeHierarchyPage(state,page,limit=HIERARCHY_PAGE_LIMIT){
  const key=hierarchyKey(page.path),previous=state.pages.find(item=>hierarchyKey(item.path)===key);
  let pages=state.pages.filter(item=>hierarchyKey(item.path)!==key&&!(previous&&previous.offset!==page.offset&&page.path.length<item.path.length&&pathContains(page.path,item.path)));
  let expanded=state.expanded.filter(path=>!(previous&&previous.offset!==page.offset&&page.path.length<path.length&&pathContains(page.path,path)));
  pages.push(page);let evicted=0;
  while(pages.length>limit){
    const victim=pages.find(item=>item.path.length&&!pathContains(item.path,page.path));
    if(!victim)break;
    pages=pages.filter(item=>!pathContains(victim.path,item.path));
    expanded=expanded.filter(path=>!pathContains(victim.path,path));evicted++;
  }
  return {...state,pages,expanded,evicted};
}
export function cancelUnloadedExpansion(state,nextPath){
  const pending=state.loadingPath;
  if(!pending?.length||hierarchyKey(pending)===hierarchyKey(nextPath)||state.pages.some(page=>hierarchyKey(page.path)===hierarchyKey(pending)))return state;
  return collapseHierarchy(state,pending);
}
export function collapseHierarchy(state,path){return {...state,expanded:state.expanded.filter(item=>!pathContains(path,item))};}
export function expandHierarchy(state,path){return state.expanded.some(item=>hierarchyKey(item)===hierarchyKey(path))?state:{...state,expanded:[...state.expanded,path]};}
export function hierarchySnapshot(state,scrollTop=0,scrollLeft=0){
  const root=state.pages.find(page=>!page.path.length);if(!root)return null;
  return {...treeNavigationSnapshot(root,scrollTop),hierarchy:{version:1,
    expanded:state.expanded.slice(-HIERARCHY_PAGE_LIMIT).map(path=>[...path]),
    pages:state.pages.slice(-HIERARCHY_PAGE_LIMIT).map(page=>({path:[...page.path],offset:page.offset})),
    scrollTop:Number.isFinite(scrollTop)?Math.max(0,scrollTop):0,scrollLeft:Number.isFinite(scrollLeft)?Math.max(0,scrollLeft):0}};
}
export function hierarchyRestore(saved,splits){
  const base=treeNavigationStart(saved,splits);if(!base)return null;
  const detail=saved.hierarchy;
  if(detail?.version===1&&Array.isArray(detail.pages)&&detail.pages.length<=HIERARCHY_PAGE_LIMIT&&Array.isArray(detail.expanded)&&detail.expanded.length<=HIERARCHY_PAGE_LIMIT&&detail.pages.every(page=>validHierarchyPath(page.path)&&Number.isSafeInteger(page.offset)&&page.offset>=0&&page.offset<=10000000)&&detail.expanded.every(validHierarchyPath)){
    const pages=[{path:[],offset:0},...detail.pages];
    const byPath=new Map(pages.map(page=>[hierarchyKey(page.path),page]));
    return {revision:base.revisionOverride,pages:[...byPath.values()].sort((a,b)=>a.path.length-b.path.length),expanded:detail.expanded,scrollTop:Number.isFinite(detail.scrollTop)?Math.max(0,detail.scrollTop):0,scrollLeft:Number.isFinite(detail.scrollLeft)?Math.max(0,detail.scrollLeft):0};
  }
  return {revision:base.revisionOverride,pages:Array.from({length:base.path.length+1},(_,depth)=>({path:base.path.slice(0,depth),offset:depth===base.path.length?base.offset:(saved.columnPositions?.[depth]?.offset||0)})),expanded:Array.from({length:base.path.length},(_,depth)=>base.path.slice(0,depth+1)),scrollTop:base.scrollTop,scrollLeft:0};
}
