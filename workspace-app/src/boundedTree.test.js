import test from 'node:test';
import assert from 'node:assert/strict';
import {boundedTreePage,inspectionTreeFocus,groupedCellPage} from './boundedTree.js';
import {indexInspectionTree} from './inspectionScope.js';

test('50,000 groups remain reachable without mounting all groups or losing off-page focus',()=>{
  const nodes=Array.from({length:50_000},(_,i)=>({key:`group-${i}`}));
  const first=boundedTreePage(nodes,0,60,nodes.at(-1));
  assert.equal(first.items.length,61);
  assert.equal(first.total,50_000);
  assert.equal(first.pinnedOutside,true);
  assert.equal(first.items.at(-1),nodes.at(-1));
  const seen=[];
  for(let offset=0;offset<nodes.length;offset+=60){
    const page=boundedTreePage(nodes,offset);
    assert.ok(page.items.length<=60);
    seen.push(...page.items);
  }
  assert.deepEqual(seen,nodes);
  const end=boundedTreePage(nodes,49_980,60,nodes.at(-1));
  assert.equal(end.pinnedOutside,false);
  assert.equal(end.items.length,20);
  assert.equal(end.hasNext,false);
});
test('page clamps after scope shrinks and never inserts a focus from another scope',()=>{
  const nodes=Array.from({length:64},(_,i)=>({key:i}));
  const page=boundedTreePage(nodes,49_980,60,{key:'foreign'});
  assert.equal(page.offset,60);
  assert.equal(page.end,64);
  assert.equal(page.items.length,4);
  assert.equal(page.pinnedOutside,false);
  assert.deepEqual(boundedTreePage([],120).items,[]);
  assert.equal(boundedTreePage([],120).offset,0);
});
test('only exact selected epoch ancestors auto-open, even when its cell occurs in every branch',()=>{
  const children=Array.from({length:20_000},(_,i)=>({key:`group-${i}`,epochs:[{epoch_uuid:`e-${i}`,cell_uuid:'same-cell'}]}));
  const tree={count:20_000,children};
  const index=indexInspectionTree(tree);
  const focus=inspectionTreeFocus(index,'e-19999');
  assert.equal(index.cellBranches.get('same-cell').size,20_001);
  assert.deepEqual([...focus.branches],[children.at(-1),tree]);
  assert.equal(focus.childOf.get(tree),children.at(-1));
  assert.equal(focus.epoch,children.at(-1).epochs[0]);
  assert.equal(boundedTreePage(children,0,60,focus.childOf.get(tree)).items.length,61);
  assert.equal(inspectionTreeFocus(index,'unknown').branches.size,0);
  assert.equal(tree.count,20_000);
});
test('grouped cell pages preserve complete type counts and every dated identity',()=>{
  const cells=Array.from({length:10_003},(_,i)=>({cell_uuid:`cell-${i}`,date:i%2?'2026-09-23':'2026-09-24',cell_type:i%3?'Parasol':'Midget'}));
  const expected=[...cells.filter(c=>c.cell_type==='Midget'),...cells.filter(c=>c.cell_type==='Parasol')];
  const actual=[];
  for(let offset=0;offset<cells.length;offset+=60){
    const page=groupedCellPage(cells,offset);
    assert.ok(page.items.length<=60);
    assert.equal(page.total,cells.length);
    for(const group of page.groups){
      assert.equal(group.total,group.type==='Midget'?3335:6668);
      actual.push(...group.cells);
    }
  }
  assert.deepEqual(actual,expected);
  assert.equal(new Set(actual.map(c=>c.cell_uuid)).size,cells.length);
  assert.equal(groupedCellPage(cells.slice(0,2),9960).offset,0);
});
