'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {rendererOwner,waitForRenderer,rendererDiagnostics,nativeWindowCount}=require('./renderer-target.cjs');
const bundle='/owned/Disco.app',url='http://127.0.0.1:1234/';
function fixture({legacy=false}={}){
 const pages=[],contents=new Map();
 function page(id,{visible=true,projectName=null,at=url}={}){
  contents.set('target-'+id,{id});
  const value={url:()=>at,isClosed:()=>false,context:()=>({newCDPSession:async()=>({send:async()=>({targetInfo:{targetId:'target-'+id}}),detach:async()=>{}})}),
   evaluate:async(fn,name)=>fn.toString().includes('document.body')?{title:String(id),visibility:visible?'visible':'hidden',text:'owned fixture'}:visible&&(!name||name===projectName)};
  pages.push(value);return value;
 }
 const shell=page(1,{at:legacy?url:'file://'+bundle+'/Contents/Resources/app.asar/recovery.html'}),hidden=page(2),active=page(3,{projectName:'Current'}),foreign=page(4);
 const child={webContents:{id:3,getURL:()=>url,isDestroyed:()=>false},getBounds:()=>({x:0,y:0,width:100,height:80}),getVisible:()=>true};
 const window={id:9,isDestroyed:()=>false,isVisible:()=>true,webContents:{id:1,getURL:shell.url},contentView:{children:legacy?[]:[child]}};
 const windows=[window];let snapshots=0;
 const application={context:()=>({pages:()=>pages}),evaluate:async(fn,arg)=>{
  if(fn.toString().includes('window.contentView')){snapshots++;application.beforeSnapshot?.(snapshots);}
  return fn({BrowserWindow:{getAllWindows:()=>windows},webContents:{fromDevToolsTargetId:id=>contents.get(id)}},arg);
 }};
 return{application,window,child,windows,page,shell,hidden,active,foreign};
}
test('selects active attached identity despite shell first and hidden/foreign pages with same URL',async()=>{
 const f=fixture();assert.equal(await waitForRenderer(f.application,{diagnostics:false}),f.active);
 assert.equal(await nativeWindowCount(f.application),1);
 const snapshot=await rendererDiagnostics(f.application);
 assert.equal(snapshot.pages.length,4);assert.equal(snapshot.windows[0].children[0].id,3);
});
test('legacy scientific BrowserWindow remains supported',async()=>{
 const f=fixture({legacy:true});assert.equal(await waitForRenderer(f.application,{diagnostics:false}),f.shell);
});
test('recovery shell is opt-in and cannot displace an attached scientific view',async()=>{
 const f=fixture();const snapshot=await rendererDiagnostics(f.application);
 assert.equal(rendererOwner(snapshot.windows,{mode:'shell',bundle}),null);
 f.window.contentView.children=[];
 const empty=(await rendererDiagnostics(f.application)).windows;
 assert.equal(rendererOwner(empty),null);
 assert.equal(await waitForRenderer(f.application,{mode:'shell',bundle,diagnostics:false}),f.shell);
 assert.equal(rendererOwner(empty,{mode:'shell',bundle:'/foreign/Disco.app'}),null);
});
test('hidden or zero-size attached views and stale project identity do not qualify',async()=>{
 for(const condition of ['hidden','zero','wrong-project']){
  const f=fixture();
  if(condition==='hidden')f.child.getVisible=()=>false;
  if(condition==='zero')f.child.getBounds=()=>({width:0,height:80});
  await assert.rejects(waitForRenderer(f.application,{projectName:condition==='wrong-project'?'Other':undefined,
   timeout:5,pollMs:1,diagnostics:false}),/did not become ready/);
 }
});
test('multiple visible windows or attached renderers fail instead of choosing first',async()=>{
 const f=fixture();f.windows.push({...f.window,id:10});
 await assert.rejects(waitForRenderer(f.application,{diagnostics:false}),/Ambiguous visible native windows/);
 f.windows.pop();f.window.contentView.children.push({...f.child,webContents:{...f.child.webContents,id:5}});
 await assert.rejects(waitForRenderer(f.application,{diagnostics:false}),/Ambiguous attached scientific renderers/);
});
test('attachment is rechecked after CDP binding so a switched-away page cannot qualify',async()=>{
 const f=fixture(),replacement=f.page(5,{projectName:'Next'});
 f.application.beforeSnapshot=count=>{if(count===2)f.child.webContents={...f.child.webContents,id:5};};
 assert.equal(await waitForRenderer(f.application,{diagnostics:false,pollMs:1}),replacement);
});

test('fresh recovery context binds the owned shell and tolerates an unready shell URL',async()=>{
 const f=fixture();f.window.contentView.children=[];
 f.window.webContents.getURL=()=>'';
 assert.equal(rendererOwner((await rendererDiagnostics(f.application)).windows,{mode:'shell',bundle}),null);
 f.window.webContents.getURL=f.shell.url;
 const fresh=f.page(1,{at:f.shell.url()});
 assert.equal(await waitForRenderer(f.application,{mode:'shell',bundle,pagesContext:{pages:()=>[f.foreign,fresh]},diagnostics:false}),fresh);
});

test('renderer errors follow launcher, replacement project and recovery pages exactly once',()=>{
 const {EventEmitter}=require('node:events');
 const {createRendererWatcher}=require('./renderer-target.cjs');
 const failures=[],watch=createRendererWatcher(error=>failures.push(error));
 const launcher=new EventEmitter(),project=new EventEmitter(),recovery=new EventEmitter();
 assert.equal(watch(launcher),launcher);watch(project);watch(project);watch(recovery,'recovered-renderer-pageerror');
 project.emit('pageerror',Error('project failed'));recovery.emit('pageerror',Error('recovery failed'));
 assert.equal(project.listenerCount('pageerror'),1);
 assert.deepEqual(failures,[{name:'renderer-pageerror',message:'project failed'},{name:'recovered-renderer-pageerror',message:'recovery failed'}]);
});
test('discovery deadlines bound a nonresponsive main snapshot or project DOM',async()=>{
 for(const operation of ['snapshot','dom']){
  const f=fixture(),never=new Promise(()=>{});
  if(operation==='snapshot')f.application.evaluate=()=>never;
  else f.active.evaluate=()=>never;
  const began=Date.now();
  await assert.rejects(waitForRenderer(f.application,{timeout:20,pollMs:1,diagnostics:false}),/timed out|did not become ready/);
  assert.ok(Date.now()-began<500,'A stalled CDP operation must respect the bounded discovery deadline');
 }
});
