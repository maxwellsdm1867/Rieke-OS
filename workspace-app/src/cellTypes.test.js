import test from 'node:test';
import assert from 'node:assert/strict';
import {cellTypeColor,recordedCellType,distinctCells} from "./cell-qc/cellTypes.js";
import {protocolCellSummary} from "./protocol-overview/protocolOverviewModel.js";
import {overviewModel} from "./protocol-overview/ui/overviewModel.js";

test('scientific colors are stable across subset order and recorded spelling, without changing labels',()=>{
  for(const [name,color] of [['ON midget','var(--cell-on-midget)'],['OFF midget','var(--cell-off-midget)'],['ON parasol','var(--cell-on-parasol)'],['OFF parasol','var(--cell-off-parasol)']]) {
    for(const type of [name,name.replace(' ','-'),`RGC\\${name.replace(' ','-')}`]) {
      const cell={cell_type:type};assert.equal(cellTypeColor(type),color);assert.equal(recordedCellType(cell),type);
    }
  }
  for(const type of ['Unknown','Unclassified','OFF','ON parasol candidate','other',''])assert.equal(cellTypeColor(type),'var(--ink-muted)');
});
test('exact distinct cells and recorded labels survive overlapping cohorts and misleading epoch facets',()=>{
  const cells=[{cell_uuid:'a',label:'Cell1',cell_type:'RGC\\ON-midget',epochs:9000},
    {cell_uuid:'b',label:'Cell1',cell_type:'Unknown',epochs:2},{cell_uuid:'c',cell_type:'',epochs:3},
    {cell_uuid:'d',cell_type:'not recorded',epochs:4},{cell_uuid:'a',cell_type:'RGC\\ON-midget',epochs:9000}];
  const before=structuredClone(cells),summary=protocolCellSummary(cells),model=overviewModel({cells,counts:{cells:99999},catalog:{fields:[{id:'cell type',values:[{value:'RGC\\ON-midget',count:18000}]}]}});
  assert.equal(summary.matchingCells,4);assert.equal(model.totalCells,4);
  assert.deepEqual(new Map(summary.types.map(row=>[row.type,row.count])),new Map([['RGC\\ON-midget',1],['Unknown',1],['Unclassified',1],['not recorded',1]]));
  assert.equal(summary.unclassifiedCells,3);assert.deepEqual(cells,before);
  assert.equal(distinctCells([{uuid:'x'},{uuid:'x'},{uuid:'y'}]).length,2);
});
