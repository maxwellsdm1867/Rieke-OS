import test from 'node:test';
import assert from 'node:assert/strict';
import {advanceEpochIntent,epochIntentAt,epochAtIntent} from './epochNavigationIntent.js';
const page=(offset,total=1776)=>({offset,total,epochs:Array.from({length:Math.min(60,total-offset)},(_,i)=>({epoch_uuid:`e${offset+i}`}))});
test('repeated down keys across an unloaded boundary resolve the exact intended epoch',()=>{
 let intent=null;
 const first=page(0);
 for(let i=0;i<15;i++)intent=advanceEpochIntent({page:i?null:first,focused:'e58',intent,direction:1});
 assert.equal(intent.index,73);assert.equal(intent.offset,60);
 assert.equal(epochAtIntent(first,intent),null);
 assert.equal(epochAtIntent(page(60),intent),'e73');
});
test('direction reversal during a pending fetch does not select its stale page edge',()=>{
 let intent=epochIntentAt(63,1776);
 for(let i=0;i<8;i++)intent=advanceEpochIntent({intent,direction:-1});
 assert.equal(intent.index,55);
 assert.equal(epochAtIntent(page(60),intent),null);
 assert.equal(epochAtIntent(page(0),intent),'e55');
});
test('a held key can cross multiple unloaded pages and clamps to both ends',()=>{
 let intent=epochIntentAt(58,173);
 for(let i=0;i<200;i++)intent=advanceEpochIntent({intent,direction:1});
 assert.deepEqual(intent,{index:172,offset:120,total:173});
 assert.equal(epochAtIntent(page(120,173),intent),'e172');
 for(let i=0;i<200;i++)intent=advanceEpochIntent({intent,direction:-1});
 assert.equal(intent.index,0);
});
test('manual focus starts a fresh intent and missing anchors do not guess an index',()=>{
 assert.equal(advanceEpochIntent({page:page(60),focused:'not-in-page',intent:null,direction:1}),null);
 assert.equal(advanceEpochIntent({page:page(60),focused:'e80',intent:null,direction:-1}).index,79);
 assert.equal(epochIntentAt(0,0),null);
 assert.equal(epochIntentAt(900,20).index,19);
});
