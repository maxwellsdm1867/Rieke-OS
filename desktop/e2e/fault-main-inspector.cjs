'use strict';
// Test-only observer: Node main inspector only. No browser CDP auto-attachment,
// application patches, or lifecycle signals. The caller owns the spawned app.
const assert=require('node:assert/strict');
function bounded(promise,ms,label){
  let timer;
  return Promise.race([promise,new Promise((_resolve,reject)=>{timer=setTimeout(()=>reject(Error(label+' timed out')),ms);})]).finally(()=>clearTimeout(timer));
}
class MainInspector {
  constructor(endpoint){
    const url=new URL(endpoint);
    assert.equal(url.protocol,'ws:');assert.equal(url.hostname,'127.0.0.1');
    assert.ok(url.port&&!url.username&&!url.password&&!url.search&&!url.hash);
    assert.match(url.pathname,/^\/[a-f0-9-]+$/i);
    this.url=url.href;this.pending=new Map();this.nextId=0;this.context=null;this.closed=false;
  }
  async connect(){
    this.socket=new WebSocket(this.url);
    const fail=message=>{this.closed=true;for(const item of this.pending.values())item.reject(Error(message));this.pending.clear();};
    this.socket.addEventListener('message',event=>{
      try{
        assert.equal(typeof event.data,'string');assert.ok(Buffer.byteLength(event.data)<16*1024*1024);
        const message=JSON.parse(event.data);
        if(message.method==='Runtime.executionContextCreated'&&message.params.context.auxData?.isDefault){
          assert.ok(this.context===null||this.context===message.params.context.id,'Main context changed');
          this.context=message.params.context.id;
        }
        if(message.method==='Runtime.executionContextsCleared'||message.method==='Runtime.executionContextDestroyed'&&message.params.executionContextId===this.context)fail('Main context invalidated');
        if(!message.id)return;
        const item=this.pending.get(message.id);if(!item)return;
        this.pending.delete(message.id);
        if(message.error||message.result?.exceptionDetails){
          const detail=message.error||message.result.exceptionDetails,exception=detail.exception;
          item.reject(Error(JSON.stringify({className:exception?.className,
            code:detail.code||exception?.code||exception?.preview?.properties?.find(property=>property.name==='code')?.value,
            description:String(exception?.description||detail.message||detail.text).slice(0,1500),
            stackTrace:detail.stackTrace}).slice(0,4000)));
        }
        else item.resolve(message.result);
      }catch(error){fail(error.message);this.socket.close();}
    });
    this.socket.addEventListener('close',()=>fail('Main inspector closed'));
    this.socket.addEventListener('error',()=>fail('Main inspector socket error'));
    await bounded(new Promise((resolve,reject)=>{
      this.socket.addEventListener('open',resolve,{once:true});
      this.socket.addEventListener('error',()=>reject(Error('Main inspector connection failed')),{once:true});
      this.socket.addEventListener('close',()=>reject(Error('Main inspector closed before connection')),{once:true});
    }),10000,'Main inspector connection');
    await this.command('Runtime.enable',{});
    assert.notEqual(this.context,null,'Default main context missing');
  }
  async command(method,params,timeout=10000){
    assert.ok(!this.closed&&this.socket.readyState===WebSocket.OPEN,'Main inspector unavailable');
    const id=++this.nextId;
    const reply=new Promise((resolve,reject)=>this.pending.set(id,{resolve,reject}));
    try{this.socket.send(JSON.stringify({id,method,params}));return await bounded(reply,timeout,method);}
    finally{this.pending.delete(id);}
  }
  async waitForElectronMain(timeout=45000){
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      // The inspector is published during node_init, before Electron registers
      // its require binding. App main-module creation happens after that setup.
      // Probe owning bootstrap state without importing or catching module errors.
      const result=await this.command('Runtime.evaluate',{
        expression:`({type:process.type,filename:process.mainModule?.filename,
          ready:process.type==='browser'&&!!process.mainModule&&typeof process.mainModule.require==='function'})`,
        contextId:this.context,returnByValue:true,
      },Math.min(10000,Math.max(1,deadline-Date.now())));
      if(result.result?.value?.ready===true)return result.result.value;
      await new Promise(resolve=>setTimeout(resolve,Math.min(50,Math.max(1,deadline-Date.now()))));
    }
    throw Error('Electron application main module did not become ready before deadline');
  }
  async evaluate(fn,arg,timeout=10000){
    const result=await this.command('Runtime.evaluate',{
      expression:`(${fn.toString()})(require('electron'),${arg===undefined?'undefined':JSON.stringify(arg)})`,
      contextId:this.context,includeCommandLineAPI:true,awaitPromise:true,returnByValue:true,
    },timeout);
    assert.ok(result.result&&!result.result.objectId,'Main result must be by value');
    return result.result.value;
  }
  close(){this.socket?.close();}
}
module.exports={MainInspector,bounded};
