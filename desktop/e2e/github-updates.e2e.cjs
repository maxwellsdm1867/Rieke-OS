'use strict';
// Only the official GitHub HTTPS transport is mapped to a loopback asset server
// inside an isolated test clone. Descriptor, ZIP, candidate/runtime validation,
// UI, draft/writer drain and ordinary Quit all run the packaged implementation.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),nativeFs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {createHash}=require('node:crypto'),asar=require('@electron/asar');
const {createFixture,launch,gracefulQuit,ownedControl,run}=require('./helpers.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-ui-e2e/github-update-receipt.json');
const receipt={format:'rieke-packaged-github-update-ui-e2e',version:1,signed_qualification:false,checks:[],failures:[],method:'Version-only Current clone, official HTTPS GitHub URLs mapped only at transport boundary to real final descriptor and ZIP; no candidate validation or drain mocks'};
let fixture,application,page,server;const counts={api:0,descriptor:0,archive:0};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify({...receipt,requests:counts},null,2)+'\n');}
async function check(name,fn){const start=Date.now();try{const evidence=await fn();receipt.checks.push({name,passed:true,elapsed_ms:Date.now()-start,evidence});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
async function main(){
 fixture=await createFixture({reuse:false});receipt.fixture_root=fixture.root;
 const published=path.resolve(__dirname,'../dist/mac-arm64/Rieke OS.app'),sourceManifestFile=path.join(published,'Contents/Resources/runtime/runtime-manifest.json'),sourceBytes=await fs.readFile(sourceManifestFile),sourceManifest=JSON.parse(sourceBytes);
 receipt.source_manifest_sha256=createHash('sha256').update(sourceBytes).digest('hex');receipt.source_app_asar_sha256=createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/app.asar'))).digest('hex');
 const candidateVersion=sourceManifest.application_version;assert.equal(candidateVersion,'0.1.3','Test scenario requires the final 0.1.3 package');
 const zip=path.resolve(__dirname,`../dist/Rieke-OS-${candidateVersion}-arm64.zip`),descriptorPath=path.join(fixture.root,'desktop-release.json');
 await run(path.join(fixture.bundle,'Contents/Resources/runtime/python/bin/python3.11'),['-B',path.resolve(__dirname,'../../tools/desktop_test_release.py'),'--app',published,'--archive',zip,'--output',descriptorPath],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 const descriptorBytes=await fs.readFile(descriptorPath),descriptor=JSON.parse(descriptorBytes);receipt.candidate_archive_sha256=descriptor.archive.sha256;
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
 const runtime=path.join(fixture.bundle,'Contents/Resources/runtime'),manifestFile=path.join(runtime,'runtime-manifest.json'),manifest=JSON.parse(await fs.readFile(manifestFile));manifest.application_version='0.1.2';
 const releaseNames=Object.keys(manifest.resources).filter(name=>name.endsWith('/rieke-release.json'));
 assert.ok(releaseNames.includes('application/rieke-release.json'));
 for(const name of releaseNames){const file=path.join(runtime,name),release=JSON.parse(await fs.readFile(file));release.version='0.1.2';const bytes=Buffer.from(JSON.stringify(release,null,2)+'\n');await fs.writeFile(file,bytes);manifest.resources[name]={sha256:createHash('sha256').update(bytes).digest('hex'),size:bytes.length};}
 await fs.writeFile(manifestFile,JSON.stringify(manifest,null,2)+'\n');
 const archive=path.join(fixture.bundle,'Contents/Resources/app.asar'),unpacked=path.join(fixture.root,'update-ui-test-asar');asar.extractAll(archive,unpacked);
 const mainFile=path.join(unpacked,'main.cjs'),original=await fs.readFile(mainFile,'utf8'),anchor='manifest: supervisor.manifest, distribution});';assert.ok(original.includes(anchor));
 await fs.writeFile(mainFile,original.replace(anchor,`manifest: supervisor.manifest, distribution, transport: require(${JSON.stringify(transport)}).transport});`));
 const packageFile=path.join(unpacked,'package.json'),pack=JSON.parse(await fs.readFile(packageFile));pack.version='0.1.2';await fs.writeFile(packageFile,JSON.stringify(pack,null,2)+'\n');
 await asar.createPackage(unpacked,archive);asar.uncacheAll();const plist=path.join(fixture.bundle,'Contents/Info.plist');
 await run('/usr/libexec/PlistBuddy',['-c','Set :CFBundleShortVersionString 0.1.2',plist]);await run('/usr/libexec/PlistBuddy',['-c','Set :CFBundleVersion 0.1.2',plist]);
 await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(archive).headerString).digest('hex')}`,plist]);
 await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),fixture.bundle]);await run('/usr/bin/codesign',['--verify','--deep','--strict',fixture.bundle]);
 await verifyResources(runtime,manifest.resources);receipt.test_current_version='0.1.2';
 ({application,page}=await launch(fixture));page.on('pageerror',error=>receipt.failures.push({name:'renderer-pageerror',message:error.message}));
 await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
 await check('background official release metadata creates a quiet version notice without downloading',async()=>{
  await page.waitForFunction(()=>[...document.querySelectorAll('.app-update-badge')].some(node=>node.textContent==='v0.1.3'),undefined,{timeout:30000});
  assert.ok(counts.api>0&&counts.descriptor>0);assert.equal(counts.archive,0);const status=await page.evaluate(()=>window.riekeDesktop.status());assert.equal(status.state,'Available');assert.equal(status.channel,'unsigned-testing');assert.equal(status.manual_updates,true);return {visible_available_version:'0.1.3',automatic_metadata:true,no_archive_download:true};
 });
 await check('explicit Check and Download prepare a fully validated real ZIP and show Restart to update',async()=>{
  await page.getByRole('button',{name:/^Release \/ Publish/}).first().click();const dialog=page.getByRole('dialog',{name:'Release / Publish',exact:true});
  assert.match(await dialog.innerText(),/Unsigned testing/);assert.doesNotMatch(await dialog.innerText(),/New versions download automatically|next launch applies/);
  const before=counts.api;await dialog.getByRole('button',{name:'Check for updates',exact:true}).click();await page.waitForFunction(()=>window.riekeDesktop.status().then(s=>s.state==='Available'));assert.ok(counts.api>before);assert.equal(counts.archive,0);
  await dialog.getByRole('button',{name:'Download update',exact:true}).click();await dialog.getByRole('button',{name:'Restart to update',exact:true}).waitFor({timeout:180000});
  const status=await page.evaluate(()=>window.riekeDesktop.status());assert.equal(status.state,'Ready');assert.equal(status.can_restart,true);assert.equal(counts.archive,1);
  await page.screenshot({path:path.join(path.dirname(output),'github-testing-update-ready.png')});return {explicit_check:true,explicit_download:true,real_zip_validated:true,ready_version:status.available,no_install_before_restart:true};
 });
 if(process.env.RIEKE_E2E_H5)await check('Restart to update defers an actual importer while the current app remains usable',async()=>{
  await page.keyboard.press('Escape');await fs.mkdir(fixture.projects,{recursive:true});await page.getByRole('button',{name:/Start a brand new project/}).click();const form=page.locator('.onboarding-create-form');await form.getByRole('textbox').first().fill('Testing update writer fixture');
  await application.evaluate(({dialog},directory)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[directory]});},fixture.projects);
  await form.getByRole('button',{name:'Browse: New project folder',exact:true}).click();const picker=page.getByRole('dialog',{name:'New project folder',exact:true});await picker.getByRole('checkbox',{name:'Create a new folder inside this location'}).check();await picker.getByRole('textbox',{name:'New folder name',exact:true}).fill('writer');await picker.getByRole('button',{name:'Use new folder',exact:true}).click();await page.getByRole('button',{name:'Create & open',exact:true}).click();await page.getByRole('button',{name:'Project overview',exact:true}).waitFor({timeout:90000});
  const author=page.getByRole('dialog',{name:'Tag author',exact:true});if(await author.waitFor({state:'visible',timeout:3000}).then(()=>true,()=>false)){await author.getByRole('textbox').fill('Update E2E');await author.getByRole('button',{name:'Create profile',exact:true}).click();}
  const source=path.join(fixture.home,'writer.h5');await fs.copyFile(path.resolve(process.env.RIEKE_E2E_H5),source);
  const job=await page.evaluate(async source=>{const response=await fetch('/api/imports',{method:'POST',headers:{'content-type':'application/json','X-Workspace-Request':'1'},body:JSON.stringify({source_path:source})});if(!response.ok)throw new Error(await response.text());return response.json();},source);
  const before=await ownedControl(fixture,'health');await page.getByRole('button',{name:/^Release \/ Publish/}).first().click();const dialog=page.getByRole('dialog',{name:'Release / Publish',exact:true});await dialog.getByRole('button',{name:'Restart to update',exact:true}).click();await dialog.getByRole('alert').waitFor({timeout:30000});
  assert.match(await dialog.getByRole('alert').innerText(),/import|work|busy|writer/i);assert.equal(page.isClosed(),false);assert.equal((await ownedControl(fixture,'health')).pid,before.pid);assert.equal((await page.evaluate(()=>window.riekeDesktop.status())).state,'Ready');
  let done;for(let n=0;n<240;n++){done=await page.evaluate(async id=>(await fetch('/api/jobs').then(r=>r.json())).jobs.find(j=>j.job_uuid===id),job.job_uuid);if(['complete','completed','failed','cancelled'].includes(done?.status))break;await delay(500);}assert.ok(['complete','completed'].includes(done?.status));await page.keyboard.press('Escape');return {busy_restart_deferred:true,root_preserved:true,current_app_usable:true,real_import_completed:true};
 });
 await check('ordinary Quit with a prepared testing update leaves the current complete app installed',async()=>{
  await page.keyboard.press('Escape');assert.equal((await page.evaluate(()=>window.riekeDesktop.status())).state,'Ready');await gracefulQuit(application,page);application=null;
  const after=JSON.parse(await fs.readFile(manifestFile));assert.equal(after.application_version,'0.1.2');await verifyResources(runtime,manifest.resources);
  assert.equal(await fs.stat(path.join(path.dirname(fixture.bundle),'.Rieke OS.previous.app')).then(()=>true,()=>false),false);const cache=path.join(fixture.userData,'updates','unsigned-testing');const entries=await fs.readdir(cache).catch(()=>[]);assert.ok(!entries.some(name=>/^install-.*\.json$/.test(name)));return {ordinary_quit_did_not_install:true,current_version:'0.1.2',runtime_immutable:true,native_orderly_exit:true};
 });
 assert.equal(receipt.failures.length,0);await write();await new Promise(resolve=>server.close(resolve));server=null;console.log('GitHub update UI receipt: '+output);
}
main().catch(async error=>{console.error(error.stack);receipt.failures.push({name:'github-update-suite',message:error.message});await write();server?.close();process.exitCode=1;});
