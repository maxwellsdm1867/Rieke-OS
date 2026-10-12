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
      assert.equal(presentation.color,polarity?`var(--cell-${polarity})`:shape==='cone'?'var(--ink-muted)':'var(--cell-outer)');assert.equal(recordedCellType(cell),spelling);
    }
  }
  for(const [type,canonical] of [
    ['RGC\\ON-midget','ON midget'],['RGC/OFF-parasol','OFF parasol'],
    ['Bipolar\\ON','ON bipolar'],['BC/OFF','OFF bipolar'],['ON bipolar cell','ON bipolar'],
    ['Photoreceptor/Cone','Cone'],['Photoreceptors/Rods','Rod'],['Cones','Cone'],['Rod cells','Rod'],['HC','Horizontal cell'],['Horizontal cells','Horizontal cell'],
  ])assert.deepEqual(cellTypePresentation(type),cellTypePresentation(canonical));
  for(const type of ['ON parasol candidate','possible cone','horizontal candidate','other/Horizontal','ON-OFF bipolar','other/ON midget','OFF','Unknown',''])
    assert.equal(cellTypePresentation(type).color,'var(--ink-muted)',type);
  for(const type of ['Bipolar','BC','Bipolar cell','Unspecified-type bipolar','Generic bipolar','BC/Unspecified','Bipolar/Unknown'])
    assert.deepEqual(cellTypePresentation(type),{shape:'bipolar',color:'var(--ink-muted)'},type);
  for(const type of ['Amacrine','Amacrine cell','Generic amacrine','AC','Amacrine/Unspecified'])
    assert.deepEqual(cellTypePresentation(type),{shape:'amacrine',color:'var(--ink-muted)'},type);
  for(const type of ['possible amacrine','other/Amacrine'])assert.equal(cellTypePresentation(type).shape,'generic');
  assert.deepEqual(cellTypePresentation(recordedCellType({label:'ON parasol'})),{shape:'generic',color:'var(--ink-muted)'});
});


test('complete recorded taxonomy retains family context, exact subtype and neutral family fallback',()=>{
  const cases=[
    ['RGC/ON-parasol','ganglion',undefined,'on','cell-on'],['RGC/OFF-parasol','ganglion',undefined,'off','cell-off'],
    ['RGC/ON-midget','midget',undefined,'on','cell-on'],['RGC/OFF-midget','midget',undefined,'off','cell-off'],
    ['RGC/small bistratified','bistratified',undefined,undefined,'ink-muted'],
    ['amacrine/AII','amacrine','aii',undefined,'ink-muted'],['amacrine/A17','amacrine','a17',undefined,'ink-muted'],['amacrine/starburst','amacrine','starburst',undefined,'ink-muted'],
    ['bipolar/OFF-diffuse','bipolar','diffuse','off','cell-off'],['bipolar/OFF-midget','bipolar','midget','off','cell-off'],
    ['bipolar/ON-diffuse','bipolar','diffuse','on','cell-on'],['bipolar/ON-midget','bipolar','midget','on','cell-on'],['bipolar/rod','bipolar','rod','on','cell-on'],
    ['horizontal','horizontal',undefined,undefined,'cell-outer'],
    ['photoreceptor/S cone','cone',undefined,undefined,'cell-cone-s'],['photoreceptor/M cone','cone',undefined,undefined,'cell-cone-m'],['photoreceptor/L cone','cone',undefined,undefined,'cell-cone-l'],
    ['photoreceptor/rod','rod',undefined,undefined,'cell-outer'],['unknown','generic',undefined,undefined,'ink-muted'],
  ];
  for(const [type,shape,variant,polarity,token] of cases){
    for(const spelling of [type,type.replaceAll('/','\\'),type.toUpperCase().replaceAll(' ','_')]){
      const cell=Object.freeze({cell_uuid:'recorded-cell',cell_type:spelling});
      const presentation=cellTypePresentation(recordedCellType(cell));
      assert.equal(presentation.shape,shape,spelling);assert.equal(presentation.variant,variant,spelling);
      assert.equal(presentation.polarity,polarity,spelling);assert.equal(presentation.color,`var(--${token})`,spelling);
      assert.equal(recordedCellType(cell),spelling);
    }
  }
  for(const [family,shape] of [['RGC','ganglion'],['bipolar','bipolar'],['amacrine','amacrine'],['photoreceptor','photoreceptor'],['horizontal','horizontal']]){
    for(const subtype of ['unknown','unspecified','new unrecognized subtype','ON-midget candidate'])
      assert.deepEqual(cellTypePresentation(`${family}/${subtype}`),{shape,color:'var(--ink-muted)'});
  }
  assert.equal(cellTypePresentation('ON-midget').shape,'midget');
  assert.equal(cellTypePresentation('ON midget bipolar').variant,'midget');
  assert.equal(cellTypePresentation('Rod bipolar').variant,'rod');
  for(const label of ['possible AII','S cone candidate','other/A17','possible starburst'])assert.deepEqual(cellTypePresentation(label),{shape:'generic',color:'var(--ink-muted)'});
});
