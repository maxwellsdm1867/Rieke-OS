'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {nativePhaseSelection}=require('../e2e/native-phase-selection.cjs');
test('normal qualification retains all native phases and full-suite authority',()=>{
 assert.deepEqual(nativePhaseSelection(undefined),{scope:'all',requestedPhases:['update','restore','rollback'],fullSuite:true});
});
test('rollback replay explicitly limits receipt authority to its requested phase',()=>{
 const replay=nativePhaseSelection('rollback');assert.equal(replay.fullSuite,false);assert.equal(replay.scope,'rollback');assert.deepEqual(replay.requestedPhases,['rollback']);
});
test('mistyped phase configuration cannot silently skip qualification',()=>{
 for(const value of ['',null,'all','restore','ROLLBACK','rollback '])assert.throws(()=>nativePhaseSelection(value),/must be unset or rollback/);
});
