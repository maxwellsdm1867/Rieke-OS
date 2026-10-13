'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {pathToFileURL}=require('node:url');
const {mkdtemp,rm}=require('node:fs/promises');
const os=require('node:os');
const ids=[1,2].map(n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`);
async function fixture(t,{retainedViews=true}={}){
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
  async loadURL(url){await this.webContents.loadURL(url);}
 }
 class View{constructor(){this.webContents=new Contents();}setBounds(value){this.bounds=value;}}
 const records=ids.map((id,i)=>({bound:true,project_uuid:id,project_path:`/owned/project-${i}`,port:42002+i,pid:200+i,created_at:i+1,session_id:'session'}));
 const origin='http://127.0.0.1:42001';const supervisor={origin,origins:new Set([origin]),ready:true,sessionId:'session',registry:{services:records},expectedHealth:()=>({session_id:'session'}),async drain(){return {ready:true};},async api(){return {ready:true,session_id:'session',services:this.registry.services};},async authorizeProjectURL(url){const selected=new URL(url).origin;if(selected!==origin&&!this.registry.services.some(item=>selected===`http://127.0.0.1:${item.port}`))return false;this.origins.add(selected);return true;}};
 const actualRequire=require('node:module').createRequire(path.join(__dirname,'../main.cjs'));
 const electron={app,BrowserWindow:Window,WebContentsView:retainedViews?View:undefined,ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},dialog:{},session:{},shell:{},Menu:{},powerMonitor:{}};
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

const retainedIdentity=index=>({projectUuid:ids[index],path:`/owned/project-${index}`});
const deferred=()=>{let resolve;return {promise:new Promise(done=>{resolve=done;}),get resolve(){return resolve;}};};
async function retainedPair(t){
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;
 await h.activateProject(h.window,'http://127.0.0.1:42003');return {...h,views,first,second:views.active};
}
test('warm project IPC activates exact retained document using only its freshly authorized owned URL',async t=>{
 const h=await retainedPair(t),calls=[],authorize=h.supervisor.authorizeProjectURL.bind(h.supervisor),created=h.contents.length;
 h.supervisor.authorizeProjectURL=async url=>{calls.push(url);return authorize(url);};
 const result=await h.call(h.second,'desktop:activate-retained-project',retainedIdentity(0));
 assert.equal(result.activated,true);assert.equal(h.views.active,h.first);assert.deepEqual(calls,['http://127.0.0.1:42002']);assert.equal(h.contents.length,created);assert.equal(h.first.webContents.loads.length,1);
});
test('warm project IPC returns a genuine absent-owner miss but rejects malformed or hidden callers',async t=>{
 const h=await fixture(t);await h.activateProject(h.window,'http://127.0.0.1:42002');const views=h.projectViews.get(h.window),first=views.active;let authorized=0;
 h.supervisor.authorizeProjectURL=async()=>{authorized++;return true;};
 assert.equal((await h.call(first,'desktop:activate-retained-project',retainedIdentity(1))).activated,false);assert.equal(authorized,0);
 for(const bad of [null,{...retainedIdentity(1),url:'http://127.0.0.1:1'},{projectUuid:'invalid',path:'/owned/project-1'},{projectUuid:ids[1],path:'/owned/../project-1'}])await assert.rejects(h.call(first,'desktop:activate-retained-project',bad),/Invalid project identity/);
 await h.activateProject(h.window,'http://127.0.0.1:42003');await assert.rejects(h.call(first,'desktop:activate-retained-project',retainedIdentity(1)),/no longer active/);
});
test('fresh authorization cannot substitute another UUID or process incarnation that reused the retained port',async t=>{
 for(const change of [record=>{record.project_uuid='00000000-0000-0000-0000-000000000099';},record=>{record.created_at++;}]){
  const h=await retainedPair(t),wait=deferred(),created=h.contents.length;
  h.supervisor.authorizeProjectURL=async()=>{await wait.promise;change(h.records[0]);return true;};
  const pending=h.call(h.second,'desktop:activate-retained-project',retainedIdentity(0)),rejected=assert.rejects(pending,/backend binding changed/);
  await new Promise(resolve=>setImmediate(resolve));wait.resolve();await rejected;assert.equal(h.views.active,h.second);assert.equal(h.contents.length,created);
 }
});
test('clean eviction during main authorization returns false while a retired caller still rejects',async t=>{
 const h=await retainedPair(t),wait=deferred();h.supervisor.authorizeProjectURL=async()=>{await wait.promise;return true;};
 const pending=h.call(h.second,'desktop:activate-retained-project',retainedIdentity(0));await new Promise(resolve=>setImmediate(resolve));h.views.limit=1;await h.views.trim();wait.resolve();
 assert.equal((await pending).activated,false);assert.equal(h.views.active,h.second);assert.equal(h.first.isDestroyed(),true);
 const other=await retainedPair(t),gate=deferred();other.supervisor.authorizeProjectURL=async()=>{await gate.promise;return true;};
 const stale=other.call(other.second,'desktop:activate-retained-project',retainedIdentity(0)),rejected=assert.rejects(stale,/requesting project is no longer active/);
 await new Promise(resolve=>setImmediate(resolve));other.views.dispose(other.second);gate.resolve();await rejected;assert.equal(other.views.active,null);
});
test('queued warm request cannot steal focus after an intervening activation',async t=>{
 const h=await retainedPair(t),wait=deferred(),activated=h.views.onActivate;
 h.views.onActivate=async owner=>{await activated(owner);if(owner===h.first)await wait.promise;};
 const held=h.views.activate(h.first.binding,h.first.binding.origin);await new Promise(resolve=>setImmediate(resolve));assert.equal(h.views.active,h.first);
 const replacement=h.views.activate(h.second.binding,h.second.binding.origin);
 const pending=h.call(h.first,'desktop:activate-retained-project',retainedIdentity(0)),rejected=assert.rejects(pending,/requesting project is no longer active/);
 wait.resolve();await held;await replacement;await rejected;assert.equal(h.views.active,h.second);
});
test('recovery during warm authorization prevents attachment and does not report a cold miss',async t=>{
 const h=await retainedPair(t),wait=deferred();h.supervisor.authorizeProjectURL=async()=>{await wait.promise;return true;};
 const pending=h.call(h.second,'desktop:activate-retained-project',retainedIdentity(0)),rejected=assert.rejects(pending,/cancelled/);
 await new Promise(resolve=>setImmediate(resolve));h.recovery('held warm request');wait.resolve();await rejected;assert.equal(h.views.active,null);
});
test('warm IPC refuses closing and crashed targets instead of falling back to cold open',async t=>{
 for(const status of ['closing','draftUnavailable']){
  const h=await retainedPair(t);h.first[status]=true;let checks=0;h.supervisor.authorizeProjectURL=async()=>{checks++;return true;};
  await assert.rejects(h.call(h.second,'desktop:activate-retained-project',retainedIdentity(0)),status==='closing'?/closing/:/renderer stopped/);
  assert.equal(h.views.active,h.second);assert.equal(checks,0);
 }
});
test('explicit Quit during held warm authorization prevents a late project attachment',async t=>{
 const h=await retainedPair(t),wait=deferred();h.supervisor.authorizeProjectURL=async()=>{await wait.promise;return true;};h.supervisor.quit=async()=>({ready:true});
 const pending=h.call(h.second,'desktop:activate-retained-project',retainedIdentity(0)),rejected=assert.rejects(pending,/cancelled/);
 await new Promise(resolve=>setImmediate(resolve));await h.call(h.second,'desktop:quit');wait.resolve();await rejected;assert.notEqual(h.views.active,h.first);
});
test('legacy scientific host without WebContentsView returns a validated cold-path miss',async t=>{
 const h=await fixture(t,{retainedViews:false});await h.activateProject(h.window,'http://127.0.0.1:42002');h.scientificWindows.add(h.window);let calls=0;
 h.supervisor.authorizeProjectURL=async()=>{calls++;return true;};const result=await h.call(h.window,'desktop:activate-retained-project',retainedIdentity(1));
 assert.equal(result.activated,false);assert.equal(calls,0);assert.equal(h.projectViews.size,0);assert.equal(h.window.webContents.loads.length,1);
 await assert.rejects(h.call(h.window,'desktop:activate-retained-project',{projectUuid:ids[1],path:'relative'}),/Invalid project identity/);
 h.window.draftUnavailable=true;await assert.rejects(h.call(h.window,'desktop:activate-retained-project',retainedIdentity(1)),/no longer active/);
 h.window.draftUnavailable=false;h.recovery('legacy recovery');await assert.rejects(h.call(h.window,'desktop:activate-retained-project',retainedIdentity(1)),/paused/);
});
