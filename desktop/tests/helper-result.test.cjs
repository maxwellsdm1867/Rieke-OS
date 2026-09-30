'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {waitForHelperResult,inspectOwnedHelper}=require('../e2e/helper-result.cjs');
test('an atomically published owned native helper outcome completes observation',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-helper-result-'));try{
  const resultPath=path.join(root,'result.json');await fs.writeFile(resultPath,JSON.stringify({state:'Installed',version:'0.1.3'}));
  const result=await waitForHelperResult({resultPath,inspectHelper:()=>assert.fail('Completed outcome needs no process probe')});assert.equal(result.result.state,'Installed');
 }finally{await fs.rm(root,{recursive:true});}
});
test('dead, zombie and reused helper identities fail immediately after one final outcome reread',async()=>{
 for(const state of[{alive:false,owned:false,status:'absent'},{alive:false,owned:true,status:'Z'},{alive:true,owned:false,status:'S'}]){
  let reads=0;await assert.rejects(waitForHelperResult({readResult:async()=>{reads++;return null;},inspectHelper:async()=>state,delay:()=>assert.fail('Dead helper must not consume fifteen minutes')}),/exited|zombie|reused/);assert.equal(reads,2);
 }
});
test('a result published during helper exit wins the final reread race',async()=>{
 let reads=0;const result=await waitForHelperResult({readResult:async()=>++reads===1?null:{state:'Restored'},inspectHelper:async()=>({alive:false,owned:false,status:'absent'})});assert.equal(result.result.state,'Restored');
});
test('a live owned helper has a bounded deadline and periodic safe observations',async()=>{
 let clock=0;const heartbeats=[];await assert.rejects(waitForHelperResult({phase:'update',timeoutMs:1000,pollMs:250,heartbeatMs:400,now:()=>clock,delay:async ms=>{clock+=ms;},readResult:async()=>null,inspectHelper:async()=>({alive:true,owned:true,status:'S'}),onHeartbeat:async value=>heartbeats.push(value)}),/bounded result deadline/);
 assert.equal(clock,1000);assert.equal(heartbeats.length,1);assert.equal(heartbeats[0].phase,'update');
});
test('malformed outcomes and permanent read failures are reported rather than treated as absent',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-helper-result-'));try{
  const resultPath=path.join(root,'result.json');await fs.writeFile(resultPath,'{broken');await assert.rejects(waitForHelperResult({resultPath}),SyntaxError);
  await assert.rejects(waitForHelperResult({readResult:async()=>{const error=new Error('denied');error.code='EACCES';throw error;}}),/denied/);
 }finally{await fs.rm(root,{recursive:true});}
});
test('real inert Node-child observation requires the exact owned wrapper and config',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-helper-pid-'));let child;try{
  const wrapper=path.join(root,'wrapper.cjs'),configFile=path.join(root,'config.json'),foreign=path.join(root,'different-config.json');await fs.writeFile(wrapper,'setInterval(()=>{},1000);');await fs.writeFile(configFile,'{}');await fs.writeFile(foreign,'{}');
  child=require('node:child_process').spawn(process.execPath,[wrapper,configFile],{stdio:'ignore'});await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});
  assert.equal((await inspectOwnedHelper(child.pid,{wrapper,configFile})).owned,true);assert.equal((await inspectOwnedHelper(child.pid,{wrapper,configFile:foreign})).owned,false);
 }finally{if(child){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');await exited;}await fs.rm(root,{recursive:true});}
});
test('nonfinite or nonpositive polling/deadline values cannot produce an unbounded wait',async()=>{
 for(const options of[{timeoutMs:Infinity},{timeoutMs:0},{pollMs:NaN},{pollMs:-1},{timeoutMs:900001}])await assert.rejects(waitForHelperResult({...options,readResult:()=>assert.fail('Invalid configuration cannot read or observe a process')}),/duration|fifteen minutes/);
});
