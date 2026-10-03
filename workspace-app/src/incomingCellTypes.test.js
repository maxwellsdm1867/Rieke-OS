import test from 'node:test';
import assert from 'node:assert/strict';
import {incomingCellTypes} from './incomingCellTypes.js';

test('recorded mixed types count unique cell identities, never epoch totals or reused labels',()=>{
 const a={cell_uuid:'a',label:'Cell1',cell_type:'RGC\\ON-midget',epochs:999};
 const cells=[a,{cell_uuid:'b',label:'Cell1',cell_type:'RGC\\ON-midget',epochs:1},{cell_uuid:'c',cell_type:'ON-parasol'},a];
 assert.deepEqual(incomingCellTypes(cells,3),[{type:'RGC\\ON-midget',count:2},{type:'ON-parasol',count:1}]);
 assert.deepEqual(incomingCellTypes(cells.filter(cell=>cell.cell_uuid==='a'),1),[{type:'RGC\\ON-midget',count:1}]);
});
test('unknown recorded types are separate from known types without inferring from labels',()=>{
 assert.deepEqual(incomingCellTypes([{cell_uuid:'a',cell_type:'Unknown'},{cell_uuid:'b',cell_type:' '},{cell_uuid:'c',label:'ON midget'},{cell_uuid:'d',cell_type:'unexpected recorded value'}],4),[{type:'unexpected recorded value',count:1},{type:'Unclassified',count:3}]);
});
test('incomplete receipts, identity conflicts and unavailable data never produce a false zero',()=>{
 for(const [cells,count] of [[null,0],[[],null],[[],1],[[{label:'Cell1'}],1],[[{cell_uuid:'a',cell_type:'ON'},{cell_uuid:'a',cell_type:'OFF'}],1]])assert.equal(incomingCellTypes(cells,count),null);
 assert.deepEqual(incomingCellTypes([],0),[]);
});
