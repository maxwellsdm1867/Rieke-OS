'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {pathToFileURL}=require('node:url');
const {mkdtemp,rm}=require('node:fs/promises');
const os=require('node:os');
const ids=[1,2].map(n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`);
async function fixture(t){
 const directory=await mkdtemp(path.join(os.tmpdir(),'disco-retained-test-'));t.after(()=>rm(directory,{recursive:true,force:true}));
 const handlers=new Map(),remembered=[],native=[],contents=[];let nextId=0;
 const app=new EventEmitter();Object.assign(app,{enableSandbox(){},setName(){},setPath(){},getPath:()=>directory,getVersion:()=> '0.1.12',isPackaged:false,requestSingleInstanceLock:()=>true,whenReady:()=>new Promise(()=>{}),quit(){}});
 class Contents extends EventEmitter{
  constructor(){super();this.id=++nextId;this.mainFrame={url:'about:blank'};this.messages=[];this.loads=[];this.destroyed=false;this.focused=false;contents.push(this);}
  isDestroyed(){return this.destroyed;}getURL(){return this.mainFrame.url;}getTitle(){return 'Disco test';}setWindowOpenHandler(){}
  async loadURL(url){this.loads.push(url);this.mainFrame.url=url;}
  send(channel,value){this.messages.push({channel,value});if(channel==='desktop:prepare-close')queueMicrotask(()=>handlers.get('desktop:drafts-ack')({sender:this,senderFrame:this.mainFrame},{requestId:value.requestId,ok:true}));}
  focus(){for(const other of contents)other.focused=false;this.focused=true;}isFocused(){return this.focused;}
  close(){this.destroyed=true;}undo(){this.undone=true;}
 }
 class Window extends EventEmitter{
  constructor(){super();this.webContents=new Contents();this.children=new Set();this.contentView={addChildView:v=>this.children.add(v),removeChildView:v=>this.children.delete(v)};native.push(this);}
  isDestroyed(){return false;}setTitle(value){this.title=value;}getContentSize(){return [1200,800];}show(){}
  async loadFile(file){this.webContents.mainFrame.url=pathToFileURL(file).href;}
 }
 class View{constructor(){this.webContents=new Contents();}setBounds(value){this.bounds=value;}}
 const records=ids.map((id,i)=>({bound:true,project_uuid:id,project_path:`/owned/project-${i}`,port:42002+i,pid:200+i,created_at:i+1,session_id:'session'}));
 const origin='http://127.0.0.1:42001';const supervisor={origin,origins:new Set([origin]),ready:true,sessionId:'session',registry:{services:records},expectedHealth:()=>({session_id:'session'}),async drain(){return {ready:true};},async api(){return {ready:true,session_id:'session',services:this.registry.services};},async authorizeProjectURL(url){const selected=new URL(url).origin;if(selected!==origin&&!this.registry.services.some(item=>selected===`http://127.0.0.1:${item.port}`))return false;this.origins.add(selected);return true;}};
 const actualRequire=require('node:module').createRequire(path.join(__dirname,'../main.cjs'));
 const electron={app,BrowserWindow:Window,WebContentsView:View,ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},dialog:{},session:{},shell:{},Menu:{},powerMonitor:{}};
 const context={require:name=>name==='electron'?electron:actualRequire(name),__dirname:path.join(__dirname,'..'),process,console,URL,AbortSignal,setTimeout,clearTimeout,queueMicrotask};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../main.cjs'),'utf8')+`\nglobalThis.h={createWindow,activateProject,projectViews,scientificWindows,rendererOwners,recovery,registerIPC,prepareQuit,set(value){supervisor=value;startupSession={remember:async(...args)=>globalThis.remembered.push(args)};draftStore=new DraftStore(globalThis.directory);}};`,Object.assign(context,{remembered,directory}));
 context.h.set(supervisor);context.h.registerIPC();const window=context.h.createWindow();
 const call=(owner,name,payload)=>handlers.get(name)({sender:owner.webContents,senderFrame:owner.webContents.mainFrame},payload);
 return {...context.h,window,supervisor,records,call,remembered,native,contents};
}
test('main retains project renderers, routes exact sender IPC and rejects cross-origin rebinding',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;
 await h.call(first,'desktop:activate-project','http://127.0.0.1:42003');const second=views.active;
 assert.equal(h.scientificWindows.size,2);assert.equal(first.active,false);assert.equal((await h.call(first,'desktop:project-visibility')).visible,false);
 await assert.rejects(h.call(first,'desktop:undo-text'),/not visible/);
 await h.call(second,'desktop:activate-project','http://127.0.0.1:42002');assert.equal(views.active,first);assert.equal(first.webContents.loads.length,1);
 first.webContents.mainFrame.url='http://127.0.0.1:42003';await assert.rejects(h.call(first,'desktop:status'),/Unauthorized/);
});
test('hidden autosave preserves last-active startup choice and remains project scoped',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const first=h.projectViews.get(h.window).active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');const chosen=h.remembered.length;
 const draft={projectId:ids[0],value:{format:'rieke-renderer-draft',version:1,projectId:ids[0],value:{route:{page:'protocol'}}}};
 await h.call(first,'desktop:save-draft',draft);assert.equal(h.remembered.length,chosen);
 await assert.rejects(h.call(first,'desktop:load-draft',ids[1]),/does not belong/);
});
test('hidden target closure requires draft preparation and authoritative absence',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');const second=views.active,identity={projectUuid:ids[0],path:'/owned/project-0'};
 await h.call(second,'desktop:prepare-project-close',identity);assert.equal(first.webContents.messages.at(-1).value.purpose,'project-checkpoint');
 await assert.rejects(h.call(second,'desktop:confirm-project-closed',identity),/not confirmed/);assert.equal(first.isDestroyed(),false);
 h.supervisor.registry.services=[h.records[1]];await h.call(second,'desktop:confirm-project-closed',identity);
 assert.equal(first.isDestroyed(),true);assert.equal(views.active,second);
});
test('recovery hides healthy documents, fences actions and preserves draft checkpointing',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const first=h.projectViews.get(h.window).active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');h.recovery('owned fixture');
 assert.equal(h.scientificWindows.size,2);assert.equal(first.isDestroyed(),false);assert.equal(h.projectViews.get(h.window).active,null);
 await assert.rejects(h.call(first,'desktop:activate-project','http://127.0.0.1:42002'),/paused/);
 const drafts=await h.prepareQuit();assert.equal(drafts.ready,true);assert.ok(first.webContents.messages.some(item=>item.channel==='desktop:prepare-close'));
});
test('changed backend process identity rejects retained renderer IPC',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const first=h.projectViews.get(h.window).active;
 h.records[0].created_at++;await assert.rejects(h.call(first,'desktop:save-draft',{}),/binding has changed/);
});
test('confirmed active-project closure reveals the launcher before disposing its document',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;
 const identity={projectUuid:ids[0],path:'/owned/project-0'};await h.call(first,'desktop:prepare-project-close',identity);
 // Root authoritative inventory can report absence without the cached registry
 // changing before sender validation, just as in the actual root health request.
 h.supervisor.api=async()=>({ready:true,session_id:'session',services:[]});
 await h.call(first,'desktop:confirm-project-closed',identity);
 assert.equal(first.isDestroyed(),true);assert.equal(views.active.binding.project_uuid,'launcher');assert.equal(h.window.children.size,1);
});
test('strict replacement requests draft receipts from both visible and hidden documents',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const first=h.projectViews.get(h.window).active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');const second=h.projectViews.get(h.window).active;let drained=0;
 h.supervisor.drain=async()=>{drained++;return {ready:true};};const result=await h.prepareQuit();
 assert.equal(result.ready,true);assert.equal(drained,1);
 for(const owner of [first,second])assert.equal(owner.webContents.messages.filter(message=>message.channel==='desktop:prepare-close'&&message.value.purpose===undefined).length,1);
});

test('hidden renderer crash preserves healthy unsaved view and checkpoints it on strict quit',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');const second=views.active;second.webContents.unsaved='pending draft';
 first.webContents.emit('render-process-gone');
 assert.equal(views.active,second);assert.equal(second.isDestroyed(),false);assert.equal(second.webContents.unsaved,'pending draft');
 assert.equal(first.draftUnavailable,true);await assert.rejects(h.activateProject(h.window,'http://127.0.0.1:42002'),/renderer stopped/);
 assert.equal((await h.prepareQuit()).ready,false);assert.ok(second.webContents.messages.some(item=>item.channel==='desktop:prepare-close'));
});
test('active renderer crash reveals launcher without destroying another healthy project',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');const second=views.active;
 second.webContents.emit('render-process-gone');await new Promise(resolve=>setImmediate(resolve));
 assert.equal(views.active.binding.project_uuid,'launcher');assert.equal(first.isDestroyed(),false);assert.equal(second.draftUnavailable,true);
 await h.activateProject(h.window,'http://127.0.0.1:42002');assert.equal(views.active,first);
});

test('recovery host can reach verified restoration while hidden project senders cannot',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const first=h.projectViews.get(h.window).active;
 h.recovery('Recovery fixture');h.supervisor.loadManifest=async()=>{throw Error('Reached verified recovery boundary');};
 await assert.rejects(h.call(h.window,'desktop:restore-previous'),/Reached verified recovery boundary/);
 await assert.rejects(h.call(first,'desktop:restore-previous'),/paused/);
});
