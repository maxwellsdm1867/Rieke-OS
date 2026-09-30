'use strict';
// Real packaged updater/helper; only GitHub transport and macOS open are mapped
// to owned test boundaries. The source app, distribution and user app are read-only.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),nativeFs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{createHash}=require('node:crypto'),asar=require('@electron/asar');
const {createFixture,launch,gracefulQuit,ownedControl,run}=require('./helpers.cjs');
const {bundleDigest}=require('../bootstrap.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-testing-upgrade-e2e.json');
const receipt={format:'rieke-packaged-testing-native-upgrade-e2e',version:1,production_ready:false,checks:[],failures:[],
  seams:['Official GitHub HTTPS transport mapped to owned loopback server serving exact final ZIP/descriptor.',
         'Native helper macOS open boundary recorded instead of OS launch; installed app then starts with real Electron/WSGI in isolated HOME/profile.'],
  limits:['Synthetic version-only prior app, not an authentic previously published 0.1.2 desktop release.','Unsigned local host only; no signed update or clean-machine qualification.'],user_app_untouched:true};
let fixture,server,application;const requests={api:0,descriptor:0,archive:0};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify({...receipt,requests},null,2)+'\n');}
async function check(name,fn){const start=Date.now();try{const evidence=await fn();receipt.checks.push({name,passed:true,elapsed_ms:Date.now()-start,evidence});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
const WRAPPER=String.raw`
'use strict';
const fs=require('node:fs'),path=require('node:path'),{promisify}=require('node:util');
const realRun=promisify(require('node:child_process').execFile);
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const helper=require(path.join(config.bundle,'Contents/Resources/app.asar/testing-install.cjs'));
let opens=0;
helper.applyTestingInstall({receiptPath:process.argv[3],run:async(exe,args,options)=>{
 if(exe!=='/usr/bin/open')return realRun(exe,args,options);
 opens++;fs.appendFileSync(config.openLog,JSON.stringify({phase:config.phase,args})+'\n',{mode:0o600});
 if(config.fail_first_open&&opens===1)throw new Error('Owned test simulates macOS refusing the candidate launch');
 return {stdout:'',stderr:''};
}}).catch(error=>{fs.writeFileSync(process.argv[3]+'.result.json',JSON.stringify({state:'Deferred',error_type:error.name,message:error.message}));process.exitCode=1;});
`;
const DRIVER=String.raw`
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),{spawn}=require('node:child_process');
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const manifest=JSON.parse(fs.readFileSync(path.join(config.bundle,'Contents/Resources/runtime/runtime-manifest.json'),'utf8'));
const packaged=path.join(config.bundle,'Contents/Resources/app.asar');
const helper=require(path.join(packaged,'testing-install.cjs'));
const {createTestingUpdateCoordinator}=require(path.join(packaged,'testing-updater.cjs'));
const statuses=[];let coordinator,handoff,authorized=false;
const app={isPackaged:true,getPath:name=>name==='exe'?process.execPath:config.userData,quit(){
 coordinator?.stop();setTimeout(()=>{fs.writeFileSync(config.driverResult,JSON.stringify({phase:config.phase,authorized,statuses,handoff}),{mode:0o600});process.exit(0);},50);
}};
const transport=url=>{
 const route=url==='https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1'?'/api':
 url===config.descriptorURL?'/descriptor':url===config.archiveURL?'/archive':null;
 if(!route)return Promise.reject(new Error('Unexpected official release URL'));
 return new Promise((resolve,reject)=>http.get(config.base+route,response=>resolve({statusCode:response.statusCode,headers:response.headers,body:response})).on('error',reject));
};
const spawnHelper=(exe,args,options)=>spawn(exe,[config.wrapper,process.argv[2],args[2]],options);
(async()=>{
 const authorizeQuit=()=>{authorized=true;};
 if(config.phase==='restore'){
  handoff=await helper.restoreTestingPriorBundle({app,manifest,prepareQuit:async()=>({ready:true}),authorizeQuit,spawnHelper});
 }else{
  coordinator=createTestingUpdateCoordinator({app,manifest,distribution:require(path.join(packaged,'distribution.json')),transport,
   publishStatus:status=>{if(statuses.at(-1)!==status.state)statuses.push(status.state);},prepareQuit:async()=>({ready:true}),authorizeQuit,
   installHelper:async options=>{handoff=await helper.launchTestingInstall({...options,spawnHelper});return handoff;}});
  await coordinator.start();if(!['Available','Ready'].includes(coordinator.getStatus().state))throw new Error('Official fixture did not offer update');
  await coordinator.download();if(coordinator.getStatus().state!=='Ready')throw new Error('Real candidate validation did not become Ready');
  const result=await coordinator.installPrepared();if(!result.installing)throw new Error(result.reason||'Native install did not hand off');
 }
})().catch(error=>{coordinator?.stop();fs.writeFileSync(config.driverResult,JSON.stringify({error:error.message,statuses}),{mode:0o600});process.exitCode=1;});
`;
async function versionPrior(){
 const runtime=path.join(fixture.bundle,'Contents/Resources/runtime'),file=path.join(runtime,'runtime-manifest.json');
 const manifest=JSON.parse(await fs.readFile(file));manifest.application_version='0.1.2';
 for(const name of Object.keys(manifest.resources).filter(name=>name.endsWith('/rieke-release.json'))){
  const target=path.join(runtime,name),release=JSON.parse(await fs.readFile(target));release.version='0.1.2';const data=Buffer.from(JSON.stringify(release,null,2)+'\n');await fs.writeFile(target,data);
  manifest.resources[name]={...manifest.resources[name],sha256:createHash('sha256').update(data).digest('hex'),size:data.length};
 }
 await fs.writeFile(file,JSON.stringify(manifest,null,2)+'\n');
 const archive=path.join(fixture.bundle,'Contents/Resources/app.asar'),directory=path.join(fixture.root,'prior-asar');asar.extractAll(archive,directory);
 const packageFile=path.join(directory,'package.json'),pack=JSON.parse(await fs.readFile(packageFile));pack.version='0.1.2';await fs.writeFile(packageFile,JSON.stringify(pack,null,2)+'\n');
 await asar.createPackage(directory,archive);asar.uncacheAll();
 const plist=path.join(fixture.bundle,'Contents/Info.plist');
 for(const field of ['CFBundleShortVersionString','CFBundleVersion'])await run('/usr/libexec/PlistBuddy',['-c',`Set :${field} 0.1.2`,plist]);
 await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(archive).headerString).digest('hex')}`,plist]);
 await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),fixture.bundle]);
 await run('/usr/bin/codesign',['--verify','--deep','--strict',fixture.bundle]);await verifyResources(runtime,manifest.resources);
}
async function phase(phase,config){
 const configFile=path.join(fixture.root,phase+'.json'),driverResult=path.join(fixture.root,phase+'-driver.json');
 await fs.writeFile(configFile,JSON.stringify({...config,phase,driverResult,fail_first_open:phase==='rollback'}),{mode:0o600});
 const log=await fs.open(path.join(fixture.root,phase+'.log'),'w');
 const child=spawn(fixture.executable,[config.driver,configFile],{cwd:fixture.root,env:{HOME:fixture.home,TMPDIR:fixture.root,PATH:'/usr/bin:/bin',LANG:'en_US.UTF-8',ELECTRON_RUN_AS_NODE:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore',log.fd,log.fd]});
 const exit=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});await log.close();
 const driver=JSON.parse(await fs.readFile(driverResult));assert.equal(exit,0,JSON.stringify(driver));assert.equal(driver.authorized,true);assert.ok(driver.handoff?.resultPath);
 let outcome;for(let n=0;n<600;n++){try{outcome=JSON.parse(await fs.readFile(driver.handoff.resultPath));break;}catch{await delay(500);}}
 assert.ok(outcome,'Native helper result missing after exact current process exit');
 return {driver,outcome};
}
async function startup(version){
 const launched=await launch(fixture);application=launched.application;
 await launched.page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
 const health=await ownedControl(fixture,'health');assert.equal(health.application_version,version);
 await gracefulQuit(application,launched.page);application=null;
 return{application_version:health.application_version,owned_wsgi_ready:true,real_electron_started:true,isolated_home_and_profile:true,orderly_shutdown:true};
}
async function main(){
 fixture=await createFixture({reuse:false});
 const published=path.resolve(__dirname,'../dist/mac-arm64/Rieke OS.app'),zip=path.resolve(__dirname,'../dist/Rieke-OS-0.1.3-arm64.zip');
 const sourceManifest=await fs.readFile(path.join(published,'Contents/Resources/runtime/runtime-manifest.json'));
 assert.equal(JSON.parse(sourceManifest).application_version,'0.1.3');receipt.runtime_manifest_sha256=createHash('sha256').update(sourceManifest).digest('hex');
 receipt.asar_sha256=createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/app.asar'))).digest('hex');
 const descriptorBytes=await fs.readFile(path.resolve(__dirname,'../dist/desktop-release.json')),descriptor=JSON.parse(descriptorBytes);receipt.archive_sha256=descriptor.archive.sha256;
 await versionPrior();const priorDigest=await bundleDigest(fixture.bundle);receipt.prior_fixture_bundle_sha256=priorDigest;
 const tag='desktop-test-v0.1.3',baseURL=`https://github.com/maxwellsdm1867/Rieke-OS/releases/download/${tag}/`;
 const releases=Buffer.from(JSON.stringify([{draft:false,prerelease:true,tag_name:tag,assets:[{name:'desktop-release.json',size:descriptorBytes.length,browser_download_url:baseURL+'desktop-release.json'},{name:descriptor.archive.filename,size:descriptor.archive.size,browser_download_url:baseURL+descriptor.archive.filename}]}]));
 server=http.createServer((request,response)=>{
  const resource=request.url==='/api'?releases:request.url==='/descriptor'?descriptorBytes:null;
  if(resource){requests[request.url==='/api'?'api':'descriptor']++;response.writeHead(200,{'content-length':resource.length});response.end(resource);}
  else if(request.url==='/archive'){requests.archive++;response.writeHead(200,{'content-length':descriptor.archive.size});nativeFs.createReadStream(zip).pipe(response);}
  else{response.writeHead(404);response.end();}
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const driver=path.join(fixture.root,'driver.cjs'),wrapper=path.join(fixture.root,'owned-open-wrapper.cjs'),openLog=path.join(fixture.root,'open.jsonl');await fs.writeFile(driver,DRIVER);await fs.writeFile(wrapper,WRAPPER);
 const config={bundle:fixture.bundle,userData:fixture.userData,driver,wrapper,openLog,base:`http://127.0.0.1:${server.address().port}`,descriptorURL:baseURL+'desktop-release.json',archiveURL:baseURL+descriptor.archive.filename};
 await check('real ZIP updater validates and native helper waits current PID exit before complete 0.1.3 installation',async()=>{
  const {driver,outcome}=await phase('update',config);assert.equal(outcome.state,'Installed');assert.equal(outcome.version,'0.1.3');
  assert.equal(await bundleDigest(fixture.bundle),await bundleDigest(published));assert.equal(await bundleDigest(path.join(path.dirname(fixture.bundle),'.Rieke OS.previous.app')),priorDigest);
  return{current_process_ready_handshake:true,authorized_only_after_helper_ready:true,exact_current_process_exited:true,complete_target_matches_final_bundle:true,previous_complete_bundle_retained:true,statuses:driver.statuses};
 });
 await check('actual updated Electron and WSGI start in preserved isolated profile and stop cleanly',()=>startup('0.1.3'));
 await check('controlled Restore installs only verified retained prior bundle without archive download',async()=>{
  const before=requests.archive,{outcome}=await phase('restore',config);assert.equal(outcome.state,'Restored');assert.equal(outcome.version,'0.1.2');assert.equal(await bundleDigest(fixture.bundle),priorDigest);assert.equal(requests.archive,before);
  return{verified_previous_restored:true,archive_download_not_required:true,profile_preserved:true};
 });
 await check('macOS launch refusal triggers complete previous-app rollback with profile unchanged',async()=>{
  const {outcome}=await phase('rollback',config);assert.equal(outcome.state,'Restored');assert.equal(outcome.version,'0.1.2');assert.equal(await bundleDigest(fixture.bundle),priorDigest);
  return{candidate_launch_refusal_simulated_at_only_open_boundary:true,exact_previous_restored:true,failed_candidate_retained:true};
 });
 await check('restored Electron and WSGI still start and stop without dependency installation',()=>startup('0.1.2'));
 const opens=(await fs.readFile(openLog,'utf8')).trim().split('\n').map(line=>JSON.parse(line));
 assert.ok(opens.every(entry=>entry.args.includes(fixture.bundle)&&entry.args.includes(`--user-data-dir=${fixture.userData}`)));receipt.open_boundary_calls=opens.length;receipt.profile_continuity_verified=true;
 assert.equal(createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/runtime/runtime-manifest.json'))).digest('hex'),receipt.runtime_manifest_sha256);
 assert.equal(createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/app.asar'))).digest('hex'),receipt.asar_sha256);
 receipt.passed=true;await write();await new Promise(resolve=>server.close(resolve));server=null;await fs.rm(fixture.root,{recursive:true,force:true});console.log('Native testing upgrade receipt: '+output);
}
main().catch(async error=>{console.error(error.stack);receipt.failures.push({name:'native-testing-upgrade-suite',message:error.message});receipt.passed=false;await write();server?.close();if(fixture)console.error('Owned diagnostics retained: '+fixture.root);process.exitCode=1;});
