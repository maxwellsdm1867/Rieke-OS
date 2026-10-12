import test from 'node:test';
import assert from 'node:assert/strict';
import {cellTypeColor,cellTypePresentation,recordedCellType,distinctCells} from "./cell-qc/cellTypes.js";
import {protocolCellSummary} from "./protocol-overview/protocolOverviewModel.js";
import {overviewModel} from "./protocol-overview/ui/overviewModel.js";

test('polarity colors are stable across subset order and recorded spelling, without changing labels',()=>{
  for(const [name,color] of [['ON midget','var(--cell-on)'],['OFF midget','var(--cell-off)'],['ON parasol','var(--cell-on)'],['OFF parasol','var(--cell-off)']]) {
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

test('retinal icons follow exact recorded classes and polarity without inferring from labels',()=>{
  const examples=[
    ['ON parasol','ganglion','on','on-parasol'],['OFF parasol','ganglion','off','off-parasol'],
    ['ON midget','midget','on','on-midget'],['OFF midget','midget','off','off-midget'],
    ['ON bipolar','bipolar','on','on-bipolar'],['OFF bipolar','bipolar','off','off-bipolar'],
    ['Cone','cone',undefined,'cone'],['Rod','rod',undefined,'rod'],['Horizontal cell','horizontal',undefined,'horizontal'],
  ];
  for(const [type,shape,polarity,token] of examples){
    for(const spelling of [type,type.toUpperCase(),` ${type.replaceAll(' ','_')} `,type.replaceAll(' ','-')]){
      const cell=Object.freeze({cell_uuid:'recorded-id',cell_type:spelling});
      const presentation=cellTypePresentation(recordedCellType(cell));
      assert.equal(presentation.shape,shape);assert.equal(presentation.polarity,polarity);
      assert.equal(presentation.color,polarity?`var(--cell-${polarity})`:'var(--ink-muted)');assert.equal(recordedCellType(cell),spelling);
    }
  }
  for(const [type,canonical] of [
    ['RGC\\ON-midget','ON midget'],['RGC/OFF-parasol','OFF parasol'],
    ['Bipolar\\ON','ON bipolar'],['BC/OFF','OFF bipolar'],['ON bipolar cell','ON bipolar'],
    ['Photoreceptor/Cone','Cone'],['Photoreceptors/Rods','Rod'],['Cones','Cone'],['Rod cells','Rod'],['HC','Horizontal cell'],['Horizontal cells','Horizontal cell'],
  ])assert.deepEqual(cellTypePresentation(type),cellTypePresentation(canonical));
  for(const type of ['ON parasol candidate','possible cone','horizontal candidate','other/Horizontal','rod bipolar','ON-OFF bipolar','other/ON midget','OFF','Unknown',''])
    assert.equal(cellTypePresentation(type).color,'var(--ink-muted)',type);
  assert.equal(cellTypePresentation(recordedCellType({label:'ON parasol'})).color,'var(--ink-muted)');
});
