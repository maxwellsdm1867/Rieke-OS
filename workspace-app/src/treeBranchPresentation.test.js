import test from 'node:test';
import assert from 'node:assert/strict';
import {branchLabel,branchTooltip,componentLabel,componentValue,epochLeafLabel,readableField} from './treeBranchPresentation.js';
const uuid='b5e8b847-3830-45e3-b46f-d6c2fa84e91c';
test('tree labels never use opaque identity keys as display fallbacks',()=>{
  assert.equal(branchLabel({value:uuid,key:'encoded-identity'},'cell'),'Cell · label not recorded');
  assert.equal(branchLabel({key:'joint/parameters%2Fhistory1+parameters%2Ftarget'}),'All epochs');
  assert.equal(branchLabel({value:uuid,label:'2026-09-24 · Cell 2'},'cell'),'2026-09-24 · Cell 2');
  assert.equal(branchLabel({value:uuid,label:'Block · 2026-09-24 13:02:03'},'block'),'Block · 2026-09-24 13:02:03');
});
test('composite display uses component labels while tooltip preserves exact source variable IDs and values',()=>{
  const node={components:[{field:'parameters/history1',label:'History 1 · mean / SD',value:[200,500],display_value:'Mean 200 · SD 500'},{field:'parameters/target',label:'Target',value:[0,60],display_value:'Mean 0 · SD 60'}]};
  assert.equal(branchLabel(node),'History 1: Mean 200 · SD 500 · Target: Mean 0 · SD 60');
  assert.equal(branchTooltip(node),'parameters/history1: [200,500]\nparameters/target: [0,60]');
  assert.equal(componentLabel(node.components[0]),'History 1');
});
test('missing and explicit null stay distinct and typed fallbacks preserve strings',()=>{
  assert.equal(componentValue({missing:true}),'Not recorded');
  assert.equal(componentValue({value:null}),'null (recorded)');
  assert.equal(branchLabel({value:1}),'1');
  assert.equal(branchLabel({value:'1'}),'"1"');
  assert.equal(branchLabel({missing:true,value:null}),'Not recorded');
});
test('epoch and field fallback labels remain readable without changing identities',()=>{
  assert.equal(epochLeafLabel({epoch_uuid:uuid,label:uuid.slice(0,8)}),'—');
  assert.equal(epochLeafLabel({epoch_uuid:uuid,epoch_number:12,start_time:'2026-09-24 12:34:56'}),'12 · 12:34:56');
  assert.equal(readableField(null,'joint/parameters%2Fa+parameters%2Fb'),'Combined fields');
  assert.equal(readableField(null,'parameters/frequencyCutoff'),'frequency Cutoff');
  assert.equal(branchTooltip({value:uuid},'cell'),`Field: cell\nSource value: "${uuid}"`);
});

test('subsecond timestamp precision remains in metadata tooltip, not dense tree rows',()=>{
  const node={value:uuid,label:'Block · 09/23/2026 16:45:07:922947'};
  assert.equal(branchLabel(node,'block'),'Block · 09/23/2026 16:45:07');
  assert.match(branchTooltip(node,'block'),/16:45:07:922947/);
  assert.equal(epochLeafLabel({label:'Epoch 1 · 16:45:10:056084'}),'1 · 16:45:10');
  assert.equal(node.value,uuid);
});
