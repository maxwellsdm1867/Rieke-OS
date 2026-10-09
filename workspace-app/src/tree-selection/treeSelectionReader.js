import {api} from '../api.js';
import {TREE_PAGE_SIZE,treePageRequest} from '../pagedTreeRequest.js';

function requestTreePage(scope,options,signal){
  return api(scope.readContext?`${scope.readContext.root}/tree/page`:'/tree-pages',{
    method:'POST',signal,body:treePageRequest(scope,options),
  });
}

function checkAborted(signal){
  if(signal?.aborted){const error=new Error('Tree selection canceled.');error.name='AbortError';throw error;}
}

/**
 * Stateless selection reads over existing ordered tree-page DTOs. requestPage
 * (scope, pageOptions, signal) is the transport adapter; default uses api so its
 * POST tracking and desktop write barriers still apply. Paths/rows are opaque.
 * The caller owns cancellation, scope lifetime and final selection publication.
 * firstEpoch(scope, {path, revision, signal}) resolves the original first DTO or
 * undefined, following only first branches. Expected revision wins over revision.
 * rangeEpochIds(scope, {page, firstIndex, lastIndex, signal}) returns ordered UUIDs
 * for normalized nonnegative absolute indices (firstIndex <= lastIndex) in the
 * supplied branch/revision: an array synchronously when the
 * supplied page suffices, otherwise a Promise. The supplied page is trusted as
 * before; no cache or additional identity authority is introduced.
 * Both operations retain tree-change/transport errors. firstEpoch rejects with
 * AbortError on cancellation; rangeEpochIds throws synchronously before a
 * transport is needed, or rejects its Promise after an asynchronous read.
 * Ranges reject incomplete rows; Main/legacy ranges also reject sizes above 1,000. No partial result
 * publishes. Scope/path/offset are caller-provided, not newly validated here.
 *
 * @example
 * const page = {kind:'epochs', revision:'r', path:[], offset:0,
 *   epochs:[{epoch_uuid:'epoch-A'}]};
 * const reader = createTreeSelectionReader({requestPage:async () => page});
 * const first = await reader.firstEpoch({}, {path:[], revision:'r'});
 * const ids = reader.rangeEpochIds({}, {page, firstIndex:0, lastIndex:0});
 * // first === page.epochs[0]; ids is the synchronous array ['epoch-A'].
 * // See AGENTS.md and the colocated public test for async/cancellation usage.
 */
export function createTreeSelectionReader({requestPage=requestTreePage}={}){
  async function read(scope,options,signal){
    checkAborted(signal);
    const page=await requestPage(scope,options,signal);
    checkAborted(signal);
    return page;
  }
  return {rangeEpochIds(scope,{page,firstIndex,lastIndex,signal}){
    checkAborted(signal);
    if(!scope.readContext?.selection_manifests&&lastIndex-firstIndex+1>1000)throw new Error('Select at most 1,000 epochs.');
    const ids=[];
    function append(part,offset){
      checkAborted(signal);
      if(part.revision!==page.revision||part.kind!=='epochs')throw new Error('Tree changed. Select the range again.');
      for(let n=Math.max(firstIndex,offset);n<=Math.min(lastIndex,offset+TREE_PAGE_SIZE-1);n++){
        const row=part.epochs[n-offset];if(!row)throw new Error('Could not load the complete range.');
        ids.push(row.epoch_uuid);
      }
    }
    function collect(offset){
      for(;offset<=lastIndex;offset+=TREE_PAGE_SIZE){
        if(offset===page.offset)append(page,offset);
        else return read(scope,{path:page.path,offset,currentRevision:page.revision},signal).then(part=>{
          append(part,offset);return collect(offset+TREE_PAGE_SIZE);
        });
      }
      return ids;
    }
    return collect(Math.floor(firstIndex/TREE_PAGE_SIZE)*TREE_PAGE_SIZE);
  },async firstEpoch(scope,{path,revision,signal}){
    let page=await read(scope,{path,currentRevision:revision},signal);
    checkAborted(signal);
    const pinned=scope.expectedRevision||revision||page.revision;
    if(page.revision!==pinned)throw new Error('Tree changed. Select the cell again.');
    while(page.kind!=='epochs'&&page.branches?.length){
      page=await read(scope,{path:page.branches[0].path,currentRevision:pinned},signal);
      checkAborted(signal);
      if(page.revision!==pinned)throw new Error('Tree changed. Select the cell again.');
    }
    return page.epochs?.[0];
  }};
}
