import test from 'node:test';
import assert from 'node:assert/strict';
import {pruneDeletedSourceSelections} from './deletedSourceSelections.js';
test('deletion removes exact source epochs and cells from stored focused and bulk selections',()=>{
  const session={initialEpoch:'deleted-epoch',scope:'deleted-cell',inspector:{focused:'deleted-epoch',checked:['kept-epoch','deleted-epoch'],authorRevisions:{'deleted-epoch':2,'kept-epoch':3}},splitOrder:['cell','block'],tab:'inspect'};
  assert.deepEqual(pruneDeletedSourceSelections(session,['deleted-epoch','deleted-cell']),{initialEpoch:null,scope:null,inspector:{focused:null,checked:['kept-epoch'],authorRevisions:{'kept-epoch':3}},splitOrder:['cell','block'],tab:'inspect'});
  assert.equal(session.initialEpoch,'deleted-epoch');
});
