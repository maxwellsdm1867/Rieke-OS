'use strict';
// Real packaged entry/copy/admission; only LaunchServices dispatch is captured
// so the owned physical child can be attached by Playwright. No validation mock.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {createHash}=require('node:crypto'),asar=require('@electron/asar');
const {createFixture,launch,gracefulQuit,cleanupOwnedFixture,run}=require('./qualification-helpers.cjs');
const {RuntimeGenerations,runtimeStore}=require('../runtime-generations.cjs');
const {bundleDigest,quarantinePreserved}=require('../bootstrap.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-ui-e2e/bootstrap-receipt.json');
const receipt={format:'rieke-packaged-bootstrap-e2e',version:2,signed_qualification:false,checks:[],failures:[],method:'Packaged unsigned front door, actual complete generation copy and admission; only native open dispatch captured before controlled physical-child launch'};
let fixture,application,page,secondApplication,secondPage;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(receipt,null,2)+'\n');}
async function check(name,fn){const started=Date.now();try{receipt.checks.push({name,passed:true,evidence:await fn(),elapsed_ms:Date.now()-started});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
async function waitFor(fn,timeout=420000){const deadline=Date.now()+timeout;while(Date.now()<deadline){const result=await fn();if(result)return result;await delay(250);}throw Error('Owned native condition did not complete');}
async function main(){
 fixture=await createFixture({reuse:false,prepare:false});receipt.fixture_root=fixture.root;
 const canonical=fixture.bundle,downloaded=path.join(fixture.home,'Downloads/Disco.app');
 const originalAsar=path.join(canonical,'Contents/Resources/app.asar');
 receipt.source_app_asar_sha256=createHash('sha256').update(await fs.readFile(originalAsar)).digest('hex');
 const manifestBytes=await fs.readFile(path.join(canonical,'Contents/Resources/runtime/runtime-manifest.json'));
 receipt.source_manifest_sha256=createHash('sha256').update(manifestBytes).digest('hex');receipt.application_version=JSON.parse(manifestBytes).application_version;
 assert.equal(JSON.parse(asar.extractFile(originalAsar,'package.json')).main,'entry.cjs');
 await fs.mkdir(path.dirname(downloaded),{recursive:true});await fs.rename(canonical,downloaded);
 const archive=path.join(downloaded,'Contents/Resources/app.asar'),stage=path.join(fixture.root,'front-door-asar'),handoff=path.join(fixture.root,'launch-handoff.json');
 asar.extractAll(archive,stage);
 const owner=path.join(stage,'runtime-generations.cjs'),source=await fs.readFile(owner,'utf8'),anchor='const run = promisify(execFile);';
 assert.equal(source.split(anchor).length,2);
 const wrapper=`const nativeRun=promisify(execFile);\nconst run=(file,args,options)=>{if(file==='/usr/bin/open'){require('node:fs').writeFileSync(${JSON.stringify(handoff)},JSON.stringify({file,args,home:process.env.HOME})+'\\n',{mode:0o600});return Promise.resolve({stdout:'',stderr:''});}return nativeRun(file,args,options);};`;
 await fs.writeFile(owner,source.replace(anchor,wrapper));await asar.createPackage(stage,archive);asar.uncacheAll();
 await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(archive).headerString).digest('hex')}`,path.join(downloaded,'Contents/Info.plist')]);
 await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),downloaded]);
 await run('/usr/bin/codesign',['--verify','--deep','--strict',downloaded]);
 const sourceDigest=await bundleDigest(downloaded),store=new RuntimeGenerations({root:runtimeStore(fixture.home),python:path.join(downloaded,'Contents/Resources/runtime/python/bin/python3.11')});
 const env={...process.env,HOME:fixture.home,TMPDIR:fixture.root,XDG_CONFIG_HOME:fixture.userData};delete env.ELECTRON_RUN_AS_NODE;
 await check('ordinary downloaded entry stages and requests scientific launch without an installer page',async()=>{
  await run(path.join(downloaded,'Contents/MacOS/Disco'),[`--user-data-dir=${fixture.userData}`],{env,timeout:420000});
  const dispatch=JSON.parse(await fs.readFile(handoff,'utf8')),current=store.current();
  assert.equal(dispatch.home,fixture.home);assert.equal(dispatch.args[2],current.generation.bundle);
  assert.ok(dispatch.args.includes(`--user-data-dir=${fixture.userData}`));assert.ok(dispatch.args.some(value=>value.startsWith('--disco-runtime-admission=')));
  assert.equal(await bundleDigest(current.generation.bundle),sourceDigest);assert.equal(await bundleDigest(downloaded),sourceDigest);
  assert.equal(await fs.stat(path.join(fixture.userData,'desktop-service.json')).then(()=>true,()=>false),false);
  fixture={...fixture,frontDoor:canonical,bundle:current.generation.bundle,executable:path.join(current.generation.bundle,'Contents/MacOS/Disco'),runtimeStore:store,
    preparedLaunch:{args:[dispatch.file,...dispatch.args]}};
  return {no_install_action:true,complete_verified_copy:true,source_unchanged:true,no_front_door_backend:true,exact_profile_and_admission:true};
 });
 await check('admitted physical runtime opens the chooser and refreshes the canonical front door',async()=>{
  ({application,page}=await launch(fixture));await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
  assert.equal((await application.evaluate(({app})=>app.getVersion())),receipt.application_version);
  await waitFor(async()=>fs.access(path.join(canonical,'Contents/Resources/runtime/runtime-manifest.json')).then(()=>true,()=>false));
  await run('/usr/bin/codesign',['--verify','--deep','--strict',canonical]);assert.equal(await bundleDigest(canonical),sourceDigest);
  await page.screenshot({path:path.join(path.dirname(output),'bootstrap-direct-chooser.png')});
  return {real_electron_and_backend:true,base_profile_preserved:true,canonical_promoted:true};
 });
 await check('opening canonical again reserves an independent profile and reuses the same complete runtime',async()=>{
  const profile=path.join(fixture.home,'second-state');await fs.mkdir(profile,{recursive:true});
  const before=store.current().id;
  await run(path.join(canonical,'Contents/MacOS/Disco'),[`--user-data-dir=${profile}`],{env:{...env,XDG_CONFIG_HOME:profile},timeout:90000});
  const dispatch=JSON.parse(await fs.readFile(handoff,'utf8'));
  assert.equal(store.current().id,before);
  const next={...fixture,userData:profile,preparedLaunch:{args:[dispatch.file,...dispatch.args]}};
  const launched=await launch(next);secondApplication=launched.application;secondPage=launched.page;
  await secondPage.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
  assert.equal(application.process().exitCode,null);assert.equal(secondApplication.process().exitCode,null);
  await gracefulQuit(secondApplication,secondPage);secondApplication=null;
  await gracefulQuit(application,page);application=null;
  return {two_real_sessions:true,independent_profiles:true,no_reinstallation:true,ordinary_quit:true};
 });
 await check('a never-executed quarantined source keeps quarantine through generation staging',async()=>{
  const quarantined=path.join(fixture.root,'quarantine-source/Disco.app');await fs.mkdir(path.dirname(quarantined),{recursive:true});await run('/usr/bin/ditto',[downloaded,quarantined]);
  const value='0083;66000000;Rieke-E2E;00000000-0000-4000-8000-000000000001';await run('/usr/bin/xattr',['-w','com.apple.quarantine',value,quarantined]);
  const isolated=new RuntimeGenerations({root:path.join(fixture.root,'quarantine-store'),python:path.join(downloaded,'Contents/Resources/runtime/python/bin/python3.11')});
  const generation=await isolated.stage(quarantined);
  const copied=(await run('/usr/bin/xattr',['-px','com.apple.quarantine',generation.bundle])).stdout.replace(/\s/g,'').toLowerCase();
  assert.equal(quarantinePreserved(Buffer.from(value).toString('hex'),copied),true);
  assert.equal(await bundleDigest(generation.bundle),sourceDigest);
  return {quarantine_preserved:true,quarantined_source_and_copy_never_executed:true,manual_macos_approval_unqualified:true};
 });
 receipt.passed=true;await write();console.log('Bootstrap receipt: '+output);
}
main().catch(async error=>{
 console.error(error.stack);receipt.failures.push({name:'bootstrap-suite',message:error.message});
 receipt.failure_cleanup=[await cleanupOwnedFixture(secondApplication,secondPage),await cleanupOwnedFixture(application,page)];
 await write();process.exitCode=1;
});
