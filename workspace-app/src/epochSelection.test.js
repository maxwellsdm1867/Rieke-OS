import test from 'node:test';
import assert from 'node:assert/strict';
import {toggleEpochSelection,mergeEpochSelection,epochSelectionRange} from './epochSelection.js';
const cells=[{cell_uuid:'a',epochs:65},{cell_uuid:'b',epochs:4}];
const endpoint=(cellUuid,index)=>({cellUuid,index,uuid:`${cellUuid}${index}`,revision:'query-A'});
const loadPage=async(cell,offset)=>({offset,query_revision:'query-A',total:cells.find(c=>c.cell_uuid===cell).epochs,
  epochs:Array.from({length:Math.min(60,cells.find(c=>c.cell_uuid===cell).epochs-offset)},(_,i)=>({epoch_uuid:`${cell}${offset+i}`,cell_uuid:cell}))});
test('command/control toggles only the clicked epoch and retains off-page selection',()=>{
  assert.deepEqual(toggleEpochSelection(['a1','b2'],'a1'),['b2']);
  assert.deepEqual(toggleEpochSelection(['a1','b2'],'a2'),['a1','b2','a2']);
  assert.deepEqual(mergeEpochSelection(['b2','a1'],['a1','a2']),['b2','a1','a2']);
});
test('shift range includes both endpoints across pagination in either direction',async()=>{
  const options={cells,anchor:endpoint('a',58),target:endpoint('a',63),loadPage};
  const expected=['a58','a59','a60','a61','a62','a63'];
  assert.deepEqual(await epochSelectionRange(options),expected);
  assert.deepEqual(await epochSelectionRange({...options,anchor:options.target,target:options.anchor}),expected);
});
test('shift range spans cells by displayed order and exact UUIDs',async()=>{
  assert.deepEqual(await epochSelectionRange({cells,anchor:endpoint('a',63),target:endpoint('b',2),loadPage}),['a63','a64','b0','b1','b2']);
});
test('range failure or reordering produces no partial selection',async()=>{
  await assert.rejects(epochSelectionRange({cells,anchor:endpoint('a',0),target:endpoint('b',2),loadPage:async(c,o)=>{if(c==='b')throw new Error('offline');return loadPage(c,o);}}),/offline/);
  await assert.rejects(epochSelectionRange({cells,anchor:{...endpoint('a',1),uuid:'different'},target:endpoint('a',4),loadPage}),/order changed/);
});
test('bounded selection refuses oversized ranges before loading',async()=>{
  await assert.rejects(epochSelectionRange({cells:[{cell_uuid:'a',epochs:1500}],anchor:endpoint('a',0),target:endpoint('a',1000),loadPage:()=>assert.fail('should not fetch')}),/1,000/);
  assert.throws(()=>mergeEpochSelection(Array.from({length:1000},(_,i)=>`${i}`),['extra']),/1,000/);
});
test('same endpoints and counts cannot conceal a different query revision inside a range',async()=>{
  await assert.rejects(epochSelectionRange({cells,anchor:endpoint('a',58),target:endpoint('a',63),
    loadPage:async(cell,offset)=>({...await loadPage(cell,offset),query_revision:offset?'query-B':'query-A'})}),/query changed/);
  await assert.rejects(epochSelectionRange({cells,anchor:endpoint('a',58),target:{...endpoint('a',63),revision:'query-B'},
    loadPage:()=>assert.fail('Endpoint revisions must agree before loading')}),/query changed/);
  await assert.rejects(epochSelectionRange({cells,anchor:endpoint('a',58),target:endpoint('a',63),
    loadPage:async(cell,offset)=>({...await loadPage(cell,offset),query_revision:undefined})}),/query changed/);
});
test('predicate ranges validate the explicit explorer revision receipt',async()=>{
  assert.deepEqual(await epochSelectionRange({cells,anchor:endpoint('a',63),target:endpoint('b',2),
    pageRevision:page=>page.revision,loadPage:async(cell,offset)=>({...await loadPage(cell,offset),query_revision:'irrelevant',revision:'query-A'})}),['a63','a64','b0','b1','b2']);
});
