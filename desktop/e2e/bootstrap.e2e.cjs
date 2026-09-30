'use strict';
// Real downloaded app UI, installer copy/seal/quarantine checks and installed
// startup. Only Launch Services dispatch is stubbed in this disposable clone;
// it must never target the user's running application or profile.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {createHash}=require('node:crypto');
const {_electron}=require('playwright');
const asar=require('@electron/asar');
const {createFixture,launch,gracefulQuit,run}=require('./helpers.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const {bundleDigest}=require('../bootstrap.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-ui-e2e/bootstrap-receipt.json');
const receipt={format:'rieke-packaged-bootstrap-e2e',version:1,signed_qualification:false,checks:[],failures:[],method:'Real downloaded packaged clone with native install checks; only /usr/bin/open dispatch stubbed; isolated installed profile launched with Playwright'};
let fixture,application,page;
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(receipt,null,2)+'\n');}
async function check(name,fn){try{const evidence=await fn();receipt.checks.push({name,passed:true,evidence});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
async function main(){
 fixture=await createFixture({reuse:false});receipt.fixture_root=fixture.root;
 const target=fixture.bundle,downloaded=path.join(fixture.home,'Downloads','Rieke OS.app');
 const resources=path.join(target,'Contents/Resources'),sourceAsar=path.join(resources,'app.asar');
 receipt.source_app_asar_sha256=createHash('sha256').update(await fs.readFile(sourceAsar)).digest('hex');
 const manifestBytes=await fs.readFile(path.join(resources,'runtime/runtime-manifest.json')),manifest=JSON.parse(manifestBytes);
 receipt.source_manifest_sha256=createHash('sha256').update(manifestBytes).digest('hex');receipt.application_version=manifest.application_version;
 await fs.mkdir(path.dirname(downloaded),{recursive:true});await fs.rename(target,downloaded);
 fixture.bundle=downloaded;fixture.executable=path.join(downloaded,'Contents/MacOS/Rieke OS');
 const archive=path.join(downloaded,'Contents/Resources/app.asar'),unpacked=path.join(fixture.root,'bootstrap-test-asar'),handoff=path.join(fixture.home,'launch-services-handoff.json');
 asar.extractAll(archive,unpacked);
 const mainFile=path.join(unpacked,'main.cjs'),original=await fs.readFile(mainFile,'utf8');
 const exact="const {execFile} = require('node:child_process');";
 assert.ok(original.includes(exact),'Expected packaged main OS process boundary');
 const wrapper=`const nativeExecFile = require('node:child_process').execFile;
const execFile = (...args) => nativeExecFile(...args);
execFile[require('node:util').promisify.custom] = async (file, args) => {
 if (file === '/usr/bin/open') { require('node:fs').writeFileSync(${JSON.stringify(handoff)}, JSON.stringify({file,args,home:process.env.HOME,userData:app.getPath('userData')})+'\\n',{mode:0o600}); return {stdout:'',stderr:''}; }
 return require('node:util').promisify(nativeExecFile)(file,args);
};`;
 await fs.writeFile(mainFile,original.replace(exact,wrapper));await asar.createPackage(unpacked,archive);asar.uncacheAll();
 const headerHash=createHash('sha256').update(asar.getRawHeader(archive).headerString).digest('hex');
 await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${headerHash}`,path.join(downloaded,'Contents/Info.plist')]);
 await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),downloaded]);
 await run('/usr/bin/codesign',['--verify','--deep','--strict',downloaded]);
 const quarantine='0083;66000000;Rieke-E2E;00000000-0000-4000-8000-000000000001';
 // Quarantine is assigned only AFTER this source test clone has launched.
 // The quarantined installed copy is never executed or stripped of quarantine.
 const before=await bundleDigest(downloaded);
 await check('downloaded clone displays explicit unsigned Install and Open before any backend starts',async()=>{
  application=await _electron.launch({executablePath:fixture.executable,args:[`--user-data-dir=${fixture.userData}`],env:{...process.env,HOME:fixture.home,TMPDIR:fixture.root,XDG_CONFIG_HOME:fixture.userData},chromiumSandbox:true,bypassCSP:false,timeout:45000});
  const actual=await application.evaluate(({app})=>({home:process.env.HOME,userData:app.getPath('userData'),appPath:app.getAppPath(),packaged:app.isPackaged}));
  assert.equal(actual.home,fixture.home);assert.equal(actual.userData,path.join(fixture.userData,'installer'));assert.ok(actual.appPath.startsWith(downloaded+'/'));assert.equal(actual.packaged,true);
  page=await application.firstWindow();await page.getByRole('heading',{name:'Install Rieke OS',exact:true}).waitFor();
  await page.getByText('Unsigned testing',{exact:true}).waitFor();assert.match(await page.locator('#detail').innerText(),/Open Anyway/);
  await page.getByRole('button',{name:'Install and Open',exact:true}).waitFor();
  assert.equal(await fs.stat(target).then(()=>true,()=>false),false);assert.equal(await fs.stat(handoff).then(()=>true,()=>false),false);
  assert.equal(await fs.stat(path.join(fixture.userData,'desktop-service.json')).then(()=>true,()=>false),false);
  await page.screenshot({path:path.join(path.dirname(output),'bootstrap-install-and-open.png')});
  await run('/usr/bin/xattr',['-w','com.apple.quarantine',quarantine,downloaded]);return {bootstrap:true,no_automatic_install:true,no_backend:true,isolated_installer_profile:true};
 });
 await check('explicit Install and Open copies the complete verified bundle and preserves quarantine and installed profile',async()=>{
  const exited=new Promise(resolve=>application.process().once('exit',resolve));await page.getByRole('button',{name:'Install and Open',exact:true}).click();
  const code=await Promise.race([exited,new Promise((_r,reject)=>setTimeout(()=>reject(new Error('Installer failed to complete its native copy')),420000).unref())]);assert.equal(code,0);
  const dispatch=JSON.parse(await fs.readFile(handoff,'utf8'));
  assert.deepEqual(dispatch.args,['-n','-a',target,'--env',`HOME=${fixture.home}`,'--args',`--user-data-dir=${fixture.userData}`]);assert.equal(dispatch.file,'/usr/bin/open');assert.equal(dispatch.home,fixture.home);
  assert.equal(await bundleDigest(target),before);assert.equal(await bundleDigest(downloaded),before);
  assert.equal((await run('/usr/bin/xattr',['-p','com.apple.quarantine',target])).stdout.trim(),quarantine);
  await verifyResources(path.join(target,'Contents/Resources/runtime'),manifest.resources);await run('/usr/bin/codesign',['--verify','--deep','--strict',target]);
  return {real_complete_copy:true,copy_hash_identical:true,source_unchanged:true,quarantine_preserved:true,exact_isolated_launch_profile:true,os_dispatch_only_stubbed:true};
 });
 await check('installed copy cold starts into Your projects using the base isolated profile',async()=>{
  // A completely separate never-quarantined fixture qualifies profile startup.
  fixture=await createFixture({reuse:false});receipt.unquarantined_profile_fixture_root=fixture.root;
  const cleanTarget=fixture.bundle,cleanDownload=path.join(fixture.home,'Downloads','Rieke OS.app'),cleanHandoff=path.join(fixture.home,'launch-services-handoff.json');
  await fs.mkdir(path.dirname(cleanDownload),{recursive:true});await fs.rename(cleanTarget,cleanDownload);
  const cleanArchive=path.join(cleanDownload,'Contents/Resources/app.asar'),cleanUnpacked=path.join(fixture.root,'profile-test-asar');asar.extractAll(cleanArchive,cleanUnpacked);
  const cleanMain=path.join(cleanUnpacked,'main.cjs'),cleanOriginal=await fs.readFile(cleanMain,'utf8');assert.ok(cleanOriginal.includes(exact));
  await fs.writeFile(cleanMain,cleanOriginal.replace(exact,wrapper.replace(JSON.stringify(handoff),JSON.stringify(cleanHandoff))));await asar.createPackage(cleanUnpacked,cleanArchive);asar.uncacheAll();
  await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(cleanArchive).headerString).digest('hex')}`,path.join(cleanDownload,'Contents/Info.plist')]);
  await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),cleanDownload]);await run('/usr/bin/codesign',['--verify','--deep','--strict',cleanDownload]);
  application=await _electron.launch({executablePath:path.join(cleanDownload,'Contents/MacOS/Rieke OS'),args:[`--user-data-dir=${fixture.userData}`],env:{...process.env,HOME:fixture.home,TMPDIR:fixture.root,XDG_CONFIG_HOME:fixture.userData},chromiumSandbox:true,bypassCSP:false,timeout:45000});
  page=await application.firstWindow();await page.getByRole('heading',{name:'Install Rieke OS',exact:true}).waitFor();
  const exited=new Promise(resolve=>application.process().once('exit',resolve));await page.getByRole('button',{name:'Install and Open',exact:true}).click();assert.equal(await Promise.race([exited,new Promise((_r,reject)=>setTimeout(()=>reject(new Error('Clean installer did not finish')),420000).unref())]),0);
  assert.deepEqual(JSON.parse(await fs.readFile(cleanHandoff,'utf8')).args,['-n','-a',cleanTarget,'--env',`HOME=${fixture.home}`,'--args',`--user-data-dir=${fixture.userData}`]);
  assert.equal(await run('/usr/bin/xattr',['-p','com.apple.quarantine',cleanTarget]).then(()=>true,error=>{if(error.code===1)return false;throw error;}),false,'This startup fixture must never carry quarantine');
  fixture.bundle=cleanTarget;fixture.executable=path.join(cleanTarget,'Contents/MacOS/Rieke OS');({application,page}=await launch(fixture));
  await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});assert.equal((await page.evaluate(()=>window.riekeDesktop.status())).channel,'unsigned-testing');
  await gracefulQuit(application,page);await verifyResources(path.join(cleanTarget,'Contents/Resources/runtime'),manifest.resources);return {manual_macos_approval_unqualified:true,separate_never_quarantined_fixture:true,real_installed_startup:true,base_profile_restored:true,native_orderly_exit:true,runtime_immutable:true};
 });
 assert.equal(receipt.failures.length,0);await write();console.log('Bootstrap receipt: '+output);
}
main().catch(async error=>{console.error(error.stack);receipt.failures.push({name:'bootstrap-suite',message:error.message});await write();process.exitCode=1;});
