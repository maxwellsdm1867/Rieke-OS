const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FORMATS=new Set(['reference-json','wheeler-sqlite','epictree-mat']);
export function exportReuseRoute(recipe){
  if(!recipe||typeof recipe!=='object')throw new Error('The saved export did not return a reusable query.');
  if(recipe.kind==='explorer_candidate'||recipe.export_scope?.kind==='explorer_candidate'){
    if(!UUID.test(recipe.candidate_revision_uuid||'')||!recipe.export_intent||!FORMATS.has(recipe.export_intent.format)||typeof recipe.export_intent.name!=='string')throw new Error('The saved search export has an invalid review destination.');
    return {page:'explore',details:{exploreRevisionId:recipe.candidate_revision_uuid,
      exploreExportIntent:{name:recipe.export_intent.name,format:recipe.export_intent.format,source_export_uuid:recipe.source_export_uuid}}};
  }
  if(!UUID.test(recipe.protocol_uuid||''))throw new Error('The saved export has no protocol workspace.');
  return {page:'protocol',details:{protocol:recipe.protocol_uuid,recipe}};
}
