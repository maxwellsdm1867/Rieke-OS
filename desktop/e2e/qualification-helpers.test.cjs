'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {cleanupOwnedFixture}=require('./qualification-helpers.cjs');
test('owned failure cleanup uses ordinary renderer Quit and observes successful exit',async()=>{
 const child=new EventEmitter();child.exitCode=null;let called=0;
 const page={evaluate:async callback=>{assert.match(String(callback),/riekeDesktop.quit/);called++;child.exitCode=0;child.emit('exit',0);}};
 assert.deepEqual(await cleanupOwnedFixture({process:()=>child},page,{timeout:50}),{state:'orderly-exit'});assert.equal(called,1);
});
test('unresponsive ordinary Quit is bounded and retained without force termination',async()=>{
 const child=new EventEmitter();child.exitCode=null;child.kill=()=>assert.fail('Cleanup must never force termination');
 const began=Date.now(),result=await cleanupOwnedFixture({process:()=>child},{evaluate:()=>new Promise(()=>{})},{timeout:20});
 assert.equal(result.state,'owned-fixture-retained');assert.match(result.reason,/deadline/);assert.ok(Date.now()-began<500);
});
test('cleanup does not reuse a stale page after the owned process has exited',async()=>{
 const result=await cleanupOwnedFixture({process:()=>({exitCode:0})},{evaluate:()=>assert.fail('No stale bridge call')});
 assert.deepEqual(result,{state:'already-exited',exit_code:0});
});
