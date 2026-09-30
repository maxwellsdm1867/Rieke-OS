import test from 'node:test';
import assert from 'node:assert/strict';
import {importReadiness,suggestionDates} from './importReadiness.js';
test('pinned protocols without a proposal stay visible without fabricated matches',()=>{
 const model=importReadiness({protocols:[{protocol_uuid:'a'},{protocol_uuid:'b'}],preferences:{a:{section:'pinned'}},suggestions:[{protocol_uuid:'b',status:'pending'}]});
 assert.equal(model.pinned[0].protocol.protocol_uuid,'a');assert.equal(model.pinned[0].suggestion,undefined);assert.equal(model.other.length,1);assert.equal(model.ready,1);
});
test('applied and stale revisions remain distinct from ready additions',()=>{
 const model=importReadiness({suggestions:[{protocol_uuid:'a',status:'applied'},{protocol_uuid:'b',status:'stale'},{protocol_uuid:'c',status:'superseded'}]});
 assert.equal(model.ready,0);assert.equal(model.added,1);assert.equal(model.stale,1);assert.equal(model.other.length,2);
});
test('date summary includes newly matched trials in existing cells without double counting dates',()=>{
 assert.deepEqual(suggestionDates({diff_summary:{cell_changes:{added:[{date:'2026-09-23'}],updated:[{date:'2026-09-23'},{date:'2026-09-24'}]}}}),['2026-09-23','2026-09-24']);
});

test('approve all scope contains only pending valid pinned candidates',()=>{
 const model=importReadiness({
  protocols:['pending','applied','stale','other','missing'].map(protocol_uuid=>({protocol_uuid})),
  preferences:Object.fromEntries(['pending','applied','stale','missing'].map(id=>[id,{section:'pinned'}])),
  suggestions:[
   {protocol_uuid:'pending',candidate_revision_uuid:'ready',status:'pending'},
   {protocol_uuid:'applied',candidate_revision_uuid:'done',status:'applied'},
   {protocol_uuid:'stale',candidate_revision_uuid:'old',status:'stale'},
   {protocol_uuid:'other',candidate_revision_uuid:'hidden',status:'pending'},
   {protocol_uuid:'missing',status:'pending'},
  ],
 });
 assert.equal(model.pinnedReady,1);
 assert.deepEqual(model.pinnedPending.map(item=>item.candidate_revision_uuid),['ready']);
 assert.equal(model.other[0].candidate_revision_uuid,'hidden');
});
test('no pins means no approve-all targets even with pending saved protocols',()=>{
 const model=importReadiness({protocols:[{protocol_uuid:'other'}],suggestions:[{protocol_uuid:'other',candidate_revision_uuid:'r',status:'pending'}]});
 assert.equal(model.pinnedReady,0);
 assert.deepEqual(model.pinnedPending,[]);
 assert.equal(model.other.length,1);
});
