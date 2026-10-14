'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {MainInspector,bounded}=require('./fault-main-inspector.cjs');
test('main observer refuses non-loopback or malformed inspector announcements',()=>{
  for(const url of ['ws://example.com:1234/abc','wss://127.0.0.1:1234/abc','ws://127.0.0.1:1234/not-a-uuid','ws://user@127.0.0.1:1234/abc'])assert.throws(()=>new MainInspector(url));
});
test('main observer evaluates, propagates exceptions and deadlines, then disconnects without killing its host',async()=>{
  // Owned inert Node fixture; no Electron, scientific services or user state.
  const child=spawn(process.execPath,['--inspect=127.0.0.1:0','-e','setInterval(()=>{},1000)'],{stdio:['ignore','ignore','pipe']});
  const exited=new Promise(resolve=>child.once('exit',resolve));let inspector;
  try{
    const endpoint=await bounded(new Promise((resolve,reject)=>{
      let text='';child.once('error',reject);child.once('exit',()=>reject(Error('Fixture exited')));
      child.stderr.on('data',chunk=>{text+=chunk;const url=text.match(/Debugger listening on (ws:\/\/\S+)/)?.[1];if(url)resolve(url);});
    }),10000,'Fixture inspector');
    inspector=new MainInspector(endpoint);await inspector.connect();
    const result=await inspector.command('Runtime.evaluate',{expression:'6*7',returnByValue:true});assert.equal(result.result.value,42);
    await assert.rejects(inspector.command('Runtime.evaluate',{expression:'throw Error("test exception")'}),/test exception/);
    await assert.rejects(inspector.command('Runtime.evaluate',{expression:'new Promise(()=>{})',awaitPromise:true},30),/timed out/);
    assert.equal(inspector.pending.size,0);
    assert.equal((await inspector.command('Runtime.evaluate',{expression:'21*2',returnByValue:true})).result.value,42);
    inspector.close();await new Promise(resolve=>setTimeout(resolve,50));
    assert.equal(child.exitCode,null,'Disconnect must not terminate the observed process');
    await assert.rejects(inspector.command('Runtime.enable',{}),/unavailable/);
  }finally{inspector?.close();child.kill('SIGTERM');await bounded(exited,5000,'Owned inert fixture shutdown');}
});

test('Electron readiness waits for owning bootstrap state and does not import or mask errors',async()=>{
  const inspector=new MainInspector('ws://127.0.0.1:1234/abc');let calls=0;
  inspector.command=async(method,params)=>{
    assert.equal(method,'Runtime.evaluate');assert.ok(!params.expression.includes("require('electron')"));
    return {result:{value:++calls===1?{type:'browser',ready:false}:{type:'browser',filename:'/fixture/app.asar/main.cjs',ready:true}}};
  };
  assert.equal((await inspector.waitForElectronMain(1000)).filename,'/fixture/app.asar/main.cjs');assert.equal(calls,2);
  inspector.command=async()=>({result:{value:{ready:false}}});
  await assert.rejects(inspector.waitForElectronMain(20),/did not become ready/);
  inspector.command=async()=>{throw Error('real inspector failure');};
  await assert.rejects(inspector.waitForElectronMain(1000),/real inspector failure/);
});
