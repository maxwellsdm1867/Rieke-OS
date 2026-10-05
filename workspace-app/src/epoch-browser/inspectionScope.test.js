import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectionSearches,indexInspectionTree,focusAfterTreeSelection,curationMatchesCellFocus} from './inspectionScope.js';

test('clicked cell focus narrows navigation without changing shared tree filters',()=>{
  const filters={group_label:'NBQX5um',cell_type:'OFF parasol'};
  const before=inspectionSearches(filters),focused=inspectionSearches(filters,'cell-two');
  assert.equal(focused.protocol,before.protocol);
  assert.equal(new URLSearchParams(focused.navigation).get('cell_uuid'),'cell-two');
  assert.equal(new URLSearchParams(focused.navigation).get('group_label'),'NBQX5um');
  assert.equal(new URLSearchParams(inspectionSearches({cell_uuid:'explicit'}).protocol).get('cell_uuid'),'explicit');
  assert.equal(inspectionSearches(filters,null).navigation,before.protocol);
  assert.equal(new URLSearchParams(inspectionSearches({cell_uuid:'explicit'},'other').navigation).get('cell_uuid'),'explicit');
});
test('a cell can focus multiple branches without changing tree membership or split order',()=>{
  const first={value:25,epochs:[{epoch_uuid:'a',cell_uuid:'one'},{epoch_uuid:'b',cell_uuid:'two'}]};
  const second={value:50,epochs:[{epoch_uuid:'c',cell_uuid:'two'}]};
  const tree={split_order:['parameters/frequencyCutoff','cell'],count:3,children:[first,second]};
  const snapshot=JSON.stringify(tree),index=indexInspectionTree(tree);
  assert.deepEqual([...index.cellBranches.get('two')],[tree,first,second]);
  assert.equal(index.epochCells.get('c'),'two');
  assert.equal(JSON.stringify(tree),snapshot);
});
test('selecting another cell or unknown tree leaf clears navigation focus',()=>{
  const index=indexInspectionTree({epochs:[{epoch_uuid:'a',cell_uuid:'one'},{epoch_uuid:'b',cell_uuid:'two'}]});
  assert.equal(focusAfterTreeSelection('one','a',index),'one');
  assert.equal(focusAfterTreeSelection('one','b',index),null);
  assert.equal(focusAfterTreeSelection('one','unknown',index),null);
  assert.equal(focusAfterTreeSelection(null,'a',index),null);
});
test('bulk writes fail closed if any target lies outside the focused cell',()=>{
  assert.equal(curationMatchesCellFocus([{cell_uuid:'one'}],'one'),true);
  assert.equal(curationMatchesCellFocus([{cell_uuid:'one'},{cell_uuid:'two'}],'one'),false);
  assert.equal(curationMatchesCellFocus([{}],'one'),false);
  assert.equal(curationMatchesCellFocus([{cell_uuid:'two'}],null),true);
});
