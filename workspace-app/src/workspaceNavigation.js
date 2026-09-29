export const WORKSPACE_PAGES=new Set(['overview','protocol','explore','stores','import','activity','files','exports','cell-qc']);
export function validWorkspaceRoute(value){
  return !!value&&typeof value==='object'&&WORKSPACE_PAGES.has(value.page)&&typeof value.key==='string'&&
    (value.page!=='protocol'||typeof value.protocol==='string');
}
export function routeAddress(route){
  return `#/${route.page}${route.protocol?`/${encodeURIComponent(route.protocol)}`:route.cell_uuid?`/${encodeURIComponent(route.cell_uuid)}`:''}`;
}
export function makeWorkspaceRoute(page,details={},key){
  if(!WORKSPACE_PAGES.has(page))throw new Error('Unknown workspace destination');
  return {...details,page,key};
}
export function resolveProtocolSession({saved,recipe,inspection,restore=false}){
  if(restore&&saved)return saved;
  if(recipe)return {filters:recipe.filters || {},tab:'export',policy:recipe.review_policy || 'include_unreviewed',exportName:recipe.name || '',format:recipe.format,splitOrder:recipe.split_order};
  if(inspection)return {...saved,filters:{},tab:'inspect',scope:inspection.cell_uuid || null,initialEpoch:inspection.epoch_uuid || null,inspector:{focused:inspection.epoch_uuid || null,focusCell:inspection.cell_uuid || null,offset:0}};
  return saved?{...saved,inspector:saved.inspector?{...saved.inspector,designMode:false,treeMode:false,treeOpen:true}:null}:{};
}

export function restoredEpochFocus(session,fallback=null){
  return session&&Object.hasOwn(session,'focused')?(session.focused ?? null):(fallback ?? null);
}

export function snapshotExplorerState(state){
  const saved=value=>{
    if(!value)return null;
    const {epochs,diff,content_sha256,...recipe}=value.recipe || {};
    if(recipe.epoch_count==null&&Array.isArray(epochs))recipe.epoch_count=epochs.length;
    if(!recipe.diff_counts&&diff)recipe.diff_counts=Object.fromEntries(['added','removed','changed'].map(key=>[key,Array.isArray(diff[key])?diff[key].length:0]));
    recipe.summary_only=true;
    return {revision_uuid:value.revision_uuid,recipe,summary:value.summary};
  };
  return {...state,applied:saved(state.applied),restored:saved(state.restored)};
}
