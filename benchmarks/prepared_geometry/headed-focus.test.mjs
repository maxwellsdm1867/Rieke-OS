import test from 'node:test';
import assert from 'node:assert/strict';
import {acquireForeground,verifyForeground,requireOwnedForeground,requireObservedFocus} from './headed-focus.mjs';
const dom={visibility:'visible',focus:true},native={pid:42,active:true};
test('foreground acquisition precedes intent, is bounded, and invokes no frames or clicks',async()=>{
 const events=[];const page={async bringToFront(){events.push('front');},async waitForFunction(predicate,arg,options){events.push('wait');assert.equal(arg,null);assert.deepEqual(options,{timeout:5000,polling:50});},async evaluate(){events.push('DOM');return dom;}};
 const result=await acquireForeground(page,42,'/helper',async helper=>{assert.equal(helper,'/helper');events.push('OS');return native;});
 assert.deepEqual(events,['front','wait','DOM','OS']);assert.equal(result.owner_pid,42);assert.equal(result.native.pid,42);assert.ok(result.setup_elapsed_ms>=0);
});
for(const [name,d,n,pid] of [['hidden',{visibility:'hidden',focus:true},native,42],['unfocused',{visibility:'visible',focus:false},native,42],['other-app',dom,{pid:43,active:true},42],['inactive',dom,{pid:42,active:false},42],['invalid-owner',dom,native,0]])test(`foreground admission refuses ${name}`,()=>assert.throws(()=>requireOwnedForeground(d,n,pid),/Environment admission failed/));
test('completion check does not activate the window or drive frames',async()=>{
 let reads=0;const page={async evaluate(){return dom;},bringToFront(){throw Error('must not activate after intent');}};
 const result=await verifyForeground(page,42,'/helper',async()=>{reads++;return native;});assert.equal(reads,1);assert.equal(result.native.pid,42);
});
test('focus acquisition timeout includes a stuck bringToFront operation',async()=>{
 const page={bringToFront:()=>new Promise(()=>{})};
 await assert.rejects(acquireForeground(page,42,'/helper',async()=>native,10),/timed out before intent/);
});
test('every observed callback must preserve visibility and DOM focus',()=>{
 assert.doesNotThrow(()=>requireObservedFocus({frames:[dom],readiness:[dom]}));
 assert.throws(()=>requireObservedFocus({frames:[dom],readiness:[{...dom,focus:false}]}),/changed during observation/);
 assert.throws(()=>requireObservedFocus({frames:[],readiness:[]}),/changed during observation/);
});
