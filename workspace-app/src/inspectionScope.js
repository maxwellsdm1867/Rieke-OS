// Cell focus controls navigation only. The shared tree retains the protocol's explicit filters.
export function inspectionSearches(filters={},focusedCell=null){
  return {
    protocol:new URLSearchParams(filters).toString(),
    navigation:new URLSearchParams({...filters,...(focusedCell&&!filters.cell_uuid?{cell_uuid:focusedCell}:{})}).toString(),
  };
}
export function indexInspectionTree(tree){
  const epochCells=new Map(),cellBranches=new Map(),epochNodes=new Map(),epochs=new Map(),parents=new WeakMap();
  function visit(node,ancestors=[]){
    const path=[...ancestors,node];
    if(ancestors.length)parents.set(node,ancestors.at(-1));
    for(const epoch of node.epochs || []){
      epochCells.set(epoch.epoch_uuid,epoch.cell_uuid || null);epochNodes.set(epoch.epoch_uuid,node);epochs.set(epoch.epoch_uuid,epoch);
      if(epoch.cell_uuid){const branches=cellBranches.get(epoch.cell_uuid)||new Set();path.forEach(branch=>branches.add(branch));cellBranches.set(epoch.cell_uuid,branches);}
    }
    (node.children || []).forEach(child=>visit(child,path));
  }
  if(tree)visit(tree);
  return {epochCells,cellBranches,epochNodes,epochs,parents};
}
export function focusAfterTreeSelection(focusedCell,epochUuid,index){
  return focusedCell&&index.epochCells.get(epochUuid)===focusedCell?focusedCell:null;
}
export function curationMatchesCellFocus(epochs,focusedCell){
  return !focusedCell||epochs.every(epoch=>epoch.cell_uuid===focusedCell);
}
