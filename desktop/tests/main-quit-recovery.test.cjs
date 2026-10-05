'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
function fixture(){
 let observeQuit;const quitCompleted=new Promise(resolve=>{observeQuit=resolve;});
 const app=new EventEmitter();let quits=0;Object.assign(app,{enableSandbox(){},setName(){},setPath(){},getPath:()=>'/private/tmp/mock-rieke-desktop',getVersion:()=> '0.1.3',isPackaged:false,requestSingleInstanceLock:()=>true,whenReady:()=>new Promise(()=>{}),quit(){quits++;observeQuit();}});
 class Window extends EventEmitter{constructor(){super();this.webContents=new EventEmitter();this.messages=[];Object.assign(this.webContents,{send:(channel,value)=>this.messages.push({channel,value}),setWindowOpenHandler(){}});}isDestroyed(){return false;}loadFile(){return Promise.resolve();}loadURL(){return Promise.resolve();}}
 const electron={app,BrowserWindow:Window,ipcMain:{handle(){}},dialog:{},session:{},shell:{},Menu:{},powerMonitor:{}};
 const actualRequire=require('node:module').createRequire(path.join(__dirname,'../main.cjs'));
 const required=name=>name==='electron'?electron:name==='./close/quit-coordinator.cjs'?{QuitCoordinator:class extends actualRequire(name).QuitCoordinator{constructor(options){super({...options,deadline:25,draftDeadline:5});}}}:actualRequire(name);
 const context={require:required,__dirname:path.join(__dirname,'..'),process,console,setTimeout,clearTimeout};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../main.cjs'),'utf8')+'\n globalThis.harness={recovery,orderlyQuit,prepareQuit,createWindow,scientificWindows,setSupervisor:value=>supervisor=value};',context);
 return{...context.harness,app,quitCompleted,get quits(){return quits;}};
}
test('recovery navigation removes the vanished scientific listener; Quit still exits with retained-view warning',async()=>{const h=fixture(),window=h.createWindow();h.scientificWindows.add(window);let calls=0;h.setSupervisor({quit:async()=>{calls++;return{ready:true};},drain:async()=>({ready:true})});h.recovery('Recovery reproduced');assert.equal(h.scientificWindows.size,0);const result=await h.orderlyQuit();assert.equal(h.quits,1);assert.equal(calls,1);assert.equal(result.drafts_saved,false);assert.match(result.warnings.join(' '),/last saved view/i);assert.equal(window.messages.filter(value=>value.channel==='desktop:prepare-close').length,0);});
// Observe the actual finite exit rather than racing a fixed sleep against the
// coordinator's sequential draft/cleanup timers under a loaded event loop.
test('native close and before-quit take the same finite path with a crashed or non-acknowledging renderer',{timeout:2000},async()=>{for(const trigger of ['close','before-quit']){const h=fixture(),window=h.createWindow();h.scientificWindows.add(window);h.setSupervisor({quit:()=>new Promise(()=>{})});let prevented=false;(trigger==='close'?window:h.app).emit(trigger,{preventDefault(){prevented=true;}});await h.quitCompleted;assert.equal(prevented,true);assert.equal(h.quits,1);}});
test('replacement remains strict but recovery never waits for the removed scientific page',async()=>{const h=fixture(),window=h.createWindow();h.scientificWindows.add(window);h.recovery('Replaced renderer');let drains=0;h.setSupervisor({drain:async()=>{drains++;return{ready:false,reason:'Native database exit not verified.'};}});const result=await h.prepareQuit();assert.equal(drains,1);assert.equal(result.ready,false);assert.match(result.reason,/not verified/);assert.equal(window.messages.filter(value=>value.channel==='desktop:prepare-close').length,0);});
