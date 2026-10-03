import {treePageRequest} from './pagedTreeRequest.js';

export const TREE_TAG_LIMIT=1000;
const samePath=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
function endpoint(scope){
  if(!scope.readContext)return '/tree-pages';
  if(!scope.readContext.root||!scope.readContext.candidate_scope_revision)throw Error('A complete frozen Incoming Workbench scope is required.');
  return `${scope.readContext.root}/tree/page`;
}
export async function verifyTreeGroup(scope,revision,request,{signal}={}){
  const route=endpoint(scope);
  const page=await request(route,{method:'POST',signal,body:treePageRequest(scope,{currentRevision:revision})});
  if(page.revision!==revision)throw new Error('Tree changed. Reopen Tag this group before saving.');
}

// Navigation keys retain the server's typed null/missing/joint semantics. Never
// reconstruct a predicate from display labels or borrow the visible leaf page.
export async function resolveTreeGroup({scope,path,revision,count,cellUuid=null,request,signal,onProgress}){
  const route=endpoint(scope);
  if(!revision||!Number.isSafeInteger(count)||count<1)throw new Error('The exact group count is unavailable. Refresh the tree.');
  if(!cellUuid&&count>TREE_TAG_LIMIT)throw new Error(`This group contains ${count.toLocaleString()} epochs. Shared group tags support at most 1,000 epochs; nothing was tagged.`);
  const rows=[],seen=new Set();
  async function visit(currentPath){
    let offset=0;
    do{
      if(signal?.aborted)throw new DOMException('Group loading cancelled','AbortError');
      const page=await request(route,{method:'POST',signal,body:treePageRequest(scope,{path:currentPath,offset,currentRevision:revision})});
      if(page.revision!==revision||!samePath(page.path,currentPath)||page.offset!==offset||!Number.isSafeInteger(page.total)||page.total<0||page.limit!==60)throw new Error('Tree changed or the complete group could not be verified. Reopen Tag this group.');
      if(offset===0&&samePath(currentPath,path)&&page.selection?.count!==count)throw new Error('Group count changed. Refresh the tree.');
      const entries=page.kind==='epochs'?page.epochs:page.kind==='branches'?page.branches:null;
      if(!Array.isArray(entries)||entries.length!==Math.min(60,page.total-offset)||page.has_more!==(offset+60<page.total))throw new Error('The complete group could not be loaded; nothing was tagged.');
      for(const item of entries){
        if(page.kind==='epochs'){
          if(!item.epoch_uuid||seen.has(item.epoch_uuid)||rows.length>=TREE_TAG_LIMIT)throw new Error('The complete group contains invalid or excessive targets; nothing was tagged.');
          if(cellUuid&&item.cell_uuid!==cellUuid)throw new Error('The recorded cell identity could not be verified.');
          seen.add(item.epoch_uuid);rows.push(item);onProgress?.(rows.length);
          if(cellUuid)return true; // One representative proves the exact cell UUID.
        }else{
          if(!Array.isArray(item.path)||item.path.length!==currentPath.length+1||!samePath(item.path.slice(0,-1),currentPath))throw new Error('Invalid structural group path.');
          if(await visit(item.path))return true;
        }
      }
      offset+=60;
      if(!page.has_more)break;
    }while(true);
    return false;
  }
  await visit(path);
  if(!rows.length||(!cellUuid&&rows.length!==count))throw new Error('The complete group count could not be verified; nothing was tagged.');
  await verifyTreeGroup(scope,revision,request,{signal});
  return Object.freeze({epoch:{...rows[0],annotations:undefined},ids:Object.freeze(rows.map(row=>row.epoch_uuid)),count:cellUuid?1:rows.length,kind:cellUuid?'cell':'epoch'});
}
