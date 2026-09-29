import test from 'node:test';
import assert from 'node:assert/strict';
import {exportProtocolGroups,pinProtocolPreference} from './exportProtocolTargets.js';
test('pinned destinations lead and typing datasets stay secondary',()=>{
 const protocols=[{protocol_uuid:'qc',name:'ExpandingSpots'},{protocol_uuid:'a',name:'VariableMeanNoise'},{protocol_uuid:'b',name:'VariableHistoryNoise'}];
 const preferences={b:{section:'pinned',rank:0}};
 const groups=exportProtocolGroups(protocols,preferences);
 assert.deepEqual(groups.map(group=>group.protocols.map(p=>p.protocol_uuid)),[['b'],['a']]);
 assert.deepEqual(exportProtocolGroups(protocols,{...preferences,qc:{section:'pinned'}})[0].protocols.map(p=>p.protocol_uuid),['qc','b']);
});
test('pinning a destination preserves every other sidebar preference',()=>{
 const before={a:{section:'pinned',rank:4},qc:{section:'support',rank:1},b:{section:'main',rank:0}};
 const next=pinProtocolPreference(before,'b');
 assert.deepEqual(next.b,{section:'pinned',rank:5});
 assert.equal(before.b.section,'main');
 assert.deepEqual(next.a,before.a);assert.deepEqual(next.qc,before.qc);
 assert.equal(pinProtocolPreference(next,'b'),next);
});
