// Search exclusions are local to this viewer. Candidate destinations all receive
// the same constrained query, while the browsable base query stays unchanged.
function nodeCount(predicate){
  if(Array.isArray(predicate.all))return 1+predicate.all.reduce((count,node)=>count+nodeCount(node),0);
  if(Array.isArray(predicate.any))return 1+predicate.any.reduce((count,node)=>count+nodeCount(node),0);
  return predicate.not?1+nodeCount(predicate.not):1;
}
function nodeDepth(predicate){
  const children=Array.isArray(predicate.all)?predicate.all:Array.isArray(predicate.any)?predicate.any:predicate.not?[predicate.not]:[];
  return 1+children.reduce((depth,node)=>Math.max(depth,nodeDepth(node)),0);
}
export function searchInclusionPredicate(predicate,excluded=[]){
  const ids=[...new Set(excluded)].sort();
  if(!ids.length)return predicate;
  // The backend caps each comparison literal at 4096 encoded characters.
  // Separate bounded UUID clauses preserve exact membership for large searches.
  const clauses=[];
  for(let offset=0;offset<ids.length;offset+=64)clauses.push({field:'epoch',operator:'not_in',value:ids.slice(offset,offset+64)});
  const result={all:[...(Array.isArray(predicate.all)?predicate.all:[predicate]),...clauses]};
  if(nodeCount(result)>128)throw new Error('This search and its exclusions exceed the query size limit. Simplify the search criteria or include more epochs before exporting.');
  if(nodeDepth(result)>8)throw new Error('This search is nested too deeply to add exclusions. Simplify the search criteria before exporting.');
  return result;
}
export function searchEpochInclusion(epoch,excluded=[]){
  return {...epoch,curation:{...epoch.curation,included:!excluded.includes(epoch.epoch_uuid)}};
}
export function toggleSearchInclusion(excluded,uuid,included){
  return included?excluded.filter(id=>id!==uuid):[...new Set([...excluded,uuid])];
}
