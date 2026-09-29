import test from 'node:test';
import assert from 'node:assert/strict';
import {exportReuseRoute} from './exportReuse.js';
const candidate='b411db17-0ab4-42aa-872a-e6e614106041',scope='7d76b76a-4c43-42c6-ac54-881ff2fc108a';
test('candidate reuse opens immutable selection for review, never its export-only scope as a protocol',()=>{
  const recipe={kind:'explorer_candidate',protocol_uuid:scope,candidate_revision_uuid:candidate,
    export_scope:{kind:'explorer_candidate'},export_intent:{name:'One-off',format:'epictree-mat'},source_export_uuid:scope};
  const route=exportReuseRoute(recipe);
  assert.deepEqual(route,{page:'explore',details:{exploreRevisionId:candidate,exploreExportIntent:{name:'One-off',format:'epictree-mat',source_export_uuid:scope}}});
  assert.equal(route.details.protocol,undefined);assert.equal(route.details.autoExport,undefined);
});
test('protocol reuse keeps its saved settings',()=>{const recipe={protocol_uuid:scope,format:'wheeler-sqlite',filters:{cell_type:'ON'}};assert.deepEqual(exportReuseRoute(recipe),{page:'protocol',details:{protocol:scope,recipe}});});
test('malformed candidate never falls back to a phantom protocol',()=>{
  for(const recipe of [null,{}, {kind:'explorer_candidate',protocol_uuid:scope},
    {kind:'explorer_candidate',candidate_revision_uuid:candidate,export_intent:{name:'x',format:'bad'}},
    {export_scope:{kind:'explorer_candidate'},protocol_uuid:scope}])assert.throws(()=>exportReuseRoute(recipe));
});
