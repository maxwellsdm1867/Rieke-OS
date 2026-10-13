'use strict';
// Test-only helpers: bind a Playwright page to the actual attached WCV identity,
// and leave failure evidence on disk before bounded, owned-process cleanup.
const fs=require('node:fs/promises'),syncFs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function bounded(operation,ms,label){let timer;try{return await Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(label+' timed out')),ms);})]);}finally{clearTimeout(timer);}}
function captureNativeProcess(application,output,receipt,label){
 const process=application.process(),record={label,pid:process.pid,stdout:'native-process.stdout.log',stderr:'native-process.stderr.log'};
 (receipt.native_processes??=[]).push(record);
 for(const name of ['stdout','stderr']){
  const target=path.join(output,record[name]);
  syncFs.appendFileSync(target,`\n--- ${label} pid=${process.pid} ---\n`);
  process[name]?.on('data',chunk=>syncFs.appendFileSync(target,chunk));
 }
 process.once('exit',(code,signal)=>{record.exit_code=code;record.exit_signal=signal;});
}
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
   if(item&&await page.evaluate(name=>[...document.querySelectorAll('button[aria-current="page"]')].some(el=>el.getAttribute('aria-label')===`${name}, current project`),project.name).catch(()=>false))return {page,...item};
  }
  await delay(100);
 }
 receipt.project_discovery={project,awaited_ms:45000,...await discoverySnapshot(application)};
 throw Error(`Attached project renderer did not become current: ${project.name}`);
}
function recordNativeRequests(page,receipt){
 const rows=new WeakMap();
 page.on('request',request=>{const url=new URL(request.url());if(!url.pathname.startsWith('/api/'))return;const row={at:performance.now(),phase:receipt.phase,page:page.url(),method:request.method(),url:request.url()};rows.set(request,row);receipt.requests.push(row);});
 page.on('response',response=>{const row=rows.get(response.request());if(row){row.response_at=performance.now();row.status=response.status();}});
 page.on('requestfinished',request=>{const row=rows.get(request);if(row){row.ended=performance.now();row.elapsed_ms=row.ended-row.at;}});
 page.on('requestfailed',request=>{const row=rows.get(request);if(row){row.ended=performance.now();row.elapsed_ms=row.ended-row.at;row.failure=request.failure()?.errorText;}});
}
async function measureRetainedSwitch({application,fromPage,project,view,receipt,sample,direction,expectFastpath=true,check}){
 const before=receipt.requests.length,began=performance.now();
 receipt.phase=`warm-${sample}-${direction}`;
 await fromPage.getByRole('button',{name:project.name,exact:true}).click({timeout:5000});
 let attached;const limit=45000,deadline=performance.now()+limit;
 while(performance.now()<deadline){
  attached=(await attachedViews(application)).find(item=>item.id===view.id&&item.bounds.width>0&&item.bounds.height>0);
  if(attached&&await view.page.evaluate(name=>document.visibilityState==='visible'&&[...document.querySelectorAll('button[aria-current="page"]')].some(el=>el.getAttribute('aria-label')===`${name}, current project`),project.name))break;
  attached=null;await delay(20);
 }
 assert.ok(attached,`Known retained WCV must become attached and visible within ${limit}ms`);
 await view.page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const visibleMs=performance.now()-began;
 const result={sample,direction,total_ms:visibleMs,web_contents_id:view.id,bounds:attached.bounds,requests:[],status:'observed'};
 (receipt.warm_switches??=[]).push(result);
 result.retention=await check(view.page);
 result.requests=receipt.requests.slice(before);
 const folder=result.requests.filter(row=>['/api/projects/inspect-folder','/api/projects/open-folder'].includes(new URL(row.url).pathname));
 const summaries=result.requests.filter(row=>/^\/api\/(?:overview|protocols\/[^/]+\/overview)$/.test(new URL(row.url).pathname));
 const traces=result.requests.filter(row=>/^\/api\/epochs\/[^/]+\/trace$/.test(new URL(row.url).pathname));
 result.folder_open_requests=folder.length;result.summary_requests=summaries.length;result.trace_requests=traces.length;
 assert.equal(summaries.length,0,'Warm project switch must not rebuild overview');
 assert.equal(traces.length,0,'Warm project switch must not reread raw traces');
 if(expectFastpath)assert.equal(folder.length,0,'Warm project switch must not inspect/reopen folder');
 result.status='passed';return result;
}
async function prepareInitialPresentation(page,receipt){
 const result={url:page.url(),closed_tag_author:false,opened_sidebar:false};
 const close=page.getByRole('button',{name:'Close tag author',exact:true});
 if(await close.isVisible()){await close.click();await close.waitFor({state:'hidden'});result.closed_tag_author=true;}
 const show=page.getByRole('button',{name:'Show sidebar',exact:true});
 if(await show.isVisible()){await show.click();await page.getByRole('button',{name:'Hide sidebar',exact:true}).waitFor();result.opened_sidebar=true;}
 const dialogs=await page.getByRole('dialog').all();
 for(const dialog of dialogs)if(await dialog.isVisible())throw Error('Unexpected modal still blocks native UI journey: '+await dialog.innerText());
 (receipt.presentation_setup??=[]).push(result);
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
module.exports={recordNativeRequests,measureRetainedSwitch,captureNativeProcess,currentProjectPage,prepareInitialPresentation,failureEvidence,closeOwned,discoverySnapshot};
