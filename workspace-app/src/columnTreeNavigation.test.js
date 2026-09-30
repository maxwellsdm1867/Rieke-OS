import test from 'node:test';
import assert from 'node:assert/strict';
import {columnAncestorPages,canReuseColumn,columnSelectionNeedsAnchor,columnBranchNavigation,columnWheelDelta} from './columnTreeNavigation.js';

test('selected epoch reconstructs ancestor pages beyond the first sixty branches',()=>{
  const page={revision:'exact',path:['date-key','cell-key','block-key'],ancestors:[{parent_offset:120},{parent_offset:60},{parent_offset:180}]};
  const targets=columnAncestorPages(page,{anchor:true,columnPositions:[{offset:0},{offset:0},{offset:0}]});
  assert.deepEqual(targets.map(item=>item.offset),[120,60,180]);
  assert.deepEqual(targets.map(item=>item.path),[[],['date-key'],['date-key','cell-key']]);
  assert.ok(targets.every(item=>item.revision==='exact'));
  assert.equal(canReuseColumn({revision:'exact',path:[],offset:0},targets[0]),false);
  assert.equal(canReuseColumn({revision:'stale',path:[],offset:120},targets[0]),false);
  assert.equal(canReuseColumn({revision:'exact',path:[],offset:120},targets[0]),true);
});
test('ordinary navigation keeps saved offsets; incomplete anchor receipts fail visibly',()=>{
  const page={revision:'r',path:['a'],ancestors:[{parent_offset:120}]};
  assert.equal(columnAncestorPages(page,{columnPositions:[{offset:60} ]})[0].offset,60);
  assert.throws(()=>columnAncestorPages({...page,ancestors:[]},{anchor:true}),/could not be located/);
  assert.deepEqual(columnAncestorPages({revision:'r',path:[]},{anchor:true}),[]);
});
test('external selections already present need no request, while pending or other-branch selections anchor',()=>{
  const columns=[{kind:'branches'},{kind:'epochs',epochs:[{epoch_uuid:'shown'}]}];
  assert.equal(columnSelectionNeedsAnchor(columns,'shown'),false);
  assert.equal(columnSelectionNeedsAnchor(columns,'different'),true);
  assert.equal(columnSelectionNeedsAnchor(columns,'shown',true),true);
  assert.equal(columnSelectionNeedsAnchor(columns,null),false);
});

test('closing a column branch returns to its parent page without selecting a descendant',()=>{
 const page={path:['date'],offset:60},cell={key:'cell3',path:['date','cell3']};
 assert.deepEqual(columnBranchNavigation(page,cell,'cell3'),{opening:false,path:['date'],offset:60});
 assert.deepEqual(columnBranchNavigation(page,cell,'cell5'),{opening:true,path:['date','cell3'],offset:0});
});


test('horizontal and Shift-wheel gestures cross columns while vertical gestures stay local',()=>{
 assert.equal(columnWheelDelta({deltaX:90,deltaY:3},600),90);
 assert.equal(columnWheelDelta({deltaX:-90,deltaY:3},600),-90);
 assert.equal(columnWheelDelta({deltaX:3,deltaY:90},600),0);
 assert.equal(columnWheelDelta({deltaY:4,shiftKey:true,deltaMode:1},600),64);
 assert.equal(columnWheelDelta({deltaX:1,deltaMode:2},600),600);
});
