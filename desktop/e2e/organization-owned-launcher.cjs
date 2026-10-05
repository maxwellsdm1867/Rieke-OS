'use strict';
// Owned spawn + public CDP transport. No lifecycle signal or Playwright launcher.
// Inert on import; source-only until the acceptance preflight HOLD is removed.
const assert=require('node:assert/strict');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createHash}=require('node:crypto');
const MAX_MESSAGE=16*1024*1024;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const digest=value=>createHash('sha256').update(value).digest('hex');
function safeMessage(error) {
  // Never propagate transport URLs/reasons or arbitrary debugger expressions.
  const value=String(error?.message||error||'Owned launcher failure');
  if(/(?:wss?:|Debugger|DevTools|inspector|websocket)/i.test(value))return 'Owned debugger operation failed; endpoint details withheld';
  return value.slice(0,1000).replace(/\bhttps?:\/\/\S+/gi,'[URL withheld]');
}
function bounded(promise,timeout,label) {
  assert.ok(Number.isFinite(timeout)&&timeout>0);
  let timer;
  return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(label)),timeout);})]).finally(()=>clearTimeout(timer));
}
function parseEndpoint(text,kind) {
  const endpoint=new URL(text);
  assert.equal(endpoint.protocol,'ws:','Unexpected debug endpoint scheme');
  assert.ok(['127.0.0.1','[::1]'].includes(endpoint.hostname),'Debug listener must use loopback');
  assert.ok(endpoint.port&&Number(endpoint.port)>0&&!endpoint.username&&!endpoint.password&&!endpoint.search&&!endpoint.hash,'Malformed debug endpoint');
  assert.match(endpoint.pathname,kind==='node'?/^\/[a-f0-9-]+$/i:/^\/devtools\/browser\/[a-f0-9-]+$/i);
  return {url:endpoint.href,host:endpoint.hostname==='[::1]'?'::1':endpoint.hostname,port:Number(endpoint.port),sha256:digest(endpoint.href)};
}

// Closing this adapter closes only the controller's WebSocket. It never owns a
// child process and cannot signal one. Public ConnectOverCDPTransport interface.
class SocketTransport {
  constructor(endpoint,onFailure) {
    this.endpoint=endpoint;this.onFailure=onFailure;this.socket=null;this.closed=false;
    this.queue=[];this.queuedBytes=0;this._onmessage=null;this._onclose=null;this.closeNotified=false;
    this.protocolFailure=null;
  }
  set onmessage(handler) {
    this._onmessage=handler;
    if(handler) {const queued=this.queue;this.queue=[];this.queuedBytes=0;for(const item of queued)handler(item);}
  }
  get onmessage(){return this._onmessage;}
  set onclose(handler){this._onclose=handler;if(handler&&this.closed)this.notifyClose();}
  get onclose(){return this._onclose;}
  notifyClose(){if(this._onclose&&!this.closeNotified){this.closeNotified=true;this._onclose('Owned socket disconnected');}}
  fail(message) {this.protocolFailure=message;this.onFailure(message);this.close();}
  async connect(timeout) {
    this.socket=new WebSocket(this.endpoint.url);
    const ready=new Promise((resolve,reject)=>{
      this.socket.addEventListener('open',resolve,{once:true});
      this.socket.addEventListener('error',()=>reject(Error('Owned socket connection failed')),{once:true});
      this.socket.addEventListener('close',()=>reject(Error('Owned socket closed during connection')),{once:true});
    });
    this.socket.addEventListener('message',event=>{
      try {
        assert.equal(typeof event.data,'string','Unexpected binary protocol message');
        const bytes=Buffer.byteLength(event.data);assert.ok(bytes<=MAX_MESSAGE,'Protocol message bound exceeded');
        const value=JSON.parse(event.data);
        if(this._onmessage)this._onmessage(value);
        else {this.queuedBytes+=bytes;assert.ok(this.queue.length<128&&this.queuedBytes<=MAX_MESSAGE,'Protocol queue bound exceeded');this.queue.push(value);}
      }catch(_error){this.fail('Owned protocol message rejected');}
    });
    this.socket.addEventListener('close',()=>{this.closed=true;this.notifyClose();});
    this.socket.addEventListener('error',()=>this.fail('Owned socket transport failed'));
    try {await bounded(ready,timeout,'Owned socket connection deadline');}
    catch(_error){this.close();throw Error('Owned socket connection failed or timed out');}
  }
  send(message) {
    assert.ok(this.socket?.readyState===WebSocket.OPEN&&!this.closed,'Owned socket unavailable');
    const forbidden=new Set(['Browser.close','Browser.crash','Target.closeTarget','Target.createTarget',
      'Target.disposeBrowserContext','Page.crash','Runtime.terminateExecution']);
    if(forbidden.has(message.method)||message.method==='Security.setIgnoreCertificateErrors'&&message.params?.ignore===true) {
      this.fail('Prohibited lifecycle/security protocol method: '+message.method);
      throw Error('Prohibited lifecycle/security protocol method');
    }
    const data=JSON.stringify(message);assert.ok(Buffer.byteLength(data)<=MAX_MESSAGE,'Protocol outbound bound exceeded');
    this.socket.send(data);
  }
  close() {
    if(this.closed)return;
    this.closed=true;
    // Native WebSocket.close is a client socket handshake, never an app command.
    try {this.socket?.close(1000,'Controller disconnect');}catch(_error){/* retain blocked close evidence */}
    this.notifyClose();
  }
  async settleClose(timeout=1000) {
    this.close();
    if(!this.socket||this.socket.readyState===WebSocket.CLOSED)return true;
    try {await bounded(new Promise(resolve=>this.socket.addEventListener('close',resolve,{once:true})),timeout,'Socket close deadline');return true;}
    catch(_error){return false;}
  }
}

class MainInspector {
  constructor(transport,onFailure) {
    this.transport=transport;this.onFailure=onFailure;this.nextId=0;this.pending=new Map();
    this.context=null;this.contextInvalid=false;this.closed=false;
    transport.onmessage=message=>this.receive(message);
    transport.onclose=()=>{this.closed=true;this.rejectPending('Main context disconnected');};
  }
  rejectPending(message) {for(const item of this.pending.values())item.reject(Error(message));this.pending.clear();}
  receive(message) {
    if(message.method==='Runtime.executionContextCreated'&&message.params?.context?.auxData?.isDefault) {
      const id=message.params.context.id;
      if(this.context!==null&&this.context!==id){this.contextInvalid=true;this.rejectPending('Main context replaced');this.onFailure('Main context replaced');}
      else if(!this.contextInvalid)this.context=id;
    }
    if(message.method==='Runtime.executionContextsCleared'||message.method==='Runtime.executionContextDestroyed'&&message.params?.executionContextId===this.context) {
      this.contextInvalid=true;this.rejectPending('Main context invalidated');
    }
    if(!message.id)return;
    const item=this.pending.get(message.id);if(!item)return;this.pending.delete(message.id);
    if(message.error||message.result?.exceptionDetails)item.reject(Error('Main evaluation failed; details withheld'));
    else item.resolve(message.result);
  }
  async request(method,params,timeout) {
    assert.ok(!this.closed,'Main context disconnected');
    const id=++this.nextId;
    const response=new Promise((resolve,reject)=>this.pending.set(id,{resolve,reject}));
    try {this.transport.send({id,method,params});return await bounded(response,timeout,'Main operation deadline; no mutation retry');}
    finally {this.pending.delete(id);}
  }
  async initialize(timeout) {
    const end=Date.now()+timeout;await this.request('Runtime.enable',{},timeout);
    while(this.context===null&&!this.contextInvalid&&!this.closed&&Date.now()<end)await delay(25);
    assert.ok(this.context!==null&&!this.contextInvalid&&!this.closed,'Default main context unavailable');
  }
  async evaluate(fn,arg,timeout) {
    assert.equal(typeof fn,'function');assert.ok(this.context!==null&&!this.contextInvalid&&!this.closed,'Default main context unavailable');
    const payload=arg===undefined?'undefined':JSON.stringify(arg);
    const result=await this.request('Runtime.evaluate',{
      expression:`(${fn.toString()})(require('electron'),${payload})`,contextId:this.context,
      includeCommandLineAPI:true,awaitPromise:true,returnByValue:true,
    },timeout);
    assert.ok(result?.result&&!result.result.objectId,'Expected by-value main evaluation');
    if(result.result.type==='undefined')return undefined;
    assert.ok(Object.hasOwn(result.result,'value'),'Main result is not JSON-safe');return result.result.value;
  }
}

class OwnedApplication {
  constructor({bundle,userData,env,owner,budget}) {
    Object.assign(this,{bundle,userData,env,owner,budget});
    this.child=null;this.endpoints={};this.errors=[];this.lines=[];this.logBytes=0;this.streamBuffers={stdout:'',stderr:''};
    this.nodeTransport=null;this.rendererTransport=null;this.inspector=null;this.browser=null;this.attached=false;
    this.waitingForDebugger=false;this.quitDelivered=false;this.exit=null;
  }
  fail(message){if(this.errors.length<20)this.errors.push(safeMessage(message));}
  assertHealthy(){assert.deepEqual(this.errors,[],'Owned launcher observation incomplete');}
  readChunk(stream,chunk) {
    // Retain no raw chunks, partial lines, URLs or arbitrary exception details.
    const combined=this.streamBuffers[stream]+chunk.toString();
    if(Buffer.byteLength(combined)>65536){this.streamBuffers[stream]='';this.fail('Owned output line bound exceeded');return;}
    const pieces=combined.split('\n');this.streamBuffers[stream]=pieces.pop();
    for(const line of pieces) {
      try {
        if(stream==='stderr') {
          const match=line.trim().match(/^(Debugger|DevTools) listening on (.*)$/);
          if(match) {
            const kind=match[1]==='Debugger'?'node':'renderer';
            assert.ok(!this.endpoints[kind],'Duplicate debugger announcement');
            const endpoint=parseEndpoint(match[2],kind);
            assert.ok(!Object.values(this.endpoints).some(value=>value.port===endpoint.port),'Duplicate debug port');
            this.endpoints[kind]=endpoint;
          }
          if(line.includes('Waiting for the debugger to disconnect...')) {
            this.waitingForDebugger=true;this.nodeTransport?.close();
          }
        }
        // Do not persist arbitrary child output: retain only redacted line counts.
        this.logBytes+=Buffer.byteLength(line);assert.ok(this.logBytes<=4*1024*1024,'Owned output bound exceeded');
        if(this.lines.length<64)this.lines.push({stream,bytes:Buffer.byteLength(line),content:'[owned app output withheld]'});
      }catch(_error){this.fail('Owned output/endpoint validation failed');}
    }
  }
  async start() {
    assert.equal(this.child,null,'No relaunch within an owned adapter');
    this.child=spawn(path.join(this.bundle,'Contents/MacOS/Disco'),[
      '--inspect=127.0.0.1:0','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',`--user-data-dir=${this.userData}`],
      {shell:false,detached:true,env:this.env,stdio:['ignore','pipe','pipe']});
    this.child.on('error',()=>this.fail('Owned process failed to start'));
    this.child.once('exit',(code,signal)=>{this.exit={code,signal:signal||null};});
    for(const stream of ['stdout','stderr'])this.child[stream].on('data',chunk=>this.readChunk(stream,chunk));
    assert.ok(Number.isInteger(this.child.pid),'Owned process PID unavailable');
    await this.owner.start(this.child.pid);this.rootCreated=this.owner.rootCreated;
    const end=Date.now()+this.budget(45000);
    while(!this.endpoints.node||!this.endpoints.renderer) {
      this.assertHealthy();assert.ok(!this.exit,'Owned process exited before attach');
      assert.ok(Date.now()<end,'Both owned debug listeners unavailable; normal recovery required');await delay(25);
    }
    this.assertHealthy();
    await this.owner.verifyDebugListeners([this.endpoints.node,this.endpoints.renderer].map(({host,port})=>({host,port})));
    this.nodeTransport=new SocketTransport(this.endpoints.node,message=>this.fail(message));
    await this.nodeTransport.connect(this.budget(10000));
    this.inspector=new MainInspector(this.nodeTransport,message=>this.fail(message));
    await this.inspector.initialize(this.budget(10000));
    await this.owner.verifyDebugListeners([this.endpoints.node,this.endpoints.renderer].map(({host,port})=>({host,port})));
    this.rendererTransport=new SocketTransport(this.endpoints.renderer,message=>this.fail(message));
    await this.rendererTransport.connect(this.budget(10000));
    const {chromium}=require('playwright');
    this.browser=await chromium.connectOverCDP(this.rendererTransport,{noDefaults:true,
      artifactsDir:path.join(this.userData,'acceptance-artifacts'),timeout:this.budget(20000)});
    this.assertHealthy();this.attached=true;
  }
  process(){return this.child;}
  evaluate(fn,arg,options={}) {
    assert.ok(this.inspector,'Main quit/evaluation channel unavailable; normal recovery required');
    return this.inspector.evaluate(fn,arg,options.timeout??this.budget(20000));
  }
  async firstWindow({timeout}) {
    const end=Date.now()+timeout;
    while(Date.now()<end) {
      this.assertHealthy();
      const windows=await this.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().filter(w=>!w.isDestroyed()).map(w=>({
        rendererProcessId:w.webContents.getProcessId(),url:w.webContents.getURL(),id:w.id}))); // supplementary process identity only
      const expected=windows.filter(w=>/^http:\/\/127\.0\.0\.1:\d+(?:\/|$)/.test(w.url));
      if(expected.length===1) {
        const pages=this.browser.contexts().flatMap(context=>context.pages()).filter(page=>page.url()===expected[0].url);
        if(pages.length===1) {
          const session=await pages[0].context().newCDPSession(pages[0]);
          try {
            const {targetInfo}=await session.send('Target.getTargetInfo');
            const mapping=await this.evaluate(({webContents,BrowserWindow},id)=>{
              const contents=webContents.fromDevToolsTargetId(id);const window=contents&&BrowserWindow.fromWebContents(contents);
              return window?{windowId:window.id,url:contents.getURL()}:null;
            },targetInfo.targetId);
            assert.equal(mapping?.windowId,expected[0].id);assert.equal(mapping.url,expected[0].url);
          }finally{await session.detach();}
          return pages[0];
        }
      }
      await delay(50);
    }
    throw Error('Exact owned renderer unavailable; normal recovery required');
  }
  markQuitDelivered() {this.quitDelivered=true;this.nodeTransport?.close();}
  async disconnect() {
    const closed=await Promise.all([this.nodeTransport,this.rendererTransport].filter(Boolean).map(transport=>transport.settleClose()));
    return {instrumentation_sockets_closed:closed.every(Boolean),application_exit_not_implied:true};
  }
  evidence() {return {pid:this.child?.pid,anchored_created:this.rootCreated,
    endpoint_hashes:Object.fromEntries(Object.entries(this.endpoints).map(([kind,value])=>[kind,{sha256:value.sha256,host:value.host,port:value.port}])),
    errors:[...this.errors],output_lines:this.lines,output_bytes:this.logBytes,exit:this.exit,
    main_attached:!!this.inspector,renderer_attached:this.attached,waiting_for_debugger:this.waitingForDebugger};}
}
module.exports={OwnedApplication,safeMessage};
