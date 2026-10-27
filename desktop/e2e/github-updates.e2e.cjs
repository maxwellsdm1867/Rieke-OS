'use strict';
// Official GitHub HTTPS transport is mapped to an owned loopback asset server;
// /usr/bin/open dispatch is captured, then the exact admitted runtime is launched
// with real Electron in the isolated fixture. Descriptor, ZIP, runtime validation,
// UI, draft/writer drain and ordinary Quit all run the packaged implementation.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),nativeFs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {createHash}=require('node:crypto'),asar=require('@electron/asar');
const {createFixture,prepareRuntime,launch,gracefulQuit,cleanupOwnedFixture,ownedControl,run}=require('./qualification-helpers.cjs');
const {showProjectSidebar,createRendererWatcher,waitForRenderer,captureRendererFailure}=require('./renderer-target.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const {RuntimeGenerations}=require('../runtime-generations.cjs');
const {bundleDigest}=require('../bootstrap.cjs');
const {releaseVersions}=require('./release-versions.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-ui-e2e/github-update-receipt.json');
const receipt={format:'rieke-packaged-github-update-ui-e2e',version:1,signed_qualification:false,checks:[],failures:[],method:'Synthetic prior clone with version metadata and test-only transport/native-open seams; official HTTPS GitHub URLs serve the real final descriptor and ZIP, /usr/bin/open dispatch is captured before real Electron launch of its admitted runtime; no candidate validation or drain mocks'};
let fixture,application,page,server,otherApplication,otherPage;const counts={api:0,descriptor:0,archive:0};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const watchRenderer=createRendererWatcher(error=>receipt.failures.push(error));
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify({...receipt,requests:counts},null,2)+'\n');}
async function check(name,fn){const start=Date.now();try{const evidence=await fn();receipt.checks.push({name,passed:true,elapsed_ms:Date.now()-start,evidence});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
async function main(){
 const published=path.resolve(__dirname,'../dist/mac-arm64/Disco.app'),sourceManifestFile=path.join(published,'Contents/Resources/runtime/runtime-manifest.json'),sourceBytes=await fs.readFile(sourceManifestFile),sourceManifest=JSON.parse(sourceBytes);
 receipt.source_manifest_sha256=createHash('sha256').update(sourceBytes).digest('hex');receipt.source_app_asar_sha256=createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/app.asar'))).digest('hex');
 const {candidateVersion,priorVersion}=releaseVersions(sourceManifest.application_version,process.env.RIEKE_E2E_PRIOR_VERSION);
 assert.equal(JSON.parse(asar.extractFile(path.join(published,'Contents/Resources/app.asar'),'package.json')).version,candidateVersion,'Packaged version must match candidate manifest');
 receipt.candidate_version=candidateVersion;receipt.synthetic_prior={version:priorVersion,authentic_published_release:false,construction:'Candidate clone with version metadata overlaid plus documented test-only HTTPS transport and /usr/bin/open capture seams'};
 fixture=await createFixture({reuse:false,prepare:false});receipt.fixture_root=fixture.root;
 const zip=path.resolve(__dirname,`../dist/Disco-${candidateVersion}-arm64.zip`),descriptorPath=path.join(fixture.root,'desktop-release.json');
 await run(path.join(fixture.bundle,'Contents/Resources/runtime/python/bin/python3.11'),['-B',path.resolve(__dirname,'../../tools/desktop_test_release.py'),'--app',published,'--archive',zip,'--output',descriptorPath],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 const descriptorBytes=await fs.readFile(descriptorPath),descriptor=JSON.parse(descriptorBytes);receipt.candidate_archive_sha256=descriptor.archive.sha256;
 assert.equal(descriptor.application_version,candidateVersion);assert.equal(descriptor.archive.filename,path.basename(zip));
 const tag=`desktop-test-v${candidateVersion}`,root=`https://github.com/maxwellsdm1867/Rieke-OS/releases/download/${tag}/`;
 const releases=Buffer.from(JSON.stringify([{draft:false,prerelease:true,tag_name:tag,assets:[{name:'desktop-release.json',browser_download_url:root+'desktop-release.json',size:descriptorBytes.length},{name:descriptor.archive.filename,browser_download_url:root+descriptor.archive.filename,size:descriptor.archive.size}]}]));
 server=http.createServer((request,response)=>{
  if(request.url==='/api'){counts.api++;response.writeHead(200,{'content-length':releases.length});response.end(releases);}
  else if(request.url==='/descriptor'){counts.descriptor++;response.writeHead(200,{'content-length':descriptorBytes.length});response.end(descriptorBytes);}
  else if(request.url==='/archive'){counts.archive++;response.writeHead(200,{'content-length':descriptor.archive.size});nativeFs.createReadStream(zip).pipe(response);}
  else{response.writeHead(404);response.end();}
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`,transport=path.join(fixture.root,'github-transport.cjs');
 await fs.writeFile(transport,`'use strict';const http=require('node:http');exports.transport=(url,{kind}={})=>{const target=url==='https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1'?'/api':url===${JSON.stringify(root+'desktop-release.json')}?'/descriptor':url===${JSON.stringify(root+descriptor.archive.filename)}?'/archive':null;if(!target)return Promise.reject(new Error('Unexpected official fixture URL'));return new Promise((resolve,reject)=>{http.get(${JSON.stringify(base)}+target,response=>resolve({statusCode:response.statusCode,headers:response.headers,body:response})).on('error',reject);});};\n`,{mode:0o600});
 const runtime=path.join(fixture.bundle,'Contents/Resources/runtime'),manifestFile=path.join(runtime,'runtime-manifest.json'),manifest=JSON.parse(await fs.readFile(manifestFile));manifest.application_version=priorVersion;
 const releaseNames=Object.keys(manifest.resources).filter(name=>name.endsWith('/rieke-release.json'));
 assert.ok(releaseNames.includes('application/rieke-release.json'));
 for(const name of releaseNames){const file=path.join(runtime,name),release=JSON.parse(await fs.readFile(file));release.version=priorVersion;const bytes=Buffer.from(JSON.stringify(release,null,2)+'\n');await fs.writeFile(file,bytes);manifest.resources[name]={...manifest.resources[name],sha256:createHash('sha256').update(bytes).digest('hex'),size:bytes.length};}
 await fs.writeFile(manifestFile,JSON.stringify(manifest,null,2)+'\n');
 const archive=path.join(fixture.bundle,'Contents/Resources/app.asar'),unpacked=path.join(fixture.root,'update-ui-test-asar');asar.extractAll(archive,unpacked);
 const mainFile=path.join(unpacked,'main.cjs'),original=await fs.readFile(mainFile,'utf8'),anchor='manifest: supervisor.manifest, distribution});';assert.ok(original.includes(anchor));
 await fs.writeFile(mainFile,original.replace(anchor,`manifest: supervisor.manifest, distribution, transport: require(${JSON.stringify(transport)}).transport});`));
 const launchHandoff=path.join(fixture.root,'generation-launch.json'),ownerFile=path.join(unpacked,'runtime-generations.cjs'),ownerSource=await fs.readFile(ownerFile,'utf8');
 const runAnchor='const run = promisify(execFile);';assert.equal(ownerSource.split(runAnchor).length,2);
 await fs.writeFile(ownerFile,ownerSource.replace(runAnchor,`const nativeRun=promisify(execFile); const run=(file,args,options)=>{if(file==='/usr/bin/open'){require('node:fs').writeFileSync(${JSON.stringify(launchHandoff)},JSON.stringify({file,args})+'\\n',{mode:0o600});return Promise.resolve({stdout:'',stderr:''});}return nativeRun(file,args,options);};`));
 const packageFile=path.join(unpacked,'package.json'),pack=JSON.parse(await fs.readFile(packageFile));pack.version=priorVersion;await fs.writeFile(packageFile,JSON.stringify(pack,null,2)+'\n');
 await asar.createPackage(unpacked,archive);asar.uncacheAll();const plist=path.join(fixture.bundle,'Contents/Info.plist');
 await run('/usr/libexec/PlistBuddy',['-c',`Set :CFBundleShortVersionString ${priorVersion}`,plist]);await run('/usr/libexec/PlistBuddy',['-c',`Set :CFBundleVersion ${priorVersion}`,plist]);
 await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(archive).headerString).digest('hex')}`,plist]);
 await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),fixture.bundle]);await run('/usr/bin/codesign',['--verify','--deep','--strict',fixture.bundle]);
 await verifyResources(runtime,manifest.resources);receipt.test_current_version=priorVersion;
 fixture=await prepareRuntime(fixture);
 const priorGeneration=fixture.generation.id,priorGenerationDigest=await bundleDigest(fixture.bundle);
 ({application,page}=await launch(fixture));watchRenderer(page);
 await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
 await check('background official release metadata creates a quiet version notice without downloading',async()=>{
  await page.waitForFunction(version=>[...document.querySelectorAll('.app-update-badge')].some(node=>node.textContent===`v${version}`),candidateVersion,{timeout:30000});
  assert.ok(counts.api>0&&counts.descriptor>0);assert.equal(counts.archive,0);const status=await page.evaluate(()=>window.riekeDesktop.status());assert.equal(status.state,'Available');assert.equal(status.available,candidateVersion);assert.equal(status.channel,'unsigned-testing');assert.equal(status.manual_updates,true);return {visible_available_version:candidateVersion,automatic_metadata:true,no_archive_download:true};
 });
 await check('explicit Check and Download prepare a fully validated real ZIP and show Restart to update',async()=>{
  await page.getByRole('button',{name:/^App Updates(?: —|$)/}).first().click();const dialog=page.getByRole('dialog',{name:'App Updates',exact:true});
  assert.match(await dialog.innerText(),/Unsigned testing/);assert.doesNotMatch(await dialog.innerText(),/New versions download automatically|next launch applies/);
  const before=counts.api;await dialog.getByRole('button',{name:'Check for updates',exact:true}).click();await page.waitForFunction(()=>window.riekeDesktop.status().then(s=>s.state==='Available'));assert.ok(counts.api>before);assert.equal(counts.archive,0);
  await dialog.getByRole('button',{name:'Download update',exact:true}).click();await dialog.getByRole('button',{name:'Restart to update',exact:true}).waitFor({timeout:180000});
  const status=await page.evaluate(()=>window.riekeDesktop.status());assert.equal(status.state,'Ready');assert.equal(status.available,candidateVersion);assert.equal(status.can_restart,true);assert.equal(counts.archive,1);
  await page.screenshot({path:path.join(path.dirname(output),'github-testing-update-ready.png')});return {explicit_check:true,explicit_download:true,real_zip_validated:true,ready_version:status.available,no_install_before_restart:true};
 });
 if(process.env.RIEKE_E2E_H5)await check('Restart to update defers an actual importer while the current app remains usable',async()=>{
  await page.keyboard.press('Escape');await fs.mkdir(fixture.projects,{recursive:true});await page.getByRole('button',{name:/^Create a new project/}).click();const form=page.locator('.onboarding-create-form');await form.getByRole('textbox').first().fill('Testing update writer fixture');
  await application.evaluate(({dialog},directory)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[directory]});},fixture.projects);
  await form.getByRole('button',{name:'Browse: New project folder',exact:true}).click();const picker=page.getByRole('dialog',{name:'New project folder',exact:true});await picker.getByRole('checkbox',{name:'Create a new folder inside this location'}).check();await picker.getByRole('textbox',{name:'New folder name',exact:true}).fill('writer');await picker.getByRole('button',{name:'Use new folder',exact:true}).click();await page.getByRole('button',{name:'Create & open',exact:true}).click();page=watchRenderer(await waitForRenderer(application,{projectName:'Testing update writer fixture',bundle:fixture.bundle}));
  const author=page.getByRole('dialog',{name:'Tag author',exact:true});if(await author.waitFor({state:'visible',timeout:3000}).then(()=>true,()=>false)){await author.getByRole('textbox').fill('Update E2E');await author.getByRole('button',{name:'Create profile',exact:true}).click();await author.waitFor({state:'hidden'});}
  await showProjectSidebar(page);
  await page.getByRole('button',{name:'Project overview',exact:true}).waitFor({timeout:90000});
  const source=path.join(fixture.home,'writer.h5');await fs.copyFile(path.resolve(process.env.RIEKE_E2E_H5),source);
  const job=await page.evaluate(async source=>{const response=await fetch('/api/imports',{method:'POST',headers:{'content-type':'application/json','X-Workspace-Request':'1'},body:JSON.stringify({source_path:source})});if(!response.ok)throw new Error(await response.text());return response.json();},source);
  const before=await ownedControl(fixture,'health');await page.getByRole('button',{name:/^App Updates(?: —|$)/}).first().click();const dialog=page.getByRole('dialog',{name:'App Updates',exact:true});
  const active=await page.evaluate(async id=>(await fetch('/api/jobs').then(r=>r.json())).jobs.find(j=>j.job_uuid===id),job.job_uuid);
  assert.ok(active&&!['complete','completed','failed','cancelled'].includes(active.status),'Importer must still be active immediately before Restart');
  await dialog.getByRole('button',{name:'Restart to update',exact:true}).click();
  await page.waitForFunction(()=>window.riekeDesktop.status().then(value=>value.state==='Current'&&/new version opened/.test(value.message||'')),null,{timeout:420000});
  const deferralReason=(await page.evaluate(()=>window.riekeDesktop.status())).message;assert.match(deferralReason,/draft|import|work|busy|writer|Scientific operations are still active/i);assert.equal(page.isClosed(),false);assert.equal((await ownedControl(fixture,'health')).pid,before.pid);
  const dispatch=JSON.parse(await fs.readFile(launchHandoff,'utf8')),selected=fixture.runtimeStore.current();
  assert.ok(dispatch.args.includes('--disco-new-session'));
  const separate={...fixture,bundle:selected.generation.bundle,executable:path.join(selected.generation.bundle,'Contents/MacOS/Disco'),generation:{id:selected.id},allowSessionSlot:true,preparedLaunch:{args:[dispatch.file,...dispatch.args]}};
  const fresh=await launch(separate);otherApplication=fresh.application;otherPage=fresh.page;
  await otherPage.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
  assert.equal((await otherApplication.evaluate(({app})=>app.getVersion())),candidateVersion);
  let done;for(let n=0;n<240;n++){done=await page.evaluate(async id=>(await fetch('/api/jobs').then(r=>r.json())).jobs.find(j=>j.job_uuid===id),job.job_uuid);if(['complete','completed','failed','cancelled'].includes(done?.status))break;await delay(500);}assert.ok(['complete','completed'].includes(done?.status));await gracefulQuit(otherApplication,otherPage);otherApplication=null;await fs.unlink(launchHandoff);await page.keyboard.press('Escape');return {busy_session_transfer_deferred:true,new_version_opened_independently:true,active_import_status_before_restart:active.status,deferral_reason:deferralReason,deferral_barrier:/draft/i.test(deferralReason)?'draft-persistence':'writer-drain',writer_drain_exercised:!/draft/i.test(deferralReason),root_preserved:true,current_app_usable:true,real_import_completed:true};
 });
 await check('ordinary Quit preserves the running runtime and selected generation',async()=>{
  await page.keyboard.press('Escape');const stateBefore=(await page.evaluate(()=>window.riekeDesktop.status())).state;assert.ok(['Ready','Current'].includes(stateBefore));const selectionBefore=fixture.runtimeStore.current(),selectedBefore=selectionBefore.id;await gracefulQuit(application,page);application=null;assert.equal(fixture.runtimeStore.current().id,selectedBefore);
  const after=JSON.parse(await fs.readFile(manifestFile));assert.equal(after.application_version,priorVersion);await verifyResources(runtime,manifest.resources);
  assert.equal(await fs.stat(path.join(path.dirname(fixture.bundle),'.Rieke OS.previous.app')).then(()=>true,()=>false),false);const cache=path.join(fixture.userData,'updates','unsigned-testing');const entries=await fs.readdir(cache).catch(()=>[]);assert.ok(!entries.some(name=>/^install-.*\.json$/.test(name)));return {ordinary_quit_did_not_change_selection:true,running_version:priorVersion,selected_version:selectionBefore.generation.manifest.application_version,update_activated_before_quit:stateBefore==='Current',runtime_immutable:true,native_orderly_exit:true};
 });
 await check('managed Restart activates the exact downloaded runtime while another old session stays usable',async()=>{
  const otherProfile=path.join(fixture.home,'other-session');await fs.mkdir(otherProfile,{recursive:true});
  const other={...fixture,userData:otherProfile,generation:{id:priorGeneration}};
  const second=await launch(other);otherApplication=second.application;otherPage=second.page;
  await otherPage.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
  ({application,page}=await launch(fixture));
  if(process.env.RIEKE_E2E_H5){await page.getByRole('heading',{name:'Testing update writer fixture',exact:true}).waitFor({timeout:90000});await showProjectSidebar(page);}else await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
  await page.waitForFunction(()=>window.riekeDesktop.status().then(value=>['Ready','Available'].includes(value.state)),null,{timeout:180000});
  await page.getByRole('button',{name:/^App Updates(?: —|$)/}).first().click();
  const dialog=page.getByRole('dialog',{name:'App Updates',exact:true}),exited=new Promise(resolve=>application.process().once('exit',resolve));
  if((await page.evaluate(()=>window.riekeDesktop.status())).state==='Available'){await dialog.getByRole('button',{name:'Download update',exact:true}).click();await dialog.getByRole('button',{name:'Restart to update',exact:true}).waitFor({timeout:180000});}
  await dialog.getByRole('button',{name:'Restart to update',exact:true}).click();
  assert.equal(await Promise.race([exited,new Promise((_,reject)=>setTimeout(()=>reject(Error('Managed restart did not exit')),420000).unref())]),0);application=null;
  let dispatch;for(let n=0;n<240;n++){try{dispatch=JSON.parse(await fs.readFile(launchHandoff,'utf8'));break;}catch(error){if(error.code!=='ENOENT')throw error;}await delay(250);}
  assert.ok(dispatch,'Exact-session helper must request the replacement launch');
  assert.ok(dispatch.args.includes('--disco-recover-session'));assert.ok(dispatch.args.includes(`--user-data-dir=${fixture.userData}`));
  const activation=fixture.runtimeStore.current();assert.equal(activation.generation.manifest.application_version,candidateVersion);
  assert.equal(await bundleDigest(activation.generation.bundle),await bundleDigest(published));
  assert.equal(await bundleDigest(fixture.bundle),priorGenerationDigest);
  assert.equal(otherApplication.process().exitCode,null);
  assert.equal((await otherApplication.evaluate(({app})=>app.getVersion())),priorVersion);
  const next={...fixture,bundle:activation.generation.bundle,executable:path.join(activation.generation.bundle,'Contents/MacOS/Disco'),generation:{id:activation.id},preparedLaunch:{args:[dispatch.file,...dispatch.args]}};
  const reopened=await launch(next);application=reopened.application;page=reopened.page;
  await page.getByRole('heading',{name:process.env.RIEKE_E2E_H5?'Testing update writer fixture':'Your projects',exact:true}).waitFor({timeout:90000});
  assert.equal((await ownedControl(next,'health')).application_version,candidateVersion);
  assert.equal((await application.evaluate(({app})=>app.getPath('userData'))),fixture.userData);
  receipt.updated_generation=activation.id;
  return {downloaded_bundle_exact:true,initiating_session_reopened_exact_profile:true,other_old_session_continues:true,old_runtime_immutable:true,launch_services_dispatch_only_captured:true};
 });
 await check('an older runtime is retained until its last session exits, then collected without removing project state',async()=>{
  const newer=path.join(fixture.root,'future-fixture/Disco.app');await fs.mkdir(path.dirname(newer),{recursive:true});await run('/usr/bin/ditto',[published,newer]);
  const parts=candidateVersion.split('.').map(Number),futureVersion=`${parts[0]}.${parts[1]}.${parts[2]+1}`;
  const futureRuntime=path.join(newer,'Contents/Resources/runtime'),futureManifestFile=path.join(futureRuntime,'runtime-manifest.json'),futureManifest=JSON.parse(await fs.readFile(futureManifestFile));
  futureManifest.application_version=futureVersion;
  for(const name of Object.keys(futureManifest.resources).filter(name=>name.endsWith('/rieke-release.json'))){const file=path.join(futureRuntime,name),value=JSON.parse(await fs.readFile(file));value.version=futureVersion;const bytes=Buffer.from(JSON.stringify(value,null,2)+'\n');await fs.writeFile(file,bytes);futureManifest.resources[name]={...futureManifest.resources[name],sha256:createHash('sha256').update(bytes).digest('hex'),size:bytes.length};}
  await fs.writeFile(futureManifestFile,JSON.stringify(futureManifest,null,2)+'\n');
  const futureArchive=path.join(newer,'Contents/Resources/app.asar'),futureAsar=path.join(fixture.root,'future-asar');asar.extractAll(futureArchive,futureAsar);
  const packageFile=path.join(futureAsar,'package.json'),value=JSON.parse(await fs.readFile(packageFile));value.version=futureVersion;await fs.writeFile(packageFile,JSON.stringify(value,null,2)+'\n');
  await asar.createPackage(futureAsar,futureArchive);asar.uncacheAll();const futurePlist=path.join(newer,'Contents/Info.plist');
  for(const key of ['CFBundleShortVersionString','CFBundleVersion'])await run('/usr/libexec/PlistBuddy',['-c',`Set :${key} ${futureVersion}`,futurePlist]);
  await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(futureArchive).headerString).digest('hex')}`,futurePlist]);
  await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),newer]);
  const store=new RuntimeGenerations({root:fixture.runtimeStore.root,python:path.join(newer,'Contents/Resources/runtime/python/bin/python3.11')});
  await store.activate(await store.stage(newer));
  const alive=await store.collect();assert.ok(!alive.removed.includes(priorGeneration));assert.equal(await bundleDigest(fixture.bundle),priorGenerationDigest);
  await gracefulQuit(otherApplication,otherPage);otherApplication=null;
  let result;for(let n=0;n<30;n++){result=await store.collect();if(result.removed.includes(priorGeneration))break;await delay(500);}
  assert.ok(result.removed.includes(priorGeneration),JSON.stringify(result));
  assert.equal(await fs.stat(fixture.bundle).then(()=>true,()=>false),false);
  assert.equal(application.process().exitCode,null);
  assert.equal((await application.evaluate(({app})=>app.getVersion())),candidateVersion);
  await gracefulQuit(application,page);application=null;
  receipt.synthetic_future={version:futureVersion,authentic_release:false,purpose:'Make original prior generation eligible beyond the retained rollback slot; never published'};
  return {live_old_generation_retained:true,normal_last_exit_releases_bytes:true,newer_session_survives_collection:true,scientific_state_untouched:true};
 });
 assert.equal(receipt.failures.length,0);await write();await new Promise(resolve=>server.close(resolve));server=null;console.log('GitHub update UI receipt: '+output);
}
main().catch(async error=>{
 application=error.launchedApplication||application||fixture?.activeApplication;
 page=error.launchedPage||page||fixture?.activePage;
 if(application)try{receipt.failure_targets=await captureRendererFailure(application,'github-updates');}catch{}
 console.error(error.stack);receipt.failures.push({name:'github-update-suite',message:error.message});
 receipt.failure_cleanup=[await cleanupOwnedFixture(otherApplication,otherPage),await cleanupOwnedFixture(application,page)];await write();
 server?.close();
 // Exit only this controller; a deferred owned app is retained for inspection.
 process.exit(1);
});
