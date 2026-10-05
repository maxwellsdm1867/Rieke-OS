import test from 'node:test';
import assert from 'node:assert/strict';
import {exportReuseRoute} from "./exports/exportReuse.js";
const candidate='b411db17-0ab4-42aa-872a-e6e614106041',scope='7d76b76a-4c43-42c6-ac54-881ff2fc108a';
test('candidate reuse opens immutable selection for review, never its export-only scope as a protocol',()=>{
  const recipe={kind:'explorer_candidate',protocol_uuid:scope,candidate_revision_uuid:candidate,
    export_scope:{kind:'explorer_candidate'},export_intent:{name:'One-off',format:'epictree-mat'},source_export_uuid:scope};
  const route=exportReuseRoute(recipe);
  assert.deepEqual(route,{page:'explore',details:{exploreRevisionId:candidate,exploreExportIntent:{name:'One-off',format:'matlab-mat',source_export_uuid:scope}}});
  assert.equal(route.details.protocol,undefined);assert.equal(route.details.autoExport,undefined);
});
test('protocol reuse keeps its saved settings',()=>{const recipe={protocol_uuid:scope,format:'wheeler-sqlite',filters:{cell_type:'ON'}};assert.deepEqual(exportReuseRoute(recipe),{page:'protocol',details:{protocol:scope,recipe}});});
test('malformed candidate never falls back to a phantom protocol',()=>{
  for(const recipe of [null,{}, {kind:'explorer_candidate',protocol_uuid:scope},
    {kind:'explorer_candidate',candidate_revision_uuid:candidate,export_intent:{name:'x',format:'bad'}},
    {export_scope:{kind:'explorer_candidate'},protocol_uuid:scope}])assert.throws(()=>exportReuseRoute(recipe));
});

test('incoming export reuse opens target protocol Workbench with exact saved proposal and intent',()=>{
 const operation='a411db17-0ab4-42aa-872a-e6e614106041';
 const recipe={kind:'workbench_incoming',target_protocol_uuid:scope,candidate_revision_uuid:candidate,accept_operation_uuid:operation,source_export_uuid:operation,export_intent:{name:'New additions',format:'wheeler-sqlite'}};
 const route=exportReuseRoute(recipe);
 assert.deepEqual(route,{page:'protocol',details:{protocol:scope,workbench:{candidate_revision_uuid:candidate,accept_operation_uuid:operation,export_intent:{name:'New additions',format:'wheeler-sqlite',source_export_uuid:operation}}}});
 assert.equal(route.details.recipe,undefined);assert.equal(route.details.exploreRevisionId,undefined);
 assert.throws(()=>exportReuseRoute({...recipe,target_protocol_uuid:undefined,protocol_uuid:candidate}),/Workbench destination/);
 assert.throws(()=>exportReuseRoute({...recipe,accept_operation_uuid:'bad'}),/Workbench destination/);
});
