import test from 'node:test';
import assert from 'node:assert/strict';
import {appendCellWindow,cellWindowOf} from './cellWindows.js';

const cell=id=>({cell_uuid:id});
test('a response with cells_total is one window; without it the list is complete',()=>{
  assert.deepEqual(cellWindowOf({cells:[cell('a')],cells_total:3,cells_next:1}),{total:3,next:1});
  assert.deepEqual(cellWindowOf({cells:[cell('a')],cells_total:1,cells_next:null}),{total:1,next:null});
  assert.equal(cellWindowOf({cells:[cell('a')]}),null,'old servers: complete list');
  assert.throws(()=>cellWindowOf({cells:[],cells_total:2,cells_next:0}));
});
test('later windows append in first-appearance order without duplicates',()=>{
  assert.deepEqual(appendCellWindow([cell('a'),cell('b')],[cell('b'),cell('c'),cell('c')]).map(item=>item.cell_uuid),['a','b','c']);
});

test('advertised pagination refuses malformed totals and an early terminal cursor',()=>{
 assert.throws(()=>cellWindowOf({cells:[cell('a')],cells_total:-1,cells_next:null}));
 assert.throws(()=>cellWindowOf({cells:[cell('a')],cells_total:3,cells_next:null}));
});
