import test from 'node:test';
import assert from 'node:assert/strict';
import {isTypingProtocol,recordingStorage,sizeLabel} from './protocolOverviewModel.js';
test('typing recordings stay separate from experimental noise protocols',()=>{
 for(const name of ['SingleSpot','ExpandingSpots','SplitFieldCentering'])assert.equal(isTypingProtocol({acquisition_protocol:`lab.${name}`}),true);
 for(const name of ['VariableMeanNoise','VariableMeanNoiseCurInject','VariableHistoryNoiseCurInject'])assert.equal(isTypingProtocol({name}),false);
 assert.equal(isTypingProtocol({definition:{name:'Expanding Spots'}}),true);
});
test('source sizes deduplicate shared H5 files and never treat missing files as zero',()=>{
 const files=[{source_sha256:'a',file_status:'available',size_bytes:2000000},{source_sha256:'b',file_status:'missing',size_bytes:9000000}];
 assert.deepEqual(recordingStorage(files,['a','a']),{bytes:2000000,knownBytes:2000000,unknown:0,sources:1});
 assert.equal(recordingStorage(files,['a','b']).bytes,null);
 assert.equal(recordingStorage(files,['unregistered']).unknown,1);
 assert.equal(recordingStorage(files,[]).bytes,0);
 assert.equal(sizeLabel(2000000),'2.0 MB');
});

test('protocol type counts use unique cell identities and distinguish export participation',async()=>{
 const {protocolCellTypes}=await import('./protocolOverviewModel.js');
 const cells=[
  {cell_uuid:'date1-cell1',label:'Cell1',cell_type:'ON-parasol',epochs:100,exported:1},
  {cell_uuid:'date2-cell1',label:'Cell1',cell_type:'ON-parasol',epochs:2,exported:0},
  {cell_uuid:'date1-cell1',label:'Cell1',cell_type:'ON-parasol',epochs:100,exported:1},
  {cell_uuid:'off',cell_type:'OFF-parasol',exported:2},
  {cell_uuid:'unknown',cell_type:''},
 ];
 assert.deepEqual(protocolCellTypes(cells),[
  {type:'ON-parasol',count:2,withExports:1},
  {type:'OFF-parasol',count:1,withExports:1},
  {type:'Unclassified',count:1,withExports:0},
 ]);
 assert.deepEqual(protocolCellTypes([]),[]);
});

test('headline counts recorded types separately from unclassified cells',async()=>{
 const {protocolCellSummary}=await import('./protocolOverviewModel.js');
 const summary=protocolCellSummary([{cell_uuid:'a',cell_type:'ON-parasol'},{cell_uuid:'a',cell_type:'ON-parasol'},{cell_uuid:'b',cell_type:'OFF-parasol'},{cell_uuid:'c',cell_type:' '},{cell_uuid:'d',cell_type:'Unknown'}]);
 assert.equal(summary.matchingCells,4);
 assert.equal(summary.cellTypes,2);
 assert.equal(summary.unclassifiedCells,2);
 assert.equal(protocolCellSummary([]).cellTypes,0);
});
