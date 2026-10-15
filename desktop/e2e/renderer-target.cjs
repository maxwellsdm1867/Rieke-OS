'use strict';
// Qualification-only: bind a CDP Page to the visible main-owned document.
// Attachment and WebContents identity, never page order or URL alone, select it.
const fs=require('node:fs/promises'),path=require('node:path');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function bounded(promise,timeout=2000){
 let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Renderer diagnostic operation timed out')),timeout);})]);}finally{clearTimeout(timer);}
}
async function rendererSnapshot(application){
 return application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().filter(window=>!window.isDestroyed()).map(window=>({
  id:window.id,visible:window.isVisible(),shell:{id:window.webContents.id,url:window.webContents.getURL()},
  children:(window.contentView?.children||[]).filter(view=>view.webContents&&!view.webContents.isDestroyed()).map(view=>({
   id:view.webContents.id,url:view.webContents.getURL(),bounds:view.getBounds(),visible:typeof view.getVisible==='function'?view.getVisible():true,
  })),
 })));
}
function rendererOwner(windows,{mode='application',bundle}={}){
 if(!['application','shell'].includes(mode))throw Error('Unknown qualification renderer mode');
 const visible=windows.filter(window=>window.visible);
 if(visible.length>1)throw Error('Ambiguous visible native windows');
 if(visible.length!==1)return null;
 const window=visible[0],attached=window.children.filter(view=>view.visible&&view.bounds.width>0&&view.bounds.height>0);
 if(attached.length>1)throw Error('Ambiguous attached scientific renderers');
 if(mode==='shell'){
  if(attached.length)return null;
  let url;try{url=new URL(window.shell.url);}catch{return null;}
  if(url.protocol!=='file:'||!bundle||!decodeURIComponent(url.pathname).startsWith(bundle+'/'))return null;
  return {...window.shell,window_id:window.id,kind:'shell'};
 }
 const owner=attached[0]||window.shell;
 if(!/^http:\/\/127\.0\.0\.1:\d+(?:\/|$)/.test(owner.url))return null;
 return {...owner,window_id:window.id,kind:attached.length?'attached-view':'legacy-window'};
}
async function rendererId(application,page){
 const session=await page.context().newCDPSession(page);
 try{
  const {targetInfo}=await session.send('Target.getTargetInfo');
  return await application.evaluate(({webContents},target)=>webContents.fromDevToolsTargetId(target)?.id??null,targetInfo.targetId);
 }finally{await session.detach();}
}
async function rendererDiagnostics(application){
 const result={windows:await bounded(rendererSnapshot(application)).catch(error=>({error:String(error)})),pages:[]};
 for(const page of application.context().pages()){
  const row={url:page.url()};
  try{row.id=await bounded(rendererId(application,page));row.dom=await bounded(page.evaluate(()=>({title:document.title,visibility:document.visibilityState,text:document.body?.innerText.slice(0,4000)})));}
  catch(error){row.error=String(error);}
  result.pages.push(row);
 }
 return result;
}
async function captureRendererFailure(application,label='renderer-discovery'){
 const directory=path.resolve(__dirname,'../build/native-qualification-diagnostics');
 await fs.mkdir(directory,{recursive:true});
 const filename=path.join(directory,`${label}-${Date.now()}.json`);
 await fs.writeFile(filename,JSON.stringify(await rendererDiagnostics(application),null,2)+'\n');
 return filename;
}
async function showProjectSidebar(page){
 const toggle=page.getByRole('button',{name:'Show sidebar',exact:true});
 if(await toggle.isVisible())await toggle.click();
}
function createRendererWatcher(onError){
 const watched=new WeakSet();
 return (page,name='renderer-pageerror')=>{
  if(!watched.has(page)){watched.add(page);page.on('pageerror',error=>onError({name,message:error.message}));}
  return page;
 };
}
async function waitForRenderer(application,{mode='application',bundle,projectName,excludeId,timeout=45000,pollMs=50,diagnostics=true,pagesContext}={}){
 const until=Date.now()+timeout;
 const within=promise=>bounded(promise,Math.max(1,until-Date.now()));
 try{
  do{
   const owner=rendererOwner(await within(rendererSnapshot(application)),{mode,bundle});
   if(owner&&owner.id!==excludeId){
    const matches=[];
    for(const page of (pagesContext||application.context()).pages()){
     if(Date.now()>=until)break;
     if(page.isClosed())continue;
     const id=await within(rendererId(application,page)).catch(()=>null);
     if(id!==owner.id)continue;
     const visible=await within(page.evaluate(name=>document.visibilityState==='visible'&&(!name||
      [...document.querySelectorAll('button[aria-current="page"]')].some(button=>button.getAttribute('aria-label')===`${name}, current project`)),projectName)).catch(()=>false);
     if(visible)matches.push(page);
    }
    if(matches.length>1)throw Error('Multiple pages bind the same visible renderer');
    if(matches.length===1){
     // Recheck attachment after CDP/DOM awaits: a project may have switched.
     const current=rendererOwner(await within(rendererSnapshot(application)),{mode,bundle});
     if(current?.id===owner.id)return matches[0];
    }
   }
   await delay(Math.min(pollMs,Math.max(0,until-Date.now())));
  }while(Date.now()<until);
  throw Error(`Visible main-owned ${mode} renderer did not become ready`);
 }catch(error){
  if(diagnostics){try{error.rendererDiagnostics=await captureRendererFailure(application);}catch(failure){error.rendererDiagnosticFailure=String(failure);}}
  throw error;
 }
}
async function nativeWindowCount(application){return application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().filter(window=>!window.isDestroyed()).length);}
module.exports={showProjectSidebar,createRendererWatcher,rendererSnapshot,rendererOwner,rendererId,rendererDiagnostics,captureRendererFailure,waitForRenderer,nativeWindowCount};
