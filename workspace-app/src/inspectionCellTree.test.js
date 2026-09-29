import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectionDates,epochTagOverview} from './inspectionCellTree.js';

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
