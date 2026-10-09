import test from 'node:test';
import assert from 'node:assert/strict';
import {loadImportedSelection} from './importedSelection.js';
import {createIncomingMergeIntents} from './incomingMergeIntent.js';
const root='/protocols/p/workbench/candidates/c';
const context={candidate_scope_revision:'scope',protocol:{definition:{protocol_uuid:'p'},counts:{epochs:3},cells:[{cell_uuid:'cell',epochs:3}]},draft:{decisions_truncated:false,decisions_total:1,decisions:[{epoch_uuid:'excluded',excluded:true}]}};
const page={query_revision:'scope',total:3,offset:0,epochs:[{epoch_uuid:'old',cell_uuid:'cell',source_sha256:'other'},{epoch_uuid:'new',cell_uuid:'cell',source_sha256:'new-source'},{epoch_uuid:'excluded',cell_uuid:'cell',source_sha256:'new-source'}]};
test('hold selection preserves exclusions and unrelated older pending sources',async()=>{
 const requests=[];assert.deepEqual(await loadImportedSelection({root,context,sourceSha256:'new-source',request:async(path)=>{requests.push(path);return page;}}),['new']);assert.match(requests[0],/candidate_scope_revision=scope/);
});
test('source selection refuses missing identity, stale/partial reads, incomplete drafts/counts and over-limit scopes',async()=>{
 for(const bad of [{...page,epochs:page.epochs.map(({source_sha256,...row})=>row)},{...page,query_revision:'changed'},{...page,epochs:page.epochs.slice(1)}])await assert.rejects(loadImportedSelection({root,context,sourceSha256:'new-source',request:async()=>bad}));
 for(const bad of [{...context,draft:{...context.draft,decisions_truncated:true}},{...context,protocol:{}}])await assert.rejects(loadImportedSelection({root,context:bad,sourceSha256:'new-source',request:async()=>page}));
 let current=true;await assert.rejects(loadImportedSelection({root,context,sourceSha256:'new-source',isCurrent:()=>current,request:async()=>{current=false;return page;}}),{name:'AbortError'});
 await assert.rejects(loadImportedSelection({root,context:{...context,protocol:{counts:{epochs:1001},cells:[{cell_uuid:'cell',epochs:1001}]}},sourceSha256:'new-source',request:async()=>assert.fail('no over-limit read')}),/1,000/);
});
test('source merge consent cannot be restored, retargeted or claimed twice',()=>{
 const ledger=createIncomingMergeIntents(),options={kind:'merge_source',candidate_revision_uuid:'c',source_sha256:'new-source'},intent=ledger.issue('project','p',options);
 assert.equal(createIncomingMergeIntents().claim(intent,'project','p'),false);assert.equal(ledger.claim({...intent,source_sha256:'other'},'project','p'),false);
 const next=ledger.issue('project','p',options);assert.equal(ledger.claim(next,'project','p'),true);assert.equal(ledger.claim(next,'project','p'),false);
});
