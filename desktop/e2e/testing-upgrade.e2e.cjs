'use strict';
// Real packaged updater/helper; only GitHub transport and macOS open are mapped
// to owned test boundaries. The source app, distribution and user app are read-only.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),nativeFs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{createHash}=require('node:crypto'),asar=require('@electron/asar');
const {createFixture,launch,gracefulQuit,ownedControl,run}=require('./helpers.cjs');
const {bundleDigest}=require('../bootstrap.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const {waitForHelperResult,captureHelperDiagnostics}=require('./helper-result.cjs');
const {releaseVersions}=require('./release-versions.cjs');
const output=path.resolve(__dirname,'../../docs/dev/desktop-testing-upgrade-e2e.json');
const diagnosticOutput=path.resolve(__dirname,'../build/native-qualification-diagnostics');
const receipt={format:'rieke-packaged-testing-native-upgrade-e2e',version:1,production_ready:false,checks:[],failures:[],
  seams:['Official GitHub HTTPS transport mapped to owned loopback server serving exact final ZIP/descriptor.',
         'Native helper macOS open boundary recorded instead of OS launch; installed app then starts with real Electron/WSGI in isolated HOME/profile.'],
  limits:['Synthetic version-only prior app, not an authentic previously published desktop release.','Unsigned local host only; no signed update or clean-machine qualification.'],user_app_untouched:true,phases:[]};
let fixture,server,application;const requests={api:0,descriptor:0,archive:0};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function write(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify({...receipt,requests},null,2)+'\n');}
async function check(name,fn){const start=Date.now();try{const evidence=await fn();receipt.checks.push({name,passed:true,elapsed_ms:Date.now()-start,evidence});console.log('PASS '+name);}catch(error){receipt.failures.push({name,message:error.message});await write();throw error;}await write();}
async function preservePhaseDiagnostics(phase,observed){
 await fs.mkdir(diagnosticOutput,{recursive:true,mode:0o700});observed.uploaded_diagnostics=[];
 const selected=new Set([`${phase}-helper-lifecycle.jsonl`,`${phase}-helper-stderr.txt`,`${phase}-driver-progress.json`,`${phase}-helper-long-wait.json`,`${phase}-helper-long-wait.sample.txt`,`${phase}-helper-timeout.json`,`${phase}-helper-timeout.sample.txt`]);
 for(const name of selected){
  const source=path.join(fixture.root,name);let stat;
  try{stat=await fs.lstat(source);}catch(error){if(error.code==='ENOENT')continue;throw error;}
  if(!stat.isFile()||stat.isSymbolicLink()||stat.uid!==process.getuid())throw new Error('Selected helper diagnostic is not an owned regular file');
  const handle=await fs.open(source,'r');let data;
  try{const bytes=Buffer.alloc(128*1024);const read=await handle.read(bytes,0,bytes.length,0);data=bytes.subarray(0,read.bytesRead);}finally{await handle.close();}
  const destination=path.join(diagnosticOutput,name);await fs.writeFile(destination,data,{mode:0o600});
  observed.uploaded_diagnostics.push({path:path.relative(path.resolve(__dirname,'../..'),destination),bytes:data.length,truncated:stat.size>data.length});
 }
}
const WRAPPER=String.raw`
'use strict';
const fs=require('node:fs'),path=require('node:path'),{promisify}=require('node:util');
const realRun=promisify(require('node:child_process').execFile);
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const helper=require(path.join(config.bundle,'Contents/Resources/app.asar/testing-install.cjs'));
fs.writeFileSync(config.helperLifecycle,JSON.stringify({phase:config.phase,pid:process.pid,event:'started',timestamp:new Date().toISOString()})+'\n',{mode:0o600});
process.on('exit',code=>fs.appendFileSync(config.helperLifecycle,JSON.stringify({phase:config.phase,pid:process.pid,event:'exit',code,timestamp:new Date().toISOString()})+'\n',{mode:0o600}));
let opens=0;
helper.applyTestingInstall({receiptPath:process.argv[3],run:async(exe,args,options)=>{
 if(exe!=='/usr/bin/open')return realRun(exe,args,options);
 opens++;fs.appendFileSync(config.openLog,JSON.stringify({phase:config.phase,args})+'\n',{mode:0o600});
 if(config.fail_first_open&&opens===1)throw new Error('Owned test simulates macOS refusing the candidate launch');
 return {stdout:'',stderr:''};
}}).catch(error=>{fs.writeFileSync(process.argv[3]+'.result.json',JSON.stringify({state:'Deferred',error_type:error.name,message:error.message}),{mode:0o600});process.exitCode=1;});
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
const progress=state=>{const temporary=config.driverProgress+'.tmp';fs.writeFileSync(temporary,JSON.stringify({phase:config.phase,state,timestamp:new Date().toISOString()}),{mode:0o600});fs.renameSync(temporary,config.driverProgress);};progress('Starting');
const app={isPackaged:true,getPath:name=>name==='exe'?process.execPath:config.userData,quit(){
 coordinator?.stop();setTimeout(()=>{fs.writeFileSync(config.driverResult,JSON.stringify({phase:config.phase,authorized,statuses,handoff}),{mode:0o600});process.exit(0);},50);
}};
const transport=url=>{
 const route=url==='https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1'?'/api':
 url===config.descriptorURL?'/descriptor':url===config.archiveURL?'/archive':null;
 if(!route)return Promise.reject(new Error('Unexpected official release URL'));
 return new Promise((resolve,reject)=>http.get(config.base+route,response=>resolve({statusCode:response.statusCode,headers:response.headers,body:response})).on('error',reject));
};
const spawnHelper=(exe,args,options)=>{
 const child=spawn(exe,[config.wrapper,process.argv[2],args[2]],options);let bytes=0;
 child.stderr.on('data',chunk=>{const keep=chunk.subarray(0,Math.max(0,65536-bytes));if(keep.length){fs.appendFileSync(config.helperStderr,keep,{mode:0o600});bytes+=keep.length;}});
 return child;
};
(async()=>{
 const authorizeQuit=()=>{authorized=true;};
 if(config.phase==='restore'){
  progress('PreparingRestore');
  handoff=await helper.restoreTestingPriorBundle({app,manifest,prepareQuit:async()=>({ready:true}),authorizeQuit,spawnHelper});
 }else{
  coordinator=createTestingUpdateCoordinator({app,manifest,distribution:require(path.join(packaged,'distribution.json')),transport,
   publishStatus:status=>{if(statuses.at(-1)!==status.state){statuses.push(status.state);progress(status.state);}},prepareQuit:async()=>({ready:true}),authorizeQuit,
   installHelper:async options=>{handoff=await helper.launchTestingInstall({...options,spawnHelper});return handoff;}});
  await coordinator.start();if(!['Available','Ready'].includes(coordinator.getStatus().state))throw new Error('Official fixture did not offer update');
  await coordinator.download();if(coordinator.getStatus().state!=='Ready')throw new Error('Real candidate validation did not become Ready');
  const result=await coordinator.installPrepared();if(!result.installing)throw new Error(result.reason||'Native install did not hand off');
 }
})().catch(error=>{coordinator?.stop();fs.writeFileSync(config.driverResult,JSON.stringify({error:error.message,statuses}),{mode:0o600});process.exitCode=1;});
`;
async function versionPrior(priorVersion){
 const runtime=path.join(fixture.bundle,'Contents/Resources/runtime'),file=path.join(runtime,'runtime-manifest.json');
 const manifest=JSON.parse(await fs.readFile(file));manifest.application_version=priorVersion;
 for(const name of Object.keys(manifest.resources).filter(name=>name.endsWith('/rieke-release.json'))){
  const target=path.join(runtime,name),release=JSON.parse(await fs.readFile(target));release.version=priorVersion;const data=Buffer.from(JSON.stringify(release,null,2)+'\n');await fs.writeFile(target,data);
  manifest.resources[name]={...manifest.resources[name],sha256:createHash('sha256').update(data).digest('hex'),size:data.length};
 }
 await fs.writeFile(file,JSON.stringify(manifest,null,2)+'\n');
 const archive=path.join(fixture.bundle,'Contents/Resources/app.asar'),directory=path.join(fixture.root,'prior-asar');asar.extractAll(archive,directory);
 const packageFile=path.join(directory,'package.json'),pack=JSON.parse(await fs.readFile(packageFile));pack.version=priorVersion;await fs.writeFile(packageFile,JSON.stringify(pack,null,2)+'\n');
 await asar.createPackage(directory,archive);asar.uncacheAll();
 const plist=path.join(fixture.bundle,'Contents/Info.plist');
 for(const field of ['CFBundleShortVersionString','CFBundleVersion'])await run('/usr/libexec/PlistBuddy',['-c',`Set :${field} ${priorVersion}`,plist]);
 await run('/usr/libexec/PlistBuddy',['-c',`Set :ElectronAsarIntegrity:Resources/app.asar:hash ${createHash('sha256').update(asar.getRawHeader(archive).headerString).digest('hex')}`,plist]);
 await run('/usr/bin/codesign',['--force','--sign','-','--entitlements',path.resolve(__dirname,'../entitlements.mac.plist'),fixture.bundle]);
 await run('/usr/bin/codesign',['--verify','--deep','--strict',fixture.bundle]);await verifyResources(runtime,manifest.resources);
}
async function phase(phase,config){
 const observed={phase,started_at:new Date().toISOString(),driver_started_at:new Date().toISOString(),helper_observations:[],diagnostics:[]};receipt.phases.push(observed);
 const configFile=path.join(fixture.root,phase+'.json'),driverResult=path.join(fixture.root,phase+'-driver.json');
 const driverProgress=path.join(fixture.root,phase+'-driver-progress.json'),helperLifecycle=path.join(fixture.root,phase+'-helper-lifecycle.jsonl'),helperStderr=path.join(fixture.root,phase+'-helper-stderr.txt');
 observed.diagnostic_paths={driver_progress:driverProgress,helper_lifecycle:helperLifecycle,helper_stderr:helperStderr};observed.driver_timeout_ms=15*60*1000;observed.helper_timeout_ms=15*60*1000;
 await fs.writeFile(configFile,JSON.stringify({...config,phase,driverResult,driverProgress,helperLifecycle,helperStderr,fail_first_open:phase==='rollback'}),{mode:0o600});
 const log=await fs.open(path.join(fixture.root,phase+'.log'),'w');
 const child=spawn(fixture.executable,[config.driver,configFile],{cwd:fixture.root,env:{HOME:fixture.home,TMPDIR:fixture.root,PATH:'/usr/bin:/bin',LANG:'en_US.UTF-8',ELECTRON_RUN_AS_NODE:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore',log.fd,log.fd]});
 const driverStarted=Date.now();let exit,error,heartbeatAt=driverStarted;
 child.once('error',value=>{error=value;});child.once('exit',(code,signal)=>{exit={code,signal};});observed.driver_pid=child.pid;
 try{
  while(!exit&&!error){await delay(500);if(Date.now()-driverStarted>=observed.driver_timeout_ms)throw new Error('Native qualification driver exceeded its bounded exit deadline; owned diagnostics retained');if(Date.now()-heartbeatAt>=60000){
   let progress;try{progress=JSON.parse(await fs.readFile(driverProgress,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
   if(progress&&(!/^[a-zA-Z]+$/.test(progress.state)||progress.phase!==phase))throw new Error('Native qualification driver progress is malformed');
   observed.driver_progress=progress||{phase,state:'Starting'};console.log(`::notice::Native ${phase} driver elapsed=${Math.floor((Date.now()-driverStarted)/1000)}s state=${observed.driver_progress.state}`);observed.driver_elapsed_ms=Date.now()-driverStarted;await write();heartbeatAt=Date.now();}}
  if(error)throw error;
  observed.driver_elapsed_ms=Date.now()-driverStarted;observed.driver_exit=exit;observed.driver_exited_at=new Date().toISOString();
  observed.driver_progress=JSON.parse(await fs.readFile(driverProgress,'utf8'));
  const driver=JSON.parse(await fs.readFile(driverResult));assert.equal(exit.code,0,JSON.stringify(driver));assert.equal(driver.authorized,true);assert.ok(driver.handoff?.resultPath);assert.ok(Number.isSafeInteger(driver.handoff.helperPid)&&driver.handoff.helperPid>0);
  observed.helper_pid=driver.handoff.helperPid;observed.helper_wait_started_at=new Date().toISOString();observed.driver_statuses=driver.statuses;await write();
  const waited=await waitForHelperResult({resultPath:driver.handoff.resultPath,helperPid:driver.handoff.helperPid,wrapper:config.wrapper,configFile,phase,
   onObservation:async value=>{observed.helper_observations.push(value);await write();},
   onHeartbeat:async value=>console.log(`::notice::Native ${phase} helper elapsed=${Math.floor(value.elapsed_ms/1000)}s state=${value.status}`),
   onDiagnostics:async value=>{observed.diagnostics.push(await captureHelperDiagnostics({helperPid:driver.handoff.helperPid,wrapper:config.wrapper,configFile,directory:fixture.root,phase,reason:value.reason}));await write();}});
  observed.helper_elapsed_ms=waited.elapsed_ms;observed.helper_outcome=waited.result.state;observed.completed_at=new Date().toISOString();await write();
  return {driver,outcome:waited.result};
 }catch(error){observed.failure={message:error.message,observation:error.observation||null};observed.failed_at=new Date().toISOString();await write();throw error;}
 finally{
  await log.close();
  try{await preservePhaseDiagnostics(phase,observed);}catch(error){observed.diagnostic_preservation_error=error.message;await write();throw error;}
  await write();
 }
}
async function startup(version){
 const launched=await launch(fixture);application=launched.application;
 await launched.page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:90000});
 const health=await ownedControl(fixture,'health');assert.equal(health.application_version,version);
 await gracefulQuit(application,launched.page);application=null;
 return{application_version:health.application_version,owned_wsgi_ready:true,real_electron_started:true,isolated_home_and_profile:true,orderly_shutdown:true};
}
async function main(){
 const harnessRoot=path.resolve(__dirname,'../..');
 receipt.qualification_harness_commit=(await run('/usr/bin/git',['rev-parse','HEAD'],{cwd:harnessRoot})).stdout.trim();
 receipt.qualification_harness_sha256=createHash('sha256').update(await fs.readFile(__filename)).digest('hex');
 receipt.qualification_helper_sha256=createHash('sha256').update(await fs.readFile(path.join(__dirname,'helper-result.cjs'))).digest('hex');
 await write();
 const published=path.resolve(__dirname,'../dist/mac-arm64/Rieke OS.app');
 const sourceManifest=await fs.readFile(path.join(published,'Contents/Resources/runtime/runtime-manifest.json'));
 const {candidateVersion,priorVersion}=releaseVersions(JSON.parse(sourceManifest).application_version,process.env.RIEKE_E2E_PRIOR_VERSION);
 assert.equal(JSON.parse(asar.extractFile(path.join(published,'Contents/Resources/app.asar'),'package.json')).version,candidateVersion,'Packaged version must match candidate manifest');
 const zip=path.resolve(__dirname,`../dist/Rieke-OS-${candidateVersion}-arm64.zip`);
 receipt.candidate_version=candidateVersion;receipt.synthetic_prior={version:priorVersion,authentic_published_release:false,construction:'Candidate clone with version metadata overlaid; documented launch and driver seams remain test-only'};
 receipt.runtime_manifest_sha256=createHash('sha256').update(sourceManifest).digest('hex');
 receipt.asar_sha256=createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/app.asar'))).digest('hex');
 const descriptorBytes=await fs.readFile(path.resolve(__dirname,'../dist/desktop-release.json')),descriptor=JSON.parse(descriptorBytes);receipt.archive_sha256=descriptor.archive.sha256;
 assert.equal(descriptor.application_version,candidateVersion);assert.equal(descriptor.archive.filename,path.basename(zip));
 fixture=await createFixture({reuse:false});
 receipt.fixture_root=fixture.root;receipt.diagnostic_directory=path.relative(harnessRoot,diagnosticOutput);await write();
 await versionPrior(priorVersion);const priorDigest=await bundleDigest(fixture.bundle);receipt.prior_fixture_bundle_sha256=priorDigest;
 const tag=`desktop-test-v${candidateVersion}`,baseURL=`https://github.com/maxwellsdm1867/Rieke-OS/releases/download/${tag}/`;
 const releases=Buffer.from(JSON.stringify([{draft:false,prerelease:true,tag_name:tag,assets:[{name:'desktop-release.json',size:descriptorBytes.length,browser_download_url:baseURL+'desktop-release.json'},{name:descriptor.archive.filename,size:descriptor.archive.size,browser_download_url:baseURL+descriptor.archive.filename}]}]));
 server=http.createServer((request,response)=>{
  const resource=request.url==='/api'?releases:request.url==='/descriptor'?descriptorBytes:null;
  if(resource){requests[request.url==='/api'?'api':'descriptor']++;response.writeHead(200,{'content-length':resource.length});response.end(resource);}
  else if(request.url==='/archive'){requests.archive++;response.writeHead(200,{'content-length':descriptor.archive.size});nativeFs.createReadStream(zip).pipe(response);}
  else{response.writeHead(404);response.end();}
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const driver=path.join(fixture.root,'driver.cjs'),wrapper=path.join(fixture.root,'owned-open-wrapper.cjs'),openLog=path.join(fixture.root,'open.jsonl');await fs.writeFile(driver,DRIVER);await fs.writeFile(wrapper,WRAPPER);
 const config={bundle:fixture.bundle,userData:fixture.userData,driver,wrapper,openLog,base:`http://127.0.0.1:${server.address().port}`,descriptorURL:baseURL+'desktop-release.json',archiveURL:baseURL+descriptor.archive.filename};
 await check(`real ZIP updater validates and native helper waits current PID exit before complete ${candidateVersion} installation`,async()=>{
  const {driver,outcome}=await phase('update',config);assert.equal(outcome.state,'Installed');assert.equal(outcome.version,candidateVersion);
  assert.equal(await bundleDigest(fixture.bundle),await bundleDigest(published));assert.equal(await bundleDigest(path.join(path.dirname(fixture.bundle),'.Rieke OS.previous.app')),priorDigest);
  return{current_process_ready_handshake:true,authorized_only_after_helper_ready:true,exact_current_process_exited:true,complete_target_matches_final_bundle:true,previous_complete_bundle_retained:true,statuses:driver.statuses};
 });
 await check('actual updated Electron and WSGI start in preserved isolated profile and stop cleanly',()=>startup(candidateVersion));
 await check('controlled Restore installs only verified retained prior bundle without archive download',async()=>{
  const before=requests.archive,{outcome}=await phase('restore',config);assert.equal(outcome.state,'Restored');assert.equal(outcome.version,priorVersion);assert.equal(await bundleDigest(fixture.bundle),priorDigest);assert.equal(requests.archive,before);
  return{verified_previous_restored:true,archive_download_not_required:true,profile_preserved:true};
 });
 await check('macOS launch refusal triggers complete previous-app rollback with profile unchanged',async()=>{
  const {outcome}=await phase('rollback',config);assert.equal(outcome.state,'Restored');assert.equal(outcome.version,priorVersion);assert.equal(await bundleDigest(fixture.bundle),priorDigest);
  return{candidate_launch_refusal_simulated_at_only_open_boundary:true,exact_previous_restored:true,failed_candidate_retained:true};
 });
 await check('restored Electron and WSGI still start and stop without dependency installation',()=>startup(priorVersion));
 const opens=(await fs.readFile(openLog,'utf8')).trim().split('\n').map(line=>JSON.parse(line));
 assert.ok(opens.every(entry=>entry.args.includes(fixture.bundle)&&entry.args.includes(`--user-data-dir=${fixture.userData}`)));receipt.open_boundary_calls=opens.length;receipt.profile_continuity_verified=true;
 assert.equal(createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/runtime/runtime-manifest.json'))).digest('hex'),receipt.runtime_manifest_sha256);
 assert.equal(createHash('sha256').update(await fs.readFile(path.join(published,'Contents/Resources/app.asar'))).digest('hex'),receipt.asar_sha256);
 receipt.passed=true;await write();await new Promise(resolve=>server.close(resolve));server=null;await fs.rm(fixture.root,{recursive:true,force:true});console.log('Native testing upgrade receipt: '+output);
}
main().catch(async error=>{console.error(error.stack);receipt.failures.push({name:'native-testing-upgrade-suite',message:error.message});receipt.passed=false;await write();server?.close();if(fixture)console.error('Owned diagnostics retained: '+fixture.root);process.exitCode=1;});
