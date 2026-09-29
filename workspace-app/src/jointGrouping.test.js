import test from 'node:test';
import assert from 'node:assert/strict';
import {jointId,jointComponents,jointDefinition,combineLevels} from './jointGrouping.js';

test('composite IDs survive legacy comma-separated recipes and round-trip exact field IDs',()=>{
  const fields=['parameters/history1','metadata/cell/properties/a+b,c%2F'];
  const id=jointId(fields);
  assert.ok(!id.includes(','));
  assert.deepEqual(jointComponents(id),fields);
  assert.equal(jointComponents('joint/a%2fb+c').length,0); // noncanonical escape
  assert.throws(()=>jointId(['a','a']));
  assert.throws(()=>jointId(['a','joint/b+c']));
  assert.throws(()=>jointId(['a']));
});
test('combining replaces separate axes in place and retains unrelated shared levels',()=>{
  const order=['date','cell','h1','h2','duration','target','block'];
  assert.deepEqual(combineLevels(order,['h1','h2','target']),['date','cell','joint/h1+h2+target','duration','block']);
  assert.deepEqual(order,['date','cell','h1','h2','duration','target','block']);
  assert.deepEqual(combineLevels(['date','block'],['h1','h2','target']),['date','block','joint/h1+h2+target']);
  assert.throws(()=>combineLevels(['a','b','c','d','e','f','g','h'],['x','y']));
});
test('saved composites show recorded labels and refuse unknown component identities',()=>{
  const fields=[{id:'a',label:'History 1 · mean / SD'},{id:'b',label:'Target · mean / SD'}];
  assert.equal(jointDefinition('joint/a+b',fields).label,'History 1 + Target');
  assert.equal(jointDefinition('joint/a+c',fields),null);
});
