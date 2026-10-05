import test from 'node:test';
import assert from 'node:assert/strict';
import {aggregateCellTypes} from "./protocol-overview/protocolOverviewModel.js";

test('type summaries deduplicate exact cell UUIDs and sum authoritative per-cell epoch membership once',()=>{
 const a={cell_uuid:'a',cell_type:'ON parasol',label:'Cell1',epochs:120,duration_seconds:12.5,exported:90,included:100,reviewed:40};
 const b={cell_uuid:'b',cell_type:'ON parasol',label:'Cell1',epochs:30,duration_seconds:3.5,exported:0,included:20,reviewed:3};
 const c={cell_uuid:'c',cell_type:'Unknown',epochs:2,duration_seconds:1,exported:0,included:0,reviewed:0};
 const d={cell_uuid:'d',cell_type:null,epochs:1,duration_seconds:0,exported:0,included:0,reviewed:0};
 const input=[a,b,c,d,a],before=structuredClone(input),rows=aggregateCellTypes(input);
 assert.equal(rows.reduce((n,row)=>n+row.count,0),4);assert.equal(rows.length,3);
 const parasol=rows.find(row=>row.type==='ON parasol');
 assert.deepEqual({count:parasol.count,epochs:parasol.epochs,duration:parasol.duration_seconds,exported:parasol.exported,included:parasol.included,reviewed:parasol.reviewed,withExports:parasol.withExports},{count:2,epochs:150,duration:16,exported:90,included:120,reviewed:43,withExports:1});
 assert.deepEqual(parasol.cells.map(cell=>cell.cell_uuid),['a','b']);assert.deepEqual(input,before);
 assert(rows.some(row=>row.type==='Unknown'));assert(rows.some(row=>row.type==='Unclassified'));
});
test('missing or invalid metrics stay unavailable independently; valid zero stays zero',()=>{
 const rows=aggregateCellTypes([{cell_uuid:'a',cell_type:'OFF midget',epochs:4,duration_seconds:2,exported:0,included:4,reviewed:0},{cell_uuid:'b',cell_type:'OFF midget',epochs:2,duration_seconds:null,exported:undefined,included:-1,reviewed:0}]);
 const row=rows[0];assert.equal(row.count,2);assert.equal(row.epochs,6);assert.equal(row.duration_seconds,null);assert.equal(row.exported,null);assert.equal(row.withExports,null);assert.equal(row.included,null);assert.equal(row.reviewed,0);
 for(const value of [undefined,null,NaN,Infinity,-1,'3',1.2]){
   const bad=aggregateCellTypes([{cell_uuid:'bad',epochs:value,duration_seconds:Infinity,exported:value}])[0];assert.equal(bad.epochs,null);assert.equal(bad.duration_seconds,null);assert.equal(bad.exported,null);
 }
 assert.deepEqual(aggregateCellTypes([]),[]);
});
test('a row without a cell UUID cannot become an authoritative distinct cell',()=>{
 const rows=aggregateCellTypes([{label:'Cell1',cell_type:'ON midget',epochs:5000},{cell_uuid:'real',label:'Cell1',cell_type:'Unknown',epochs:3,duration_seconds:1,exported:0}]);
 assert.equal(rows.length,1);assert.equal(rows[0].type,'Unknown');assert.equal(rows[0].count,1);assert.equal(rows[0].epochs,3);
});
