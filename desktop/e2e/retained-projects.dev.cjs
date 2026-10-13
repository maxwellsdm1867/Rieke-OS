'use strict';
// Actual development main.cjs + WebContentsView integration. A separately staged,
// manifest-refreshed runtime is mandatory; never use the installed application.
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {createRequire}=require('node:module'),{execFile}=require('node:child_process');
const {promisify}=require('node:util'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const run=promisify(execFile);
const config={};for(let i=2;i<process.argv.length;i+=2){if(!process.argv[i].startsWith('--')||!process.argv[i+1])throw Error('Expected --key value');config[process.argv[i].slice(2)]=process.argv[i+1];}
for(const name of ['desktop-root','dependency-root','source-root','commit','output'])if(!config[name])throw Error(`Missing --${name}`);

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
 const receipt={format:'disco-native-project-retention-v1',status:'running',source_commit:manifest.source_commit,desktop_source_sha256:desktopHashes,desktop,runtime,fixture,
  limitations:['Two empty native projects; no populated database or waveform latency qualification.','Elapsed times include Playwright orchestration and frame observations.','Development Electron runtime; not an installed or packaged-app qualification.'],samples:[],requests:[],cleanup:{}};
 let application,activePage,exited=false;
 try{
  await run(path.join(runtime,'python/bin/python3.11'),['-B',path.join(__dirname,'seed-retention-projects.py'),path.join(runtime,'application'),home,runtime],{env:fixtureEnv});
  const projects=JSON.parse(await fs.readFile(path.join(home,'projects.json')));receipt.projects=projects;
  for(const project of projects)assert.ok((await fs.realpath(project.path)).startsWith(home+path.sep));
  receipt.isolation={home,userData,project_index:fixtureEnv.RIEKE_PROJECT_INDEX,preferences:fixtureEnv.RIEKE_PREFERENCES_DIR,inherited_environment:false};
  application=await _electron.launch({executablePath,args:[desktop,`--user-data-dir=${userData}`],env:fixtureEnv,chromiumSandbox:true,bypassCSP:false,timeout:45000});
  const actual=await application.evaluate(({app})=>({home:process.env.HOME,userData:app.getPath('userData'),appPath:app.getAppPath(),packaged:app.isPackaged,pid:process.pid,electron:process.versions.electron}));
  assert.equal(actual.home,home);assert.equal(actual.userData,userData);assert.equal(actual.appPath,desktop);assert.equal(actual.packaged,false);receipt.runtime_identity=actual;
  const record=page=>{page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/'))receipt.requests.push({at:performance.now(),page:page.url(),method:request.method(),url:request.url()});});};
  application.context().pages().forEach(record);application.context().on('page',record);
  await application.evaluate(({app})=>{
    globalThis.__retentionNavigations=[];
    app.on('web-contents-created',(_event,wc)=>wc.on('did-start-navigation',(_event,url,inPlace,isMainFrame)=>{if(isMainFrame)globalThis.__retentionNavigations.push({id:wc.id,url,inPlace,at:Date.now()});}));
  });
  async function currentPage(project){
    const until=Date.now()+45000;
    while(Date.now()<until){
      const attached=await application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().flatMap(window=>window.contentView.children.map(view=>view.webContents?{id:view.webContents.id,url:view.webContents.getURL(),bounds:view.getBounds()}:null).filter(Boolean)));
      for(const item of attached){
        const page=application.context().pages().find(page=>page.url()===item.url);
        if(page&&await page.getByRole('button',{name:`${project.name}, current project`,exact:true}).isVisible().catch(()=>false))return {page,...item};
      }
      await new Promise(resolve=>setTimeout(resolve,50));
    }
    throw Error(`Attached project renderer did not become current: ${project.name}`);
  }
  let launcher;const chooserDeadline=Date.now()+45000;
  while(!launcher&&Date.now()<chooserDeadline){
    for(const page of application.context().pages())if(await page.locator('.project-launcher').isVisible().catch(()=>false)){launcher=page;break;}
    if(!launcher)await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert.ok(launcher,'Owned launcher renderer must become visible');activePage=launcher;
  const opened=await launcher.evaluate(async directory=>{const response=await fetch('/api/projects/open-folder',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Request':'1'},body:JSON.stringify({directory})});return {status:response.status,result:await response.json()};},projects[0].path);
  assert.equal(opened.status,200);await launcher.evaluate(url=>window.riekeDesktop.activateProject(url),opened.result.url);
  const initialA=await currentPage(projects[0]);activePage=initialA.page;
  await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor({timeout:120000});
  await activePage.getByRole('button',{name:'Data stores',exact:true}).click();await activePage.getByRole('heading',{name:'Data stores',exact:true}).waitFor({timeout:30000});
  const token=await activePage.evaluate(()=>window.__nativeRetentionToken=crypto.randomUUID());
  for(let sample=0;sample<3;sample++){
    await activePage.getByRole('button',{name:projects[1].name,exact:true}).click();
    const b=await currentPage(projects[1]);activePage=b.page;
    await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor({timeout:120000});
    const before=receipt.requests.length,began=performance.now();
    await activePage.getByRole('button',{name:projects[0].name,exact:true}).click();
    const a=await currentPage(projects[0]);activePage=a.page;
    await activePage.getByRole('heading',{name:'Data stores',exact:true}).waitFor({timeout:30000});
    await activePage.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.equal(a.id,initialA.id);assert.equal(await activePage.evaluate(()=>window.__nativeRetentionToken),token);
    assert.ok(a.bounds.width>0&&a.bounds.height>0);
    const requests=receipt.requests.slice(before);
    assert.equal(requests.some(row=>new URL(row.url).pathname==='/api/overview'),false,'Warm project switch must not rebuild overview');
    receipt.samples.push({sample,total_ms:performance.now()-began,web_contents_id:a.id,same_document:true,bounds:a.bounds,requests});
  }
  await activePage.screenshot({path:path.join(output,'retained-project-A.png')});
  receipt.navigation_events=await application.evaluate(()=>globalThis.__retentionNavigations);
  assert.equal(receipt.navigation_events.filter(row=>row.id===initialA.id&&!row.inPlace).length,1,'A must load its document only once');
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
  application=await _electron.launch({executablePath,args:[desktop,`--user-data-dir=${userData}`],env:fixtureEnv,chromiumSandbox:true,bypassCSP:false,timeout:45000});
  exited=false;
  const reopened=await currentPage(projects[0]);activePage=reopened.page;
  await activePage.getByRole('heading',{name:'Data stores',exact:true}).waitFor({timeout:120000});
  assert.equal(await activePage.evaluate(()=>window.__nativeRetentionToken),undefined);
  const restored=await activePage.evaluate(()=>({route:history.state?.riekeWorkspace?.route,registry:null}));
  assert.equal(restored.route?.page,'stores');
  receipt.restart={new_process:true,project_uuid:projects[0].uuid,project_path:projects[0].path,restored_route:restored.route};
  const secondExit=new Promise(resolve=>application.process().once('exit',code=>resolve(code)));
  await activePage.evaluate(()=>{void window.riekeDesktop.quit();});
  assert.equal(await Promise.race([secondExit,new Promise((_,reject)=>setTimeout(()=>reject(Error('Restarted fixture Quit timed out')),45000).unref())]),0);
  exited=true;receipt.cleanup.restart_orderly_exit=true;receipt.status='passed';
 }catch(error){receipt.status='failed';receipt.error=String(error);if(activePage)await activePage.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});throw error;}
 finally{
  if(application&&!exited){try{await application.evaluate(({app})=>app.quit());await application.close();receipt.cleanup.fallback_close_requested=true;}catch(error){receipt.cleanup.close_error=String(error);}}
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
