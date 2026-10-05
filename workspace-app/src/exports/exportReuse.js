import {normalizeExportFormat} from './exportFormats.js';
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FORMATS=new Set(['reference-json','wheeler-sqlite','matlab-mat']);
export function exportReuseRoute(recipe){
  if(!recipe||typeof recipe!=='object')throw new Error('The saved export did not return a reusable query.');
  if(recipe.kind==='workbench_incoming'||recipe.export_scope?.kind==='workbench_incoming'){
    if(!UUID.test(recipe.target_protocol_uuid||'')||!UUID.test(recipe.candidate_revision_uuid||'')||recipe.accept_operation_uuid!=null&&!UUID.test(recipe.accept_operation_uuid)||!recipe.export_intent||!FORMATS.has(normalizeExportFormat(recipe.export_intent.format))||typeof recipe.export_intent.name!=='string')throw new Error('The saved incoming export has an invalid Workbench destination.');
    return {page:'protocol',details:{protocol:recipe.target_protocol_uuid,workbench:{candidate_revision_uuid:recipe.candidate_revision_uuid,accept_operation_uuid:recipe.accept_operation_uuid||null,export_intent:{name:recipe.export_intent.name,format:normalizeExportFormat(recipe.export_intent.format),source_export_uuid:recipe.source_export_uuid}}}};
  }
  if(recipe.kind==='explorer_candidate'||recipe.export_scope?.kind==='explorer_candidate'){
    if(!UUID.test(recipe.candidate_revision_uuid||'')||!recipe.export_intent||!FORMATS.has(normalizeExportFormat(recipe.export_intent.format))||typeof recipe.export_intent.name!=='string')throw new Error('The saved search export has an invalid review destination.');
    return {page:'explore',details:{exploreRevisionId:recipe.candidate_revision_uuid,
      exploreExportIntent:{name:recipe.export_intent.name,format:normalizeExportFormat(recipe.export_intent.format),source_export_uuid:recipe.source_export_uuid}}};
  }
  if(!UUID.test(recipe.protocol_uuid||''))throw new Error('The saved export has no protocol workspace.');
  return {page:'protocol',details:{protocol:recipe.protocol_uuid,recipe}};
}
export function exportHistoryLabel(record){return record?.export_scope?.kind==='workbench_incoming'?'Incoming additions':record?.export_scope?.kind==='explorer_candidate'?'One-off search':'Protocol export';}
export function exportReuseLabel(record){return record?.export_scope?.kind==='workbench_incoming'?'Review incoming export':record?.export_scope?.kind==='explorer_candidate'?'Review saved query':'Reuse query';}
