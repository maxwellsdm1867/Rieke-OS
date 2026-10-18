'use strict';
// A backend crash clears the supervisor's authenticated origins. Retained
// WebContentsView documents must still persist and acknowledge their drafts at
// the exact origin recorded when they registered, and Retry must retire them.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {pathToFileURL}=require('node:url');
const {mkdtemp,rm,readdir}=require('node:fs/promises');
const os=require('node:os');
const ids=[1,2].map(n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`);
async function fixture(t){
 const directory=await mkdtemp(path.join(os.tmpdir(),'disco-crash-drafts-test-'));t.after(()=>rm(directory,{recursive:true,force:true}));
 const handlers=new Map(),contents=[],failures=[];let nextId=0;
 const app=new EventEmitter();Object.assign(app,{enableSandbox(){},setName(){},setPath(){},getPath:()=>directory,getVersion:()=> '0.1.19',isPackaged:false,requestSingleInstanceLock:()=>true,whenReady:()=>new Promise(()=>{}),quit(){}});
 const call=(webContents,name,payload)=>handlers.get(name)({sender:webContents,senderFrame:webContents.mainFrame},payload);
 class Contents extends EventEmitter{
  constructor(){super();this.id=++nextId;this.mainFrame={url:'about:blank'};this.messages=[];this.loads=[];this.destroyed=false;contents.push(this);}
  isDestroyed(){return this.destroyed;}getURL(){return this.mainFrame.url;}getTitle(){return 'Disco test';}setWindowOpenHandler(){}
  async loadURL(url){this.loads.push(url);this.mainFrame.url=url;}
  // Behaves like the renderer lifecycle: persist the project view, then acknowledge.
  send(channel,value){
   this.messages.push({channel,value});
   if(channel!=='desktop:prepare-close')return;
   if(this.held){this.held.push(value);return;}
   queueMicrotask(async()=>{
    let ok=true;
    if(this.draft)try{await call(this,'desktop:save-draft',this.draft);}catch(error){ok=false;failures.push(['save',error.message]);}
    try{await call(this,'desktop:drafts-ack',{requestId:value.requestId,ok});}catch(error){failures.push(['ack',error.message]);}
   });
  }
  async respond(value,ok=true){await call(this,'desktop:drafts-ack',{requestId:value.requestId,ok});}
  focus(){}isFocused(){return false;}close(){this.destroyed=true;}
 }
 class Window extends EventEmitter{
  constructor(){super();this.webContents=new Contents();this.children=new Set();this.contentView={addChildView:v=>this.children.add(v),removeChildView:v=>this.children.delete(v)};}
  isDestroyed(){return false;}setTitle(){}getContentSize(){return [1200,800];}show(){}
  async loadFile(file){this.webContents.mainFrame.url=pathToFileURL(file).href;}
  async loadURL(url){await this.webContents.loadURL(url);}
 }
 class View{constructor(){this.webContents=new Contents();}setBounds(){}}
 const records=ids.map((id,i)=>({bound:true,project_uuid:id,project_path:`/owned/project-${i}`,port:42002+i,pid:200+i,created_at:i+1,session_id:'session'}));
 const origin='http://127.0.0.1:42001';
 const supervisor={origin,origins:new Set([origin]),ready:true,bound:true,exited:false,child:{pid:100},sessionId:'session',registry:{services:records},
  expectedHealth:()=>({session_id:'session'}),async drain(){return {ready:true};},async quit(){return {ready:true};},
  async api(){return {ready:true,session_id:'session',services:this.registry.services};},
  async authorizeProjectURL(url){const selected=new URL(url).origin;if(selected!==this.origin&&!this.registry.services.some(item=>selected===`http://127.0.0.1:${item.port}`))return false;this.origins.add(selected);return true;}};
 const actualRequire=require('node:module').createRequire(path.join(__dirname,'../main.cjs'));
 const electron={app,BrowserWindow:Window,WebContentsView:View,ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},dialog:{},session:{},shell:{},Menu:{},powerMonitor:{}};
 const context={require:name=>name==='electron'?electron:actualRequire(name),__dirname:path.join(__dirname,'..'),process,console,URL,AbortSignal,setTimeout,clearTimeout,queueMicrotask,directory};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../main.cjs'),'utf8')+`\nglobalThis.h={createWindow,activateProject,projectViews,scientificWindows,recovery,registerIPC,prepareQuit,startScientificUI,status:()=>lifecycleStatus,unconfirmed:()=>retiredDraftsUnconfirmed,
  set(value){supervisor=value;coordinator={start:async()=>{},stop(){},getStatus:()=>({state:'Current'})};startupSession={claim:()=>null,remember:async()=>{}};draftStore=new DraftStore(globalThis.directory);}};`,context);
 context.h.set(supervisor);context.h.registerIPC();const window=context.h.createWindow();
 await context.h.activateProject(window,'http://127.0.0.1:42002');const views=context.h.projectViews.get(window),first=views.active;
 await context.h.activateProject(window,'http://127.0.0.1:42003');const second=views.active;
 for(const [index,owner] of [first,second].entries())owner.webContents.draft={projectId:ids[index],value:{format:'rieke-renderer-draft',version:1,projectId:ids[index],value:{route:{page:'protocol'},edit:index}}};
 // The real supervisor exit handler: origins are cleared, then recovery runs.
 const crash=()=>{supervisor.origins.clear();supervisor.exited=true;supervisor.ready=false;context.h.recovery('The owned backend stopped unexpectedly.');};
 return {...context.h,window,views,first,second,supervisor,records,call,failures,crash,directory};
}
async function savedDrafts(directory){
 try{return (await readdir(path.join(directory,'scoped-views'),{recursive:true})).filter(name=>name.endsWith('.json')&&name.includes('drafts'));}
 catch(error){if(error.code==='ENOENT')return [];throw error;}
}

test('after a backend crash retained project views still save and acknowledge drafts at their registered origin',{timeout:4000},async t=>{
 const h=await fixture(t);h.crash();
 assert.equal(h.supervisor.origins.size,0);assert.equal(h.first.draftUnavailable,false);
 assert.deepEqual(await h.call(h.first.webContents,'desktop:save-draft',h.first.webContents.draft),{saved:true});
 const result=await h.prepareQuit();
 assert.deepEqual(h.failures,[]);assert.equal(result.ready,true);
 assert.equal((await savedDrafts(h.directory)).length,2);
});
test('a crash does not widen non-draft IPC or admit a document that left its registered origin',async t=>{
 const h=await fixture(t);h.crash();
 await assert.rejects(h.call(h.first.webContents,'desktop:status'),/Unauthorized/);
 await assert.rejects(h.call(h.first.webContents,'desktop:load-draft',ids[0]),/Unauthorized/);
 h.first.webContents.mainFrame.url='http://127.0.0.1:42003/';
 await assert.rejects(h.call(h.first.webContents,'desktop:save-draft',h.second.webContents.draft),/Unauthorized/);
});
test('successful Retry checkpoints retained views before replacement, then disposes owners whose backend is gone',{timeout:4000},async t=>{
 const h=await fixture(t);h.crash();let checkpointed=false;
 h.supervisor.start=async()=>{
  checkpointed=[h.first,h.second].every(owner=>owner.webContents.messages.some(item=>item.channel==='desktop:prepare-close'&&item.value.purpose==='project-checkpoint'));
  Object.assign(h.supervisor,{origin:'http://127.0.0.1:43001',exited:false,ready:true,child:{pid:300},sessionId:'session-2',registry:{services:[]}});
  h.supervisor.origins.add(h.supervisor.origin);return h.supervisor.origin;
 };
 await h.startScientificUI();
 assert.equal(h.status().state,'Running');assert.equal(checkpointed,true);assert.deepEqual(h.failures,[]);
 assert.equal((await savedDrafts(h.directory)).length,2);
 for(const owner of [h.first,h.second]){assert.equal(owner.isDestroyed(),true);assert.equal(h.scientificWindows.has(owner),false);}
 assert.equal(h.views.owners.size,1);assert.equal(h.views.active.binding.origin,'http://127.0.0.1:43001');
 // Quit no longer waits on stale owners whose acknowledgements cannot authenticate.
 const started=Date.now(),result=await h.prepareQuit();
 assert.equal(result.ready,true);assert.ok(Date.now()-started<1000);
});
test('a failed Retry keeps retained views and their draft path for a later Quit',{timeout:4000},async t=>{
 const h=await fixture(t);h.crash();h.supervisor.start=async()=>{throw Error('injected start failure');};
 await h.startScientificUI();
 assert.equal(h.status().state,'Recovery');assert.equal(h.first.isDestroyed(),false);
 assert.equal((await h.prepareQuit()).ready,true);assert.deepEqual(h.failures,[]);
});

const turns=async(count=5)=>{for(let index=0;index<count;index++)await new Promise(resolve=>setImmediate(resolve));};
async function readDraft(directory,projectId){
 const names=await savedDrafts(directory),name=names.find(item=>item.endsWith(`${projectId}.json`));
 return JSON.parse(fs.readFileSync(path.join(directory,'scoped-views',name),'utf8')).value;
}
// The one way a second document for a project can appear: a new backend binding
// for the same project while the previous document is still retained.
async function successor(h){
 h.records.push({...h.records[0],port:42012,pid:210,created_at:9});
 h.first.webContents.held=[];
 await h.activateProject(h.window,'http://127.0.0.1:42012');
 return h.views.active;
}
const view=(index,edit)=>({projectId:ids[index],value:{format:'rieke-renderer-draft',version:1,projectId:ids[index],value:{route:{page:'protocol'},edit}}});
test('one project has one draft writer: the successor writes only after the predecessor final checkpoint',{timeout:4000},async t=>{
 const h=await fixture(t),next=await successor(h);
 assert.notEqual(next,h.first);assert.equal(h.first.webContents.held.length,1);
 assert.equal(h.first.webContents.held[0].purpose,'project-checkpoint');
 let admitted=false;const nextSave=h.call(next.webContents,'desktop:save-draft',view(0,'successor')).then(value=>{admitted=true;return value;});
 await turns();assert.equal(admitted,false,'Successor waits for the predecessor checkpoint');
 assert.deepEqual(await h.call(h.first.webContents,'desktop:save-draft',view(0,'final checkpoint')),{saved:true});
 await h.first.webContents.respond(h.first.webContents.held[0]);
 assert.deepEqual(await nextSave,{saved:true});
 assert.equal((await readDraft(h.directory,ids[0])).edit,'successor');
 assert.equal(h.first.isDestroyed(),true);assert.equal(h.scientificWindows.has(h.first),false);
 await assert.rejects(h.call(h.first.webContents,'desktop:save-draft',view(0,'late stale write')),/Unauthorized/);
 assert.equal((await readDraft(h.directory,ids[0])).edit,'successor');
});
test('a superseded owner cannot write outside its final checkpoint, and an unanswered checkpoint is unconfirmed',{timeout:9000},async t=>{
 const h=await fixture(t),next=await successor(h);
 const stale=h.first,staleFrame=stale.webContents.mainFrame;
 // Simulate the gate after the checkpoint deadline without disposal racing the assertion.
 await h.call(next.webContents,'desktop:save-draft',view(0,'successor'));
 assert.equal(stale.isDestroyed(),true);
 const result=await h.prepareQuit();
 assert.equal(result.ready,true);assert.equal(h.unconfirmed(),true);
 stale.webContents.destroyed=false;h.scientificWindows.add(stale);stale.webContents.mainFrame=staleFrame;
 await assert.rejects(h.call(stale.webContents,'desktop:save-draft',view(0,'resurrected stale write')),/now owns this project/);
});
test('skip-unchanged stays correct: the single writer never sees a foreign write in between',{timeout:4000},async t=>{
 const h=await fixture(t),next=await successor(h);
 await h.first.webContents.respond(h.first.webContents.held[0]);
 await h.call(next.webContents,'desktop:save-draft',view(0,'same'));
 await assert.rejects(h.call(h.first.webContents,'desktop:save-draft',view(0,'foreign')),/Unauthorized/);
 assert.equal((await readDraft(h.directory,ids[0])).edit,'same');
});
