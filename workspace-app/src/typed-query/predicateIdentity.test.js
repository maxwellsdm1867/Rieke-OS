import test from 'node:test';
import assert from 'node:assert/strict';
import {predicateIdentity} from './predicateIdentity.js';
test('server-sorted saved predicate matches rebuilt editor predicate',()=>{
  assert.equal(predicateIdentity({all:[{field:'protocol',operator:'eq',value:'Noise'}]}),predicateIdentity({all:[{operator:'eq',value:'Noise',field:'protocol'}]}));
});
test('values and ordered tree splits remain distinct',()=>{
  assert.notEqual(predicateIdentity({value:100}),predicateIdentity({value:'100'}));
  assert.notEqual(predicateIdentity({splits:['date','cell']}),predicateIdentity({splits:['cell','date']}));
});
