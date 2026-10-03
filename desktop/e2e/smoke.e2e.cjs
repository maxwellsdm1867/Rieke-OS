'use strict';
// Routine qualification of one packaged build. Only the native folder chooser
// return value is mapped to this owned scratch fixture; no updater/install mock.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {createHash,randomUUID}=require('node:crypto');
const {createFixture,launch,gracefulQuit,ownedControl,run}=require('./helpers.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-smoke-e2e.json');
const started=Date.now(),workDeadline=started+240000,totalDeadline=started+300000;
const receipt={format:'rieke-packaged-smoke-e2e',version:1,started_at:new Date().toISOString(),total_deadline_ms:300000,
 signed_qualification:false,passed:false,checks:[],failures:[],warnings:[],
 seams:['Actual packaged Electron and owned scientific services in isolated HOME/userData.','Native folder chooser returns only this owned fixture folder.','Real update Check UI and status; offline handling never proves connectivity.'],
 limits:['Routine smoke only; no import/export, fault, signing or full runtime-hash qualification.']};
let fixture,application,page,aborted=false,finishing=false;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(receipt,null,2)+'\n');}
function remaining(){if(aborted||Date.now()>=workDeadline)throw new Error('Routine smoke reached its four-minute work budget; one minute reserved for orderly shutdown');return workDeadline-Date.now();}
async function bounded(promise,name,budget=45000){
 let timer;try{return await Promise.race([promise,new Promise((_resolve,reject)=>{timer=setTimeout(()=>{aborted=true;reject(new Error(`${name} exceeded the routine smoke deadline`));},Math.min(budget,remaining()));})]);}finally{clearTimeout(timer);}
}
async function check(name,fn){remaining();const began=Date.now();try{const evidence=await fn();remaining();receipt.checks.push({name,passed:true,elapsed_ms:Date.now()-began,evidence});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
async function bundleReceipts(){
 const resources=path.join(fixture.bundle,'Contents/Resources'),bytes=await fs.readFile(path.join(resources,'runtime/runtime-manifest.json'));
 return{manifest:JSON.parse(bytes),manifest_sha256:createHash('sha256').update(bytes).digest('hex'),asar_sha256:createHash('sha256').update(await fs.readFile(path.join(resources,'app.asar'))).digest('hex')};
}
async function ownedProcesses(){
 const physical=await fs.realpath(fixture.bundle),prefixes=[physical+'/',physical.replace(/^\/private\/var\//,'/var/')+'/'];
 const {stdout}=await run('/bin/ps',['-ww','-axo','pid=,comm='],{timeout:5000,maxBuffer:1024*1024});
 return stdout.split('\n').flatMap(line=>{const match=/^\s*(\d+)\s+(.+)$/.exec(line);return match&&prefixes.some(prefix=>match[2].startsWith(prefix))?[{pid:Number(match[1]),executable:match[2]}]:[];});
}
async function quitAndVerify(){
 const before=await ownedProcesses();assert.ok(before.length,'Owned packaged processes must exist before shutdown');
 await bounded(gracefulQuit(application,page),'Orderly quit',45000);application=null;page=null;
 const deadline=Math.min(workDeadline,Date.now()+10000);let left;
 do{left=await ownedProcesses();if(!left.length)break;await delay(200);}while(Date.now()<deadline);
 assert.equal(left.length,0,'Root, project, native database and Electron processes must all exit');
 await assert.rejects(fs.stat(path.join(fixture.userData,'desktop-service.json')),{code:'ENOENT'});
 return{orderly_exit:true,owned_processes_before:before.length,owned_processes_after:0,root_registry_removed:true};
}
async function authorProfile(){
 const dialog=page.getByRole('dialog',{name:'Tag author',exact:true});
 if(await dialog.waitFor({state:'visible',timeout:3000}).then(()=>true,()=>false)){
  const existing=dialog.getByRole('button',{name:'Smoke test',exact:true});
  if(await existing.count())await existing.first().click();else{await dialog.getByRole('textbox').fill('Smoke test');await dialog.getByRole('button',{name:'Create profile',exact:true}).click();}
  await dialog.waitFor({state:'hidden',timeout:10000});
 }
}
async function start(){
 ({application,page}=await bounded(launch(fixture),'Packaged launch'));
 page.setDefaultTimeout(20000);page.on('pageerror',error=>receipt.failures.push({name:'renderer-pageerror',message:error.message}));
 await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:Math.min(60000,remaining())});
}
async function main(){
 fixture=await bounded(createFixture(),'Owned fixture preparation',90000);receipt.fixture_root=fixture.root;
 assert.equal((await ownedProcesses()).length,0,'Reusable fixture must have no running app or scientific service');
 const initial=await bundleReceipts(),manifest=initial.manifest;
 assert.equal(manifest.format,'rieke-desktop-runtime');assert.equal(typeof manifest.application_version,'string');assert.ok(manifest.application_version);
 receipt.application_version=manifest.application_version;receipt.manifest_sha256=initial.manifest_sha256;receipt.asar_sha256=initial.asar_sha256;
 await check('packaged launcher starts with matching app and backend versions',async()=>{
  await start();const brand=await application.evaluate(({app,Menu})=>({name:app.getName(),version:app.getVersion(),executable:process.execPath,menu:Menu.getApplicationMenu().items[0].label,quit:Menu.getApplicationMenu().items[0].submenu.items.at(-1).label}));
  const version=brand.version;assert.equal(version,manifest.application_version);assert.equal(brand.name,'Disco');assert.equal(brand.menu,'Disco');assert.equal(brand.quit,'Quit Disco');assert.equal(path.basename(brand.executable),'Disco');assert.equal(path.basename(fixture.bundle),'Disco.app');
  const health=await bounded(ownedControl(fixture,'health'),'Root readiness');assert.equal(health.ready,true);assert.equal(health.application_version,version);
  return{app_version:version,root_ready:true,isolated_home_and_profile:true,branding:brand};
 });
 await check('explicit update Check returns an honest valid result',async()=>{
  await page.getByRole('button',{name:/^App Updates(?: —|$)/}).first().click();const dialog=page.getByRole('dialog',{name:'App Updates',exact:true}),button=dialog.getByRole('button',{name:'Check for updates',exact:true});
  await bounded(button.click({timeout:Math.min(45000,remaining())}),'Explicit update Check');
  // Poll asynchronous IPC explicitly and assert the same completed snapshot.
  const status=await bounded((async()=>{
   for(;;){
    remaining();
    const snapshot=await page.evaluate(async()=>({status:await window.riekeDesktop.status(),
     enabled:[...document.querySelectorAll('.app-update-dialog button')].some(button=>button.textContent.includes('Check for updates')&&!button.disabled)}));
    const status=snapshot.status,terminal=['Current','Available','Deferred','Ready','Downloading','Validating'];
    if(!status||!terminal.includes(status.state)&&status.state!=='Checking')return status||{state:'Invalid'};
    const checked=process.env.RIEKE_SMOKE_REQUIRE_UPDATE_CONNECTIVITY!=='1'||status.checked_at||status.state==='Deferred';
    if(terminal.includes(status.state)&&checked&&snapshot.enabled)return status;
    await delay(100);
   }
  })(),'Update Check response');
  receipt.update_status=status;await write();
  assert.ok(['Current','Available','Deferred','Ready','Downloading','Validating'].includes(status.state),'Unexpected update result: '+JSON.stringify(status));assert.equal(status.installed,manifest.application_version);
  assert.ok(status.available===null||typeof status.available==='string');assert.equal(typeof status.message,'string');
  const connected=Boolean(status.checked_at&&!status.check_error&&['Current','Available','Downloading','Validating'].includes(status.state));
  receipt.update_connectivity_verified=connected;
  if(!connected)receipt.warnings.push('Update status was handled, but release-feed connectivity/availability was not verified.');
  if(process.env.RIEKE_SMOKE_REQUIRE_UPDATE_CONNECTIVITY==='1')assert.equal(connected,true,'This run requires a successful release-feed check');
  await dialog.getByRole('button',{name:'Close updates',exact:true}).click();
  return{state:status.state,available:status.available,checked_at:status.checked_at||null,check_error:status.check_error||null,message:status.message,connectivity_verified:connected,download_or_install_not_requested:true};
 });
 const leaf='smoke-'+randomUUID().slice(0,8),projectName='Packaged smoke '+leaf,projectPath=path.join(fixture.projects,leaf);let projectUuid,firstSession;
 await check('native folder selection creates and opens a real project',async()=>{
  await fs.mkdir(fixture.projects,{recursive:true});await page.getByRole('button',{name:/^Create a new project/}).click();const form=page.locator('.onboarding-create-form');await form.getByRole('textbox').first().fill(projectName);
  await application.evaluate(({dialog},directory)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[directory]});},fixture.projects);
  await form.getByRole('button',{name:'Browse: New project folder',exact:true}).click();const picker=page.getByRole('dialog',{name:'New project folder',exact:true});
  await picker.getByRole('checkbox',{name:'Create a new folder inside this location'}).check();await picker.getByRole('textbox',{name:'New folder name',exact:true}).fill(leaf);await picker.getByRole('button',{name:'Use new folder',exact:true}).click();
  assert.equal(await form.locator('#new-project-directory').inputValue(),projectPath);await form.getByRole('button',{name:'Create & open',exact:true}).click();
  await page.getByRole('button',{name:'Project overview',exact:true}).waitFor({timeout:Math.min(60000,remaining())});await authorProfile();
  const project=await page.evaluate(()=>fetch('/api/projects').then(response=>response.json()));projectUuid=project.current_project_uuid;assert.ok(projectUuid);
  assert.ok((await fs.stat(projectPath)).isDirectory());const health=await bounded(ownedControl(fixture,'health'),'Project readiness');firstSession=health.session_id;
  assert.ok(health.services.some(service=>service.project_uuid===projectUuid&&service.project_path===projectPath&&service.bound===true));receipt.project_uuid=projectUuid;
  return{project_uuid:projectUuid,native_project_service_ready:true,folder_selection_scoped_to_fixture:true};
 });
 await check('first orderly quit exits root and project services',quitAndVerify);
 await check('cold restart reopens the persisted project',async()=>{
  await start();await page.getByRole('button',{name:new RegExp('^Open '+projectName+',')}).click();await page.getByRole('button',{name:'Project overview',exact:true}).waitFor({timeout:Math.min(60000,remaining())});await authorProfile();
  const project=await page.evaluate(()=>fetch('/api/projects').then(response=>response.json()));assert.equal(project.current_project_uuid,projectUuid);
  const health=await bounded(ownedControl(fixture,'health'),'Reopened project readiness');assert.notEqual(health.session_id,firstSession);assert.ok(health.services.some(service=>service.project_uuid===projectUuid&&service.project_path===projectPath&&service.bound===true));
  return{same_project_uuid:true,new_owned_session:true,persisted_native_project_reopened:true};
 });
 await check('final orderly quit preserves original manifest and ASAR bytes',async()=>{
  const shutdown=await quitAndVerify(),after=await bundleReceipts();assert.equal(after.manifest_sha256,initial.manifest_sha256);assert.equal(after.asar_sha256,initial.asar_sha256);assert.equal(receipt.failures.length,0,'Renderer errors occurred');
  return{...shutdown,manifest_unchanged:true,asar_unchanged:true};
 });
 receipt.passed=true;receipt.elapsed_ms=Date.now()-started;await write();console.log('Routine smoke receipt: '+output);
}
async function finish(error){
 if(finishing)return;finishing=true;aborted=true;clearTimeout(workTimer);
 if(error){receipt.failures.push({name:'smoke-suite',message:error.message});receipt.elapsed_ms=Date.now()-started;
  if(application&&page){try{const child=application.process(),exit=child.exitCode!==null?Promise.resolve(child.exitCode):new Promise(resolve=>child.once('exit',resolve));const left=Math.max(1,Math.min(45000,totalDeadline-Date.now()));
   let result;
   try{result=await Promise.race([page.evaluate(()=>window.riekeDesktop.quit()),delay(left).then(()=>{throw new Error('Cleanup deadline reached');})]);}
   catch(error){if(!/Target.*closed/.test(error.message))throw error;}
   if(result&&!result.ready)throw new Error(result.reason||'Orderly closure was not acknowledged');const code=await Promise.race([exit,delay(Math.max(1,totalDeadline-Date.now())).then(()=>{throw new Error('Owned app did not exit before total deadline');})]);
   assert.equal(code,0,'Owned app must acknowledge successful exit');assert.equal((await ownedProcesses()).length,0,'Owned scientific services must exit even if renderer closes before the quit reply');receipt.failure_cleanup='orderly-exit';
  }catch(cleanup){receipt.failure_cleanup='owned-fixture-retained';receipt.warnings.push(cleanup.message);}}
  await write();console.error(error.message);
 }
 // Exit only this test controller. Never signal the app, its services, or
 // writers if normal shutdown is deferred; the owned fixture stays inspectable.
 process.exit(error?1:0);
}
const hardTimer=setTimeout(()=>{console.error('Routine smoke total deadline reached; only the test controller is exiting.');process.exit(1);},300000);
const workTimer=setTimeout(()=>{void finish(new Error('Routine smoke work deadline reached; preserving one minute for orderly shutdown'));},240000);
main().then(()=>finish(),finish);
