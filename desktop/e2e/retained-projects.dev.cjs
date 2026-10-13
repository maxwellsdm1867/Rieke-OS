'use strict';
// Actual development main.cjs + WebContentsView integration. A separately staged,
// manifest-refreshed runtime is mandatory; never use the installed application.
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {createRequire}=require('node:module'),{execFile}=require('node:child_process');
const {promisify}=require('node:util'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const run=promisify(execFile);
const {recordNativeRequests,measureRetainedSwitch,captureNativeProcess,currentProjectPage,prepareInitialPresentation,failureEvidence,closeOwned}=require('./retention-native-support.cjs');
const config={};for(let i=2;i<process.argv.length;i+=2){if(!process.argv[i].startsWith('--')||!process.argv[i+1])throw Error('Expected --key value');config[process.argv[i].slice(2)]=process.argv[i+1];}
for(const name of ['desktop-root','dependency-root','source-root','commit','output'])if(!config[name])throw Error(`Missing --${name}`);
if(config['expect-warm-fastpath']!==undefined&&!['true','false'].includes(config['expect-warm-fastpath']))throw Error('Expected --expect-warm-fastpath true|false');
const expectFastpath=config['expect-warm-fastpath']!=='false';

(async()=>{
 const desktop=await fs.realpath(config['desktop-root']),dependencies=createRequire(path.join(await fs.realpath(config['dependency-root']),'package.json'));
 const {_electron}=dependencies('playwright'),executablePath=dependencies('electron');
 const runtime=path.join(desktop,'build/runtime'),manifest=JSON.parse(await fs.readFile(path.join(runtime,'runtime-manifest.json')));
 assert.equal(manifest.source_commit,config.commit);assert.equal(manifest.source_dirty,false,'Native candidate must have an exact clean manifest');
 const source=await fs.realpath(config['source-root']);
 assert.equal((await run('git',['-C',source,'rev-parse','HEAD'])).stdout.trim(),config.commit);
 assert.equal((await run('git',['-C',source,'status','--porcelain'])).stdout.trim(),'','Native source must be clean');
 const desktopHashes={};
 for(const name of ['main.cjs','preload.cjs','security.cjs','project-views.cjs','close/draft-barrier.cjs','drafts/draft-store.cjs','startup/startup-session.cjs']){
   const original=await fs.readFile(path.join(source,'desktop',name)),staged=await fs.readFile(path.join(desktop,name));
   assert.deepEqual(staged,original,`Staged desktop source differs: ${name}`);
   desktopHashes[name]=createHash('sha256').update(staged).digest('hex');
 }
 const output=path.resolve(config.output);await fs.mkdir(output,{recursive:false});
 const fixture=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'disco-retention-native-'))),home=path.join(fixture,'home'),userData=path.join(home,'state');
 await fs.mkdir(userData,{recursive:true});
 // Construct an environment instead of inheriting application overrides,
 // project indices, Python import paths or Electron/Node injection settings.
 const fixtureEnv={HOME:home,TMPDIR:fixture,XDG_CONFIG_HOME:userData,
  PATH:'/usr/bin:/bin:/usr/sbin:/sbin',LANG:'en_US.UTF-8',LC_ALL:'en_US.UTF-8',
  RIEKE_PREFERENCES_DIR:path.join(home,'.rieke-os'),
  RIEKE_PROJECT_INDEX:path.join(userData,'backend/preferences/project-index.json'),
  RIEKE_DESKTOP_USER_STATE:path.join(userData,'backend'),
  RIEKE_MANAGED_PROJECTS_ROOT:path.join(home,'projects'),RECORDING_WORKSPACE_ROOT:path.join(home,'projects'),
  PYTHONDONTWRITEBYTECODE:'1',PYTHONNOUSERSITE:'1'};
 for(const directory of [fixture,home,userData]){const info=await fs.lstat(directory);assert.equal(info.isSymbolicLink(),false);assert.equal(info.uid,process.getuid());assert.equal(await fs.realpath(directory),directory);}
 assert.ok(fixture.startsWith(await fs.realpath(os.tmpdir())+path.sep));
 const receipt={format:'disco-native-project-retention-v1',status:'running',source_commit:manifest.source_commit,desktop_source_sha256:desktopHashes,desktop,runtime,fixture,expect_warm_fastpath:expectFastpath,
  limitations:['Two empty native projects; no populated database or waveform latency qualification.','Elapsed times include Playwright orchestration and frame observations.','Development Electron runtime; not an installed or packaged-app qualification.'],samples:[],requests:[],cleanup:{}};
 let application,activePage,exited=false;
 try{
  await run(path.join(runtime,'python/bin/python3.11'),['-B',path.join(__dirname,'seed-retention-projects.py'),path.join(runtime,'application'),home,runtime],{env:fixtureEnv});
  const projects=JSON.parse(await fs.readFile(path.join(home,'projects.json')));receipt.projects=projects;
  for(const project of projects)assert.ok((await fs.realpath(project.path)).startsWith(home+path.sep));
  receipt.isolation={home,userData,project_index:fixtureEnv.RIEKE_PROJECT_INDEX,preferences:fixtureEnv.RIEKE_PREFERENCES_DIR,inherited_environment:false};
  application=await _electron.launch({executablePath,args:[desktop,`--user-data-dir=${userData}`],env:fixtureEnv,chromiumSandbox:true,bypassCSP:false,timeout:45000});captureNativeProcess(application,output,receipt,'initial');
  const actual=await application.evaluate(({app})=>({home:process.env.HOME,userData:app.getPath('userData'),appPath:app.getAppPath(),packaged:app.isPackaged,pid:process.pid,electron:process.versions.electron}));
  assert.equal(actual.home,home);assert.equal(actual.userData,userData);assert.equal(actual.appPath,desktop);assert.equal(actual.packaged,false);receipt.runtime_identity=actual;
  const record=page=>recordNativeRequests(page,receipt);
  application.context().pages().forEach(record);application.context().on('page',record);
  await application.evaluate(({app})=>{
    globalThis.__retentionNavigations=[];
    app.on('web-contents-created',(_event,wc)=>wc.on('did-start-navigation',(_event,url,inPlace,isMainFrame)=>{if(isMainFrame)globalThis.__retentionNavigations.push({id:wc.id,url,inPlace,at:Date.now()});}));
  });
  const currentPage=project=>currentProjectPage(application,project,receipt);
  let launcher;const chooserDeadline=Date.now()+45000;
  while(!launcher&&Date.now()<chooserDeadline){
    for(const page of application.context().pages())if(await page.locator('.project-launcher').isVisible().catch(()=>false)){launcher=page;break;}
    if(!launcher)await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert.ok(launcher,'Owned launcher renderer must become visible');activePage=launcher;
  await launcher.getByRole('button',{name:`Open ${projects[0].name}, ${projects[0].path}`,exact:true}).click();
  const initialA=await currentPage(projects[0]);activePage=initialA.page;
  await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor({timeout:120000});await prepareInitialPresentation(activePage,receipt);
  await activePage.getByRole('button',{name:'Data stores',exact:true}).click();await activePage.getByRole('heading',{name:'Data stores',exact:true}).waitFor({timeout:30000});
  const token=await activePage.evaluate(()=>window.__nativeRetentionToken=crypto.randomUUID());
  await activePage.evaluate(()=>{window.__nativeRetentionNode=document.querySelector('.data-stores');});
  // Preload B separately. Only later switches between two ready views are timed.
  receipt.phase='cold-project-B';
  await activePage.getByRole('button',{name:projects[1].name,exact:true}).click();
  const initialB=await currentPage(projects[1]);activePage=initialB.page;
  await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor({timeout:120000});await prepareInitialPresentation(activePage,receipt);
  const tokenB=await activePage.evaluate(()=>{window.__nativeRetentionNode=document.querySelector('.infographic-overview');return window.__nativeRetentionToken=crypto.randomUUID();});
  await activePage.getByRole('button',{name:projects[0].name,exact:true}).click();activePage=(await currentPage(projects[0])).page;
  await activePage.getByRole('heading',{name:'Data stores',exact:true}).waitFor();
  async function retainedCheck(page,expectedToken,selector){const value=await page.evaluate(({expectedToken,selector})=>({same_document:window.__nativeRetentionToken===expectedToken,same_node:document.querySelector(selector)===window.__nativeRetentionNode}),{expectedToken,selector});assert.deepEqual(value,{same_document:true,same_node:true});return value;}
  for(let sample=0;sample<3;sample++){
    await measureRetainedSwitch({application,fromPage:activePage,project:projects[1],view:initialB,receipt,sample,direction:'A-to-B',expectFastpath,check:page=>retainedCheck(page,tokenB,'.infographic-overview')});activePage=initialB.page;
    const result=await measureRetainedSwitch({application,fromPage:activePage,project:projects[0],view:initialA,receipt,sample,direction:'B-to-A',expectFastpath,check:page=>retainedCheck(page,token,'.data-stores')});activePage=initialA.page;
    receipt.samples.push(result);await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  }
  await activePage.screenshot({path:path.join(output,'retained-project-A.png')});
  receipt.navigation_events=await application.evaluate(()=>globalThis.__retentionNavigations);
  for(const view of [initialA,initialB])assert.equal(receipt.navigation_events.filter(row=>row.id===view.id&&!row.inPlace).length,1,'Each preloaded project must load its document only once');
  // Actual bounded Quit asks every retained renderer to checkpoint its draft.
  const exit=new Promise(resolve=>application.process().once('exit',code=>resolve(code)));
  await activePage.evaluate(()=>{void window.riekeDesktop.quit();});
  const code=await Promise.race([exit,new Promise((_,reject)=>setTimeout(()=>reject(Error('Owned native Quit timed out')),45000).unref())]);
  assert.equal(code,0);exited=true;receipt.cleanup.orderly_exit=true;
  async function files(directory){const result=[];for(const item of await fs.readdir(directory,{withFileTypes:true})){const name=path.join(directory,item.name);if(item.isDirectory())result.push(...await files(name));else result.push(name);}return result;}
  const snapshots=[];for(const file of await files(path.join(userData,'scoped-views'))){if(file.endsWith('.json')){try{const value=JSON.parse(await fs.readFile(file));if(value.format==='rieke-renderer-draft')snapshots.push({file,projectId:value.projectId,route:value.value.route});}catch{}}}
  for(const project of projects)assert.ok(snapshots.some(value=>value.projectId===project.uuid),'Quit must checkpoint every retained project');
  receipt.saved_drafts=snapshots;
  for(const project of projects){const owner=JSON.parse(await fs.readFile(path.join(project.path,'database/native-owner.json')));assert.equal(owner.clean_shutdown,true,'Native project must close cleanly');}
  // Fresh main/renderer process: only saved scoped drafts may restore the view.
  application=await _electron.launch({executablePath,args:[desktop,`--user-data-dir=${userData}`],env:fixtureEnv,chromiumSandbox:true,bypassCSP:false,timeout:45000});captureNativeProcess(application,output,receipt,'restart');
  exited=false;
  const reopened=await currentPage(projects[0]);activePage=reopened.page;
  await activePage.getByRole('heading',{name:'Data stores',exact:true}).waitFor({timeout:120000});await prepareInitialPresentation(activePage,receipt);
  assert.equal(await activePage.evaluate(()=>window.__nativeRetentionToken),undefined);
  const restored=await activePage.evaluate(()=>({route:history.state?.riekeWorkspace?.route,registry:null}));
  assert.equal(restored.route?.page,'stores');
  receipt.restart={new_process:true,project_uuid:projects[0].uuid,project_path:projects[0].path,restored_route:restored.route};
  const secondExit=new Promise(resolve=>application.process().once('exit',code=>resolve(code)));
  await activePage.evaluate(()=>{void window.riekeDesktop.quit();});
  assert.equal(await Promise.race([secondExit,new Promise((_,reject)=>setTimeout(()=>reject(Error('Restarted fixture Quit timed out')),45000).unref())]),0);
  exited=true;receipt.cleanup.restart_orderly_exit=true;receipt.status='passed';
 }catch(error){await failureEvidence(application,activePage,output,receipt,error);throw error;}
 finally{
  if(application&&!exited){try{await closeOwned(application,userData,receipt);}catch(error){receipt.cleanup.close_error=String(error);}}
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
