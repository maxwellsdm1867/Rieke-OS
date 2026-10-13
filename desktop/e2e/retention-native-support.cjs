'use strict';
// Test-only helpers: bind a Playwright page to the actual attached WCV identity,
// and leave failure evidence on disk before bounded, owned-process cleanup.
const fs=require('node:fs/promises'),path=require('node:path');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function bounded(operation,ms,label){let timer;try{return await Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(label+' timed out')),ms);})]);}finally{clearTimeout(timer);}}
async function attachedViews(application){return application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().flatMap(window=>window.contentView.children.map(view=>({view_class:view.constructor.name,id:view.webContents?.id??null,url:view.webContents?.getURL()??null,bounds:view.getBounds()}))));}
async function pageBinding(application,page){const session=await application.context().newCDPSession(page);try{const {targetInfo}=await session.send('Target.getTargetInfo');const id=await application.evaluate(({webContents},targetId)=>webContents.fromDevToolsTargetId(targetId)?.id??null,targetInfo.targetId);return {id,target_id:targetInfo.targetId};}finally{await session.detach();}}
async function discoverySnapshot(application){
 const attached=await bounded(attachedViews(application),3000,'attached view snapshot').catch(error=>({error:String(error)})),pages=[];
 for(const page of application.context().pages()){
  const row={url:page.url()};
  try{Object.assign(row,await bounded(pageBinding(application,page),3000,'page binding'));row.dom=await bounded(page.evaluate(()=>({title:document.title,visibility:document.visibilityState,text:document.body?.innerText.slice(0,6000),buttons:[...document.querySelectorAll('button')].map(el=>({label:el.getAttribute('aria-label')||el.textContent,current:el.getAttribute('aria-current'),visible:!!el.getClientRects().length})).slice(0,50)})),3000,'page DOM snapshot');}catch(error){row.error=String(error);}
  pages.push(row);
 }
 return {attached,pages};
}
async function currentProjectPage(application,project,receipt){
 const until=Date.now()+45000,bindings=new Map();
 while(Date.now()<until){
  const attached=await attachedViews(application);
  for(const page of application.context().pages()){
   let binding=bindings.get(page);if(!binding){binding=await bounded(pageBinding(application,page),3000,'project page binding').catch(()=>null);if(binding)bindings.set(page,binding);}
   const item=binding&&attached.find(item=>item.id===binding.id);
   if(item&&await page.getByRole('button',{name:`${project.name}, current project`,exact:true}).isVisible().catch(()=>false))return {page,...item};
  }
  await delay(100);
 }
 receipt.project_discovery={project,awaited_ms:45000,...await discoverySnapshot(application)};
 throw Error(`Attached project renderer did not become current: ${project.name}`);
}
async function failureEvidence(application,page,output,receipt,error){
 receipt.status='failed';receipt.error=String(error);
 await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
 if(application&&!receipt.project_discovery)receipt.failure_snapshot=await discoverySnapshot(application);
 if(page)await bounded(page.screenshot({path:path.join(output,'failure.png')}),5000,'failure screenshot').catch(error=>{receipt.failure_screenshot_error=String(error);});
 await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
}
async function closeOwned(application,userData,receipt){
 const process=application.process();
 const ended=()=>process.exitCode!==null||process.signalCode!==null;
 if(ended()){receipt.cleanup.fallback_already_exited=true;return;}
 const exit=new Promise(resolve=>process.once('exit',resolve));
 await bounded(application.evaluate(({app})=>{app.quit();}),5000,'fallback quit request').catch(error=>{receipt.cleanup.quit_request_error=String(error);});
 if(await Promise.race([exit.then(()=>true),delay(30000).then(()=>false)])){receipt.cleanup.fallback_orderly_exit=true;return;}
 const registryPath=path.join(userData,'backend/desktop-services.json');
 const registry=JSON.parse(await fs.readFile(registryPath));
 receipt.cleanup.registry_before_forced_exit=registry;
 if(!Array.isArray(registry.services)||registry.services.length||!Array.isArray(registry.database_operations)||registry.database_operations.length){receipt.cleanup.blocked='Owned backend still has services or database operations; no signal sent';throw Error(receipt.cleanup.blocked);}
 // This handle is the exact Electron child returned by _electron.launch; never
 // search by process name or signal a process group. Backend writers are absent.
 receipt.cleanup.forced_electron_pid=process.pid;
 process.kill('SIGTERM');
 if(!await Promise.race([exit.then(()=>true),delay(1500).then(()=>false)])){process.kill('SIGKILL');await bounded(exit,5000,'owned Electron exit');receipt.cleanup.forced_signal='SIGKILL';}else receipt.cleanup.forced_signal='SIGTERM';
}
module.exports={currentProjectPage,failureEvidence,closeOwned,discoverySnapshot};
