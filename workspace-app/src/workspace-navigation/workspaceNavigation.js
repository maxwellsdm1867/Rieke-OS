/** Existing admitted destination set; callers retain its current mutable identity. */
export const WORKSPACE_PAGES=new Set(['overview','protocol','explore','stores','import','activity','files','exports','cell-qc']);
/** Check the existing minimal local route shape, including protocol identity. */
export function validWorkspaceRoute(value){
  return !!value&&typeof value==='object'&&WORKSPACE_PAGES.has(value.page)&&typeof value.key==='string'&&
    (value.page!=='protocol'||typeof value.protocol==='string');
}
/** Encode the destination hash, preferring protocol identity over cell identity. */
export function routeAddress(route){
  return `#/${route.page}${route.protocol?`/${encodeURIComponent(route.protocol)}`:route.cell_uuid?`/${encodeURIComponent(route.cell_uuid)}`:''}`;
}
/** Create a visit with the supplied key; reject unknown destinations. */
export function makeWorkspaceRoute(page,details={},key){
  if(!WORKSPACE_PAGES.has(page))throw new Error('Unknown workspace destination');
  return {...details,page,key};
}
/** Resolve restore, recipe and inspection precedence without scientific consent. */
export function resolveProtocolSession({saved,recipe,inspection,restore=false}){
  if(restore&&saved)return saved;
  if(recipe)return {filters:saved?.filters || {},exportFilters:recipe.filters || {},tab:'export',policy:recipe.review_policy || 'include_unreviewed',exportName:recipe.name || '',format:recipe.format,splitOrder:recipe.split_order};
  if(inspection)return {...saved,filters:{},tab:'inspect',scope:inspection.cell_uuid || null,initialEpoch:inspection.epoch_uuid || null,inspector:{focused:inspection.epoch_uuid || null,focusCell:inspection.cell_uuid || null,offset:0}};
  return saved?{...saved,inspector:saved.inspector?{...saved.inspector,designMode:false,treeMode:false,treeOpen:true}:null}:{};
}

/** Preserve explicit cleared focus instead of resurrecting a handoff fallback. */
export function restoredEpochFocus(session,fallback=null){
  return session&&Object.hasOwn(session,'focused')?(session.focused ?? null):(fallback ?? null);
}

/** Keep draft/immutable identity and counts, omitting heavy preview membership. */
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
