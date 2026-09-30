import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectionDates,epochTagOverview} from './inspectionCellTree.js';
import {datedCellLabel} from './recordingIdentity.js';

test('full date overview keeps all four cells independently of 60-epoch pages and repeated labels',()=>{
  const cells=[
    {cell_uuid:'a',date:'2026-09-23',label:'Cell3',epochs:33},
    {cell_uuid:'b',date:'2026-09-23',label:'Cell5',epochs:39},
    {cell_uuid:'c',date:'2026-09-24',label:'Cell1',epochs:49},
    {cell_uuid:'d',date:'2026-09-24',label:'Cell3',epochs:52},
  ];
  const groups=inspectionDates(cells);
  assert.deepEqual(groups.map(g=>[g.date,g.cells.length,g.epochs]),[['2026-09-23',2,72],['2026-09-24',2,101]]);
  assert.deepEqual(groups.flatMap(g=>g.cells.map(c=>c.cell_uuid)),['a','b','c','d']);
});
test('epoch overview distinguishes inherited, direct, and dataset tags',()=>{
  assert.equal(epochTagOverview({}),'No tags');
  assert.equal(epochTagOverview({annotations:{cell_tags:[{tag:'ON'}],epoch_tags:[{tag:'noisy'}]},curation:{tags:['review']}}),'Cell: ON · Epoch: noisy · Dataset: review');
});
test('same-date same-label cells remain separate and have distinct identity qualifiers',()=>{
  const cells=[
    {cell_uuid:'12345678-aaaa-aaaa-aaaa-000000000001',date:'2026-06-11',label:'Cell3',epochs:3},
    {cell_uuid:'12345678-aaaa-aaaa-aaaa-000000000002',date:'2026-06-11',label:'Cell3',epochs:5},
    {cell_uuid:'another-cell',date:'2026-06-12',label:'Cell3',epochs:7},
  ],before=structuredClone(cells);
  const groups=inspectionDates(cells),same=groups[0].cells;
  assert.equal(groups[0].epochs,8);
  assert.deepEqual(same.map(cell=>cell.cell_uuid),cells.slice(0,2).map(cell=>cell.cell_uuid));
  assert.deepEqual(same.map(cell=>cell.label),['Cell3','Cell3']);
  assert.notEqual(same[0].identity_qualifier,same[1].identity_qualifier);
  assert.notEqual(datedCellLabel(same[0],true),datedCellLabel(same[1],true));
  assert.equal(groups[1].cells[0].identity_qualifier,undefined);
  assert.deepEqual(cells,before);
  const reversed=inspectionDates([...cells].reverse())[0].cells;
  for(const cell of reversed)assert.equal(cell.identity_qualifier,same.find(item=>item.cell_uuid===cell.cell_uuid).identity_qualifier);
});
test('many repeated labels use unique qualifiers without losing metadata or membership',()=>{
  const cells=Array.from({length:10000},(_,i)=>({cell_uuid:`shared-prefix-${i.toString().padStart(5,'0')}`,label:'Cell3',date:'2026-06-11',epochs:1,cell_type:'ON'}));
  const [group]=inspectionDates(cells);
  assert.equal(group.cells.length,10000);
  assert.equal(new Set(group.cells.map(cell=>cell.identity_qualifier)).size,10000);
  assert.ok(group.cells.every(cell=>cell.label==='Cell3'&&cell.cell_type==='ON'));
});
