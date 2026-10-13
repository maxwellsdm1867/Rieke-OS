'use strict';
// Actual development main.cjs + WebContentsView integration. A separately staged,
// manifest-refreshed runtime is mandatory; never use the installed application.
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {createRequire}=require('node:module'),{execFile}=require('node:child_process');
const {promisify}=require('node:util'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const run=promisify(execFile);
const {captureNativeProcess,currentProjectPage,prepareInitialPresentation,failureEvidence,closeOwned}=require('./retention-native-support.cjs');
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
 const initialSource=(await run('git',['-C',source,'status','--porcelain'])).stdout;
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
 const receipt={format:'disco-native-populated-ui-audit-v1',status:'running',source_commit:manifest.source_commit,desktop_source_sha256:desktopHashes,desktop,runtime,fixture,
  limitations:['Synthetic63epoch/two-cell/two-response fixture; not real dataset or scale qualification.','Candidate-only actual UI audit; elapsed actions include Playwright.','Development Electron runtime; not packaged/installed qualification.'],actions:[],unsupported:[],requests:[],errors:[],cleanup:{}};
 let application,activePage,exited=false;
 try{
  await run(path.join(runtime,'python/bin/python3.11'),['-B',path.join(__dirname,'seed-retention-projects.py'),path.join(runtime,'application'),home,runtime],{env:fixtureEnv});
  const projects=JSON.parse(await fs.readFile(path.join(home,'projects.json')));receipt.projects=projects;
  for(const project of projects)assert.ok((await fs.realpath(project.path)).startsWith(home+path.sep));
  receipt.isolation={home,userData,project_index:fixtureEnv.RIEKE_PROJECT_INDEX,preferences:fixtureEnv.RIEKE_PREFERENCES_DIR,inherited_environment:false};
  application=await _electron.launch({executablePath,args:[desktop,`--user-data-dir=${userData}`],env:fixtureEnv,chromiumSandbox:true,bypassCSP:false,timeout:45000});captureNativeProcess(application,output,receipt,'initial');
  const actual=await application.evaluate(({app})=>({home:process.env.HOME,userData:app.getPath('userData'),appPath:app.getAppPath(),packaged:app.isPackaged,pid:process.pid,electron:process.versions.electron}));
  assert.equal(actual.home,home);assert.equal(actual.userData,userData);assert.equal(actual.appPath,desktop);assert.equal(actual.packaged,false);receipt.runtime_identity=actual;
  const record=page=>{page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/'))receipt.requests.push({at:performance.now(),page:page.url(),method:request.method(),url:request.url()});});};
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
  activePage.setDefaultTimeout(20000);
  const pending=[],responses=[];
  function observe(page){page.on('pageerror',error=>receipt.errors.push(String(error)));page.on('response',response=>{
    const url=new URL(response.url());if(!/^\/api\/epochs\/[^/]+\/trace$/.test(url.pathname))return;
    pending.push(response.json().then(value=>responses.push({url:response.url(),status:response.status(),value})).catch(error=>receipt.errors.push(String(error))));
  });}observe(activePage);
  const hash=async file=>createHash('sha256').update(await fs.readFile(file)).digest('hex');
  async function api(endpoint){return activePage.evaluate(async endpoint=>{const response=await fetch(endpoint);if(!response.ok)throw Error(await response.text());return response.json();},endpoint);}
  async function poll(fn,timeout=120000){const until=Date.now()+timeout;while(Date.now()<until){const result=await fn();if(result)return result;await new Promise(resolve=>setTimeout(resolve,100));}throw Error('Owned UI audit poll deadline');}
  async function shot(name){await activePage.screenshot({path:path.join(output,name+'.png')});}
  async function step(name,fn){const before=receipt.requests.length,began=performance.now();const row={name,status:'running',started_at:new Date().toISOString()};receipt.actions.push(row);await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');try{row.result=await fn();row.total_ms=performance.now()-began;row.requests=receipt.requests.slice(before);await shot(name);row.status='passed';}catch(error){row.status='failed';row.error=String(error);throw error;}finally{row.elapsed_ms=performance.now()-began;await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');}}
  const synthetic=path.join(home,'synthetic');
  await run(path.join(runtime,'python/bin/python3.11'),['-B',path.join(__dirname,'seed-dual-response-fixture.py'),synthetic,path.join(runtime,'python/lib/python3.11/site-packages/retinanalysis/utils/parse_data.py')],{env:fixtureEnv,timeout:45000});
  const oracle=JSON.parse(await fs.readFile(path.join(synthetic,'dual-oracle.json'))),fixtureReceipt=JSON.parse(await fs.readFile(path.join(synthetic,'dual-fixture-receipt.json'))),input=path.join(synthetic,'synthetic-dual.h5');
  assert.equal(fixtureReceipt.status,'passed');assert.equal(await hash(input),fixtureReceipt.h5_sha256);receipt.synthetic=fixtureReceipt;
  await step('01-import-through-ui',async()=>{
    await activePage.getByRole('button',{name:'Data stores',exact:true}).click();
    await activePage.getByRole('button',{name:'Import H5s',exact:true}).click();
    const chooser=activePage.waitForEvent('filechooser');await activePage.getByRole('button',{name:'Browse H5 files',exact:true}).click();await(await chooser).setFiles(input);
    const job=await poll(async()=>{const jobs=(await api('/api/jobs')).jobs;assert.ok(jobs.length<=1);const job=jobs[0];if(!job)return false;if(['failed','interrupted','duplicate','complete_with_warnings'].includes(job.status))throw Error(`Unexpected import terminal status ${job.status}`);return job.status==='complete'?job:false;});
    assert.equal(job.source_sha256,fixtureReceipt.h5_sha256);assert.equal(job.recording_storage?.verified,true);
    const managed=await fs.realpath(job.recording_storage.path);assert.ok(managed.startsWith(home+path.sep),'Managed recording must stay in owned HOME');assert.equal(await hash(managed),fixtureReceipt.h5_sha256);receipt.managed_source=managed;
    const overview=await api('/api/overview');assert.equal(overview.counts.epochs,63);assert.equal(overview.counts.cells,2);assert.equal(overview.protocols.length,1);receipt.protocol=overview.protocols[0].protocol_uuid;
    const review=activePage.getByRole('dialog',{name:'Review imported data',exact:true});
    await review.waitFor({timeout:30000});await shot('01-import-review');await review.getByRole('button',{name:'Done reviewing',exact:true}).click();
    return {epochs:63,cells:2,source_sha256:job.source_sha256};
  });
  await step('02-overview',async()=>{await activePage.getByRole('button',{name:'Project overview',exact:true}).click();await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor();return {protocol_count:await activePage.locator('.ov-protocol-row:visible').count()};});
  await step('03-protocol-and-inspect',async()=>{
    await activePage.locator('.ov-protocol-row:visible').first().click();await activePage.getByRole('tab',{name:'Inspect',exact:true}).click();
    await activePage.getByRole('button',{name:'Edit Tree',exact:true}).waitFor();
    const date=activePage.locator('.epoch-inspector-mode:visible .cell-tree-date:visible').first();await date.waitFor();if(!await date.evaluate(el=>el.open))await date.locator(':scope > summary').click();
    const cell=activePage.locator('.epoch-inspector-mode:visible .cell-tree-cell:visible').first();await cell.waitFor();if(!await cell.evaluate(el=>el.open))await cell.locator(':scope > summary').click();
    const epoch=activePage.locator('.epoch-inspector-mode:visible').getByRole('button',{name:/^Inspect .* epoch 1$/}).first();await epoch.click();
    await activePage.getByRole('region',{name:'Recorded response viewer',exact:true}).waitFor();
    await activePage.waitForFunction(()=>{const view=[...document.querySelectorAll('.epoch-inspector-mode')].find(el=>el.getClientRects().length);return !!view?.querySelector('.tv-base')&&!view.querySelector('.tv-status');});
    await Promise.all(pending);const painted=responses.filter(row=>row.status===200).at(-1);assert.ok(painted,'Actual renderer trace response must be observed');
    const expected=oracle.epochs.find(row=>row.uuid===painted.value.epoch_uuid);assert.ok(expected);receipt.inspected_epoch=expected;
    assertTrace(painted.value,expected);return {epoch_uuid:expected.uuid,renderer_trace:painted.url,count:painted.value.count};
  });
  function assertTrace(value,expected){assert.equal(value.epoch_uuid,expected.uuid);assert.equal(value.stream_uuid,expected.stream_uuid);assert.equal(value.sample_rate,10000);assert.equal(value.units,'pA');assert.equal(value.decimated,false);assert.deepEqual(value.values,Array.from({length:value.count},(_,i)=>expected.ordinal+(value.start+i)/256));}
  await step('04-metadata',async()=>{const details=activePage.getByRole('button',{name:'Details',exact:true});if(await details.getAttribute('aria-pressed')!=='true')await details.click();const panel=activePage.locator('.epoch-inspector-mode:visible .inspection-metadata:visible');await panel.getByRole('heading',{name:'Epoch details',exact:true}).waitFor();const allFields=panel.getByRole('button',{name:'All fields',exact:true});if(!await allFields.isVisible())await panel.getByRole('button',{name:'Load values',exact:true}).click();await allFields.click();await panel.locator('.metadata-panel-section').first().waitFor();const registered=(await api('/api/metadata/fields')).fields.length;assert.ok(registered>0);return {registered_fields:registered,visible_sections:await panel.locator('.metadata-panel-section:visible').count(),live_metadata:await panel.getByRole('switch',{name:'Live metadata',exact:true}).isChecked()};});
  await step('05-trace-window-and-cursor',async()=>{
    await activePage.getByRole('button',{name:'Sample',exact:true}).click();await activePage.getByRole('spinbutton',{name:'Start sample',exact:true}).fill('17');await activePage.getByRole('spinbutton',{name:'Sample count',exact:true}).fill('127');await activePage.locator('.tv-window-fields:visible').getByRole('button',{name:'Apply',exact:true}).click();
    await activePage.getByRole('spinbutton',{name:'Exact sample index for cursor',exact:true}).fill('20');
    await poll(async()=>await activePage.getByLabel('Recorded sample index',{exact:true}).textContent()==='20');
    const expected=receipt.inspected_epoch;assert.equal(await activePage.getByLabel('Recorded response and scientific units',{exact:true}).textContent(),`${expected.ordinal+20/256} pA`);
    const window=await api(`/api/epochs/${expected.uuid}/trace?stream_uuid=${expected.stream_uuid}&start=17&count=127`);assertTrace(window,expected);assert.equal(window.start,17);assert.equal(window.count,127);
    return {start:17,count:127,cursor:20,analytic_values_exact:true};
  });
  await step('05b-channel-switching',async()=>{
    const expected=receipt.inspected_epoch,checks=[];
    for(const name of ['Amp2','Amp1','Amp2']){
      const streamId=name==='Amp2'?expected.amp2.stream_uuid:expected.stream_uuid;
      const selector=activePage.locator('.tv-streams:visible button').filter({hasText:name});await selector.click();
      await poll(async()=>await selector.getAttribute('aria-pressed')==='true'&&!await activePage.locator('.tv-status:visible').count());
      await Promise.all(pending);
      const painted=responses.filter(row=>row.status===200&&row.value.epoch_uuid===expected.uuid&&row.value.stream_uuid===streamId).at(-1);assert.ok(painted,`Actual ${name} renderer response is required`);
      const value=painted.value,offset=name==='Amp2'?expected.amp2.offset:expected.ordinal,coefficient=name==='Amp2'?1/128:1/256;
      assert.equal(value.stream_uuid,streamId);assert.equal(value.sample_rate,10000);assert.equal(value.units,'pA');assert.deepEqual(value.values,Array.from({length:value.count},(_,i)=>offset+(value.start+i)*coefficient));
      await activePage.getByRole('spinbutton',{name:'Exact sample index for cursor',exact:true}).fill('20');await poll(async()=>await activePage.getByLabel('Recorded response and scientific units',{exact:true}).textContent()===`${offset+20*coefficient} pA`);
      checks.push({device:name,stream_uuid:streamId,exact_values:true});await shot('05b-channel-'+checks.length+'-'+name);
    }
    return {checks,selected_device:'Amp2'};
  });
  let savedScroll;
  await step('06-tree-scroll',async()=>{const tree=activePage.locator('.epoch-inspector-mode:visible .tree-scroll');await tree.hover();await activePage.mouse.wheel(0,140);await new Promise(resolve=>setTimeout(resolve,150));savedScroll=await tree.evaluate(el=>el.scrollTop);assert.ok(savedScroll>0,'Owned63epoch fixture must exercise actual scrolling');await activePage.evaluate(()=>{window.__auditInspector=[...document.querySelectorAll('.epoch-inspector-mode')].find(el=>el.getClientRects().length&&!el.closest('[hidden],[inert]'));window.__auditCanvas=window.__auditInspector?.querySelector('.tv-base');});return {scroll_top:savedScroll};});
  async function assertInspect(){assert.equal(await activePage.locator('.tv-streams:visible button').filter({hasText:'Amp2'}).getAttribute('aria-pressed'),'true');await activePage.getByRole('button',{name:'Edit Tree',exact:true}).waitFor();await poll(async()=>await activePage.getByRole('spinbutton',{name:'Start sample',exact:true}).inputValue()==='17');assert.equal(await activePage.getByRole('spinbutton',{name:'Sample count',exact:true}).inputValue(),'127');await poll(async()=>Math.abs(await activePage.locator('.epoch-inspector-mode:visible .tree-scroll').evaluate(el=>el.scrollTop)-savedScroll)<=1);const retained=await activePage.evaluate(()=>{const inspector=[...document.querySelectorAll('.epoch-inspector-mode')].find(el=>el.getClientRects().length&&!el.closest('[hidden],[inert]'));return {inspector:!!inspector&&inspector===window.__auditInspector,canvas:!!inspector?.querySelector('.tv-base')&&inspector.querySelector('.tv-base')===window.__auditCanvas};});assert.deepEqual(retained,{inspector:true,canvas:true});return retained;}
  await step('07-workbench',async()=>{await activePage.getByRole('tab',{name:'Workbench',exact:true}).click();await activePage.locator('.incoming-workbench:visible').waitFor();return {visible:true};});
  await step('08-inspect-return',async()=>{await activePage.getByRole('tab',{name:'Inspect',exact:true}).click();return assertInspect();});
  await step('09-overview-return',async()=>{await activePage.getByRole('button',{name:'Project overview',exact:true}).click();await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor();await shot('09-overview-away');await activePage.getByRole('button',{name:'Back to previous workspace',exact:true}).click();return assertInspect();});
  const token=await activePage.evaluate(()=>window.__populatedAuditToken=crypto.randomUUID());
  await step('10-project-away',async()=>{await activePage.getByRole('button',{name:projects[1].name,exact:true}).click();activePage=(await currentPage(projects[1])).page;await activePage.getByRole('region',{name:'Project infographic',exact:true}).waitFor();await prepareInitialPresentation(activePage,receipt);return {project_uuid:projects[1].uuid};});
  await step('11-project-return',async()=>{await activePage.getByRole('button',{name:projects[0].name,exact:true}).click();const a=await currentPage(projects[0]);activePage=a.page;assert.equal(a.id,initialA.id);assert.equal(await activePage.evaluate(()=>window.__populatedAuditToken),token);return assertInspect();});
  async function quit(){const exit=new Promise(resolve=>application.process().once('exit',resolve));await activePage.evaluate(()=>{void window.riekeDesktop.quit();});assert.equal(await Promise.race([exit,new Promise((_,reject)=>setTimeout(()=>reject(Error('Owned populated Quit timed out')),45000).unref())]),0);exited=true;}
  await quit();receipt.cleanup.orderly_exit=true;
  const owner=JSON.parse(await fs.readFile(path.join(projects[0].path,'database/native-owner.json')));assert.equal(owner.clean_shutdown,true);
  application=await _electron.launch({executablePath,args:[desktop,`--user-data-dir=${userData}`],env:fixtureEnv,chromiumSandbox:true,bypassCSP:false,timeout:45000});captureNativeProcess(application,output,receipt,'restart');exited=false;
  activePage=(await currentPage(projects[0])).page;activePage.setDefaultTimeout(20000);observe(activePage);
  await step('12-fresh-process-restore',async()=>{await activePage.getByRole('button',{name:'Edit Tree',exact:true}).waitFor({timeout:120000});await prepareInitialPresentation(activePage,receipt);assert.equal(await activePage.evaluate(()=>window.__populatedAuditToken),undefined);await poll(async()=>await activePage.getByRole('spinbutton',{name:'Start sample',exact:true}).inputValue()==='17');assert.equal(await activePage.getByRole('spinbutton',{name:'Sample count',exact:true}).inputValue(),'127');const data=await api('/api/overview');assert.equal(data.counts.epochs,63);assert.equal(data.counts.cells,2);assert.equal(await activePage.locator('.tv-streams:visible button').filter({hasText:'Amp2'}).getAttribute('aria-pressed'),'true');assert.equal(await hash(input),fixtureReceipt.h5_sha256);assert.equal(await hash(receipt.managed_source),fixtureReceipt.h5_sha256);return {new_process:true,start:17,count:127,epochs:63,cells:2,selected_device:'Amp2',source_bytes_unchanged:true};});
  await quit();receipt.cleanup.restart_orderly_exit=true;
  assert.equal((await run('git',['-C',source,'rev-parse','HEAD'])).stdout.trim(),config.commit);assert.equal((await run('git',['-C',source,'status','--porcelain'])).stdout,initialSource);assert.deepEqual(receipt.errors,[]);receipt.status='passed';
 }catch(error){await failureEvidence(application,activePage,output,receipt,error);throw error;}
 finally{
  if(application&&!exited){try{await closeOwned(application,userData,receipt);}catch(error){receipt.cleanup.close_error=String(error);}}
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
