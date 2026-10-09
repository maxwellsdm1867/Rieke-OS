'use strict';
// Explicit unsigned-testing distribution only. Integrity is checked locally;
// macOS quarantine and Gatekeeper decisions are left intact.
const fs=require('./physical-fs.cjs').promises;
const path=require('node:path');
const os=require('node:os');
const {promisify}=require('node:util');
const {execFile,spawn}=require('node:child_process');
const {createHash,randomUUID}=require('node:crypto');
const runFile=promisify(execFile);
const {APP_ID,enclosingApp,bundleDigest,installCompleteBundle,compatibleManifest,assertNotRunning,verifyTestingBundle}=require('./bootstrap.cjs');
const {compareVersions,stableVersion,verifyResources}=require('./updater-validation.cjs');
const READY='RIEKE_TESTING_INSTALL_READY=';
function failureDetails(error){
 const bounded=value=>String(value||'').replace(/[\x00-\x08\x0b-\x1f\x7f]/g,'').slice(0,4096);
 return {error:bounded(error.message)||'Testing update could not complete.',error_type:bounded(error.name),
  activation_failure:error.activationFailure||null,previous_path:error.previousPath||null,failed_candidate_path:error.failedCandidatePath||null,phases:error.updatePhases||[],phase:bounded(error.updatePhase)||'unknown',code:bounded(error.code)||null,stderr:bounded(error.stderr)||null};
}

async function sha256(file){
 const digest=createHash('sha256'),handle=await fs.open(file,'r');
 try{for await(const chunk of handle.createReadStream())digest.update(chunk);}finally{await handle.close();}
 return digest.digest('hex');
}
async function privateReceipt(receiptPath,{previous=false}={}){
 const info=await fs.lstat(receiptPath);
 if(!info.isFile()||info.isSymbolicLink()||info.uid!==process.getuid()||(info.mode&0o077)||info.size>65536)throw new Error('Update receipt must be a private current-user-owned regular file');
 const parent=await fs.lstat(path.dirname(receiptPath));
 if(!parent.isDirectory()||parent.isSymbolicLink()||parent.uid!==process.getuid())throw new Error('Update receipt directory must be current-user owned');
 const value=JSON.parse(await fs.readFile(receiptPath,'utf8'));
 if(value.format!==(previous?'rieke-unsigned-testing-previous':'rieke-unsigned-testing-update')||value.version!==1||value.channel!=='unsigned-testing'||value.identifier!==APP_ID||(!previous&&value.validated!==true))throw new Error('Unsigned testing update receipt is invalid');
 return value;
}
async function processCreationIdentity(pid,currentExecutable,run=runFile){
 if(!Number.isSafeInteger(pid)||pid<=0)throw new Error('Current app process identity is invalid');
 const bundle=enclosingApp(currentExecutable);
 if(!bundle)throw new Error('Current app executable must be an installed complete bundle');
 const python=path.join(bundle,'Contents/Resources/runtime/python/bin/python3.11');
 const code='import json,os,psutil,sys\ntry:\n p=psutil.Process(int(sys.argv[1])); value={"pid":p.pid,"created_at":p.create_time(),"executable":os.path.realpath(p.exe()),"alive":p.status()!=psutil.STATUS_ZOMBIE}\nexcept psutil.NoSuchProcess: value={"pid":int(sys.argv[1]),"alive":False}\nprint("RIEKE_PROCESS_IDENTITY="+json.dumps(value))';
 const result=await run(python,['-I','-B','-c',code,String(pid)],{timeout:15000,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONNOUSERSITE:'1'}});
 const line=result.stdout.split('\n').find(value=>value.startsWith('RIEKE_PROCESS_IDENTITY='));
 if(!line)throw new Error('Current app process identity is unavailable');
 const identity=JSON.parse(line.slice('RIEKE_PROCESS_IDENTITY='.length));
 if(identity.pid!==pid||typeof identity.alive!=='boolean'||(identity.alive&&(!Number.isFinite(identity.created_at)||typeof identity.executable!=='string')))throw new Error('Current app process identity is invalid');
 return identity;
}
async function ownedCachePath(file,cache,{directory=false}={}){
 const info=await fs.lstat(file),physical=await fs.realpath(file);
 if(info.uid!==process.getuid()||info.isSymbolicLink()||!(directory?info.isDirectory():info.isFile())||!physical.startsWith(cache+path.sep))throw new Error('Prepared update must remain in its owned receipt cache');
 return physical;
}
async function atomicPrivateJSON(file,value){
 const temporary=file+'.'+randomUUID();
 const handle=await fs.open(temporary,'wx',0o600);
 try{await handle.writeFile(JSON.stringify(value,null,2)+'\n');await handle.sync();}finally{await handle.close();}
 try{await fs.rename(temporary,file);const directory=await fs.open(path.dirname(file),'r');try{await directory.sync();}finally{await directory.close();}}
 finally{await fs.rm(temporary,{force:true});}
}
async function validatePrepared({receiptPath,currentExecutable,run=runFile,requireParent=true,retainCurrentDigest=false}){
 const receipt=await privateReceipt(receiptPath);
 const restoring=receipt.operation==='restore';
 if(receipt.operation!==undefined&&!['update','restore'].includes(receipt.operation))throw new Error('Unsigned testing operation is invalid');
 const executable=await fs.realpath(currentExecutable),installed=enclosingApp(executable);
 if(!installed||await fs.realpath(receipt.install_path)!==installed||await fs.realpath(receipt.current_executable)!==executable||!Number.isSafeInteger(receipt.current_pid)||receipt.current_pid<=0||!Number.isFinite(receipt.current_created_at))throw new Error('Update does not belong to this exact installed app');
 for(const field of [...(restoring?[]:['archive_sha256']),'bundle_sha256','runtime_manifest_sha256','current_manifest_sha256'])if(!/^[a-f0-9]{64}$/.test(receipt[field]||''))throw new Error('Update receipt checksum is invalid');
 const cache=await fs.realpath(path.dirname(receiptPath));
 if(path.basename(cache)!=='unsigned-testing'||path.basename(path.dirname(cache))!=='updates')throw new Error('Update cache does not belong to the current application profile');
 const userData=path.dirname(path.dirname(cache)),profile=await fs.lstat(userData);
 if(profile.isSymbolicLink()||!profile.isDirectory()||profile.uid!==process.getuid())throw new Error('Current application profile ownership differs');
 let bundle;
 if(restoring){
  const prior=await privateReceipt(path.join(cache,'previous.json'),{previous:true});
  const expected=path.join(path.dirname(installed),'.Rieke OS.previous.app');
  const info=await fs.lstat(expected);
  if(info.isSymbolicLink()||!info.isDirectory()||info.uid!==process.getuid()||await fs.realpath(receipt.bundle_path)!==expected||prior.previous_path!==expected||prior.install_path!==installed||prior.current_version!==receipt.current_version||prior.previous_version!==receipt.target_version||prior.previous_bundle_sha256!==receipt.bundle_sha256||prior.previous_manifest_sha256!==receipt.runtime_manifest_sha256)throw new Error('Restore does not identify the retained verified previous app');
  bundle=expected;
 }else{
  const archive=await ownedCachePath(receipt.archive_path,cache);
  bundle=await ownedCachePath(receipt.bundle_path,cache,{directory:true});
  if(await sha256(archive)!==receipt.archive_sha256)throw new Error('Prepared update archive or bundle checksum differs');
 }
 const manifestPath=path.join(bundle,'Contents/Resources/runtime/runtime-manifest.json');
 const currentPath=path.join(installed,'Contents/Resources/runtime/runtime-manifest.json');
 const candidateBytes=await fs.readFile(manifestPath),currentBytes=await fs.readFile(currentPath);
 if(createHash('sha256').update(candidateBytes).digest('hex')!==receipt.runtime_manifest_sha256||createHash('sha256').update(currentBytes).digest('hex')!==receipt.current_manifest_sha256)throw new Error('Prepared update or installed runtime manifest differs');
 const current=JSON.parse(currentBytes.toString('utf8')),candidate=JSON.parse(candidateBytes.toString('utf8'));
 if(await bundleDigest(bundle,{runtimeManifest:candidate,runtimeManifestSha256:receipt.runtime_manifest_sha256})!==receipt.bundle_sha256)throw new Error('Prepared update archive or bundle checksum differs');
 stableVersion(receipt.target_version);
 if(current.application_version!==receipt.current_version||candidate.application_version!==receipt.target_version||(!restoring&&compareVersions(receipt.target_version,receipt.current_version)<=0)||!compatibleManifest(candidate,current))throw new Error('Unsigned update version or data compatibility differs');
 let currentDigest=null;
 if(retainCurrentDigest)currentDigest=await bundleDigest(installed,{runtimeManifest:current,runtimeManifestSha256:receipt.current_manifest_sha256});
 else await verifyResources(path.join(installed,'Contents/Resources/runtime'),current.resources);
 await verifyTestingBundle(bundle,run);
 await require('./install-name.cjs').assertBundleDestination(bundle,installed,run);
 if(requireParent){
  const identity=await processCreationIdentity(receipt.current_pid,executable,run);
  if(!identity.alive||identity.created_at!==receipt.current_created_at||await fs.realpath(identity.executable)!==executable)throw new Error('Current app process ownership changed');
 }
 return {receipt,installed,executable,bundle,cache,current,candidate,userData,currentDigest};
}
async function applyTestingInstall({receiptPath,currentExecutable=process.execPath,run=runFile,publishReady=packet=>process.stdout.write(READY+JSON.stringify(packet)+'\n'),timeoutMs=90000,pollMs=200}){
 const started=Date.now(),phases=[];
 async function stage(name,action){
  const start=Date.now();
  try{return await action();}catch(error){error.updatePhase ||= name;error.updatePhases=phases;throw error;}
  finally{phases.push({phase:name,elapsed_ms:Date.now()-start});}
 }
 const prepared=await stage('validate-prepared',()=>validatePrepared({receiptPath,currentExecutable,run}));
 const {receipt,installed,executable,bundle,cache,current,userData}=prepared;
 const openArguments=['-n','-a',installed,'--env','HOME='+os.homedir(),'--args','--user-data-dir='+userData];
 publishReady({pid:process.pid,current_pid:receipt.current_pid,version:receipt.target_version,archive_sha256:receipt.archive_sha256});
 await stage('wait-parent-exit',async()=>{
 const deadline=Date.now()+timeoutMs;
 for(;;){
  const identity=await processCreationIdentity(receipt.current_pid,executable,run);
  if(!identity.alive)break;
  if(identity.created_at!==receipt.current_created_at||await fs.realpath(identity.executable)!==executable)throw new Error('Current app process ownership changed while waiting for exit');
  if(Date.now()>=deadline)throw new Error('Current app exit was not acknowledged; installation deferred');
  await new Promise(resolve=>setTimeout(resolve,pollMs));
 }
 });
 // Cached data is checked again after actual exit, before touching installation.
 const afterExit=await stage('validate-after-exit',()=>validatePrepared({receiptPath,currentExecutable,run,requireParent:false,retainCurrentDigest:true}));
 const priorDigest=afterExit.currentDigest;
 const result=await stage('replace-bundle',()=>installCompleteBundle({source:bundle,destination:installed,distribution:{channel:'unsigned-testing'},expectedBundleSha256:receipt.bundle_sha256,run,allowRollback:true,ignorePid:process.pid}));
 try{
 await stage('save-rollback-receipt',()=>atomicPrivateJSON(path.join(cache,'previous.json'),{format:'rieke-unsigned-testing-previous',version:1,channel:'unsigned-testing',identifier:APP_ID,
  install_path:installed,previous_path:result.previous,previous_version:current.application_version,previous_bundle_sha256:priorDigest,
  previous_manifest_sha256:receipt.current_manifest_sha256,current_version:receipt.target_version}));
 await stage('request-launch',()=>run('/usr/bin/open',openArguments));
 }
 catch(error){
  const activationFailure={phase:error.updatePhase,error:error.message};
  let priorRestored=false,failed=null;
  // Receipt persistence and launch are both part of activation. Preserve attributes and return to
  // the verified previous app; never clear quarantine or suppress OS approval.
  try{
  if(!result.previous||await bundleDigest(result.previous)!==priorDigest)throw error;
  await assertNotRunning(installed,run,process.pid);
  failed=path.join(cache,'failed-candidate-'+randomUUID()+'.app');
  await fs.rename(installed,failed);
  try{await fs.rename(result.previous,installed);priorRestored=true;}catch(rollbackError){await fs.rename(failed,installed);throw rollbackError;}
  if(await bundleDigest(installed)!==priorDigest)throw new Error('Restored previous application checksum differs');
  await fs.rm(path.join(cache,'previous.json'),{force:true});
  await run('/usr/bin/open',openArguments);
  const outcome={state:'Restored',destination:installed,version:current.application_version,failedCandidateRetained:true,failure:failureDetails(error),phases,elapsed_ms:Date.now()-started};
  await atomicPrivateJSON(receiptPath+'.result.json',outcome);return outcome;
  }catch(recoveryError){recoveryError.updatePhase='restore-previous';recoveryError.activationFailure=activationFailure;recoveryError.previousPath=priorRestored?installed:result.previous;recoveryError.failedCandidatePath=priorRestored?failed:null;throw recoveryError;}
 }
 const outcome={state:receipt.operation==='restore'?'Restored':'Installed',destination:installed,previous:result.previous,version:receipt.target_version,launch_requested:true,phases,elapsed_ms:Date.now()-started};
 await atomicPrivateJSON(receiptPath+'.result.json',outcome);
 return outcome;
}
async function privateReceiptResult(file){
 const stat=await fs.lstat(file);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.uid!==process.getuid()||(stat.mode&0o077)||stat.size>65536)throw new Error('Invalid helper result');
 return JSON.parse(await fs.readFile(file,'utf8'));
}
async function launchTestingInstall({receiptPath,currentExecutable=process.execPath,currentPid=process.pid,run=runFile,spawnHelper=spawn,readyTimeoutMs=150000}){
 const prepared=await validatePrepared({receiptPath,currentExecutable,run});
 if(prepared.receipt.current_pid!==currentPid||!path.resolve(__filename).startsWith(prepared.installed+path.sep))throw new Error('Install helper must originate from this exact current app');
 const script=path.join(__dirname,'testing-install.cjs');
 const resultPath=receiptPath+'.result.json';
 try{await privateReceiptResult(resultPath);await fs.rm(resultPath);}catch(error){if(error.code!=='ENOENT')throw error;}
 const child=spawnHelper(prepared.executable,[script,'--apply',receiptPath],{detached:true,stdio:['ignore','pipe','pipe'],cwd:prepared.cache,
  env:{HOME:process.env.HOME,TMPDIR:process.env.TMPDIR,LANG:process.env.LANG||'en_US.UTF-8',PATH:'/usr/bin:/bin',ELECTRON_RUN_AS_NODE:'1'}});
 await new Promise((resolve,reject)=>{
  let buffer='',done=false;
  const timer=setTimeout(()=>finish(new Error('Install helper readiness was not acknowledged; current app stays open')),readyTimeoutMs);
  const finish=error=>{if(done)return;done=true;clearTimeout(timer);if(error)reject(error);else resolve();};
  child.once('error',finish);child.once('exit',async()=>{
   let detail;
   try{detail=await privateReceiptResult(resultPath);}catch{}
   finish(new Error(detail?.error ? `Install helper failed (${detail.phase||'unknown'}): ${detail.error}` : 'Install helper exited before readiness acknowledgement'));
  });
  child.stderr?.on('data',()=>{});
  child.stdout.on('data',chunk=>{
   buffer+=chunk.toString('utf8');if(buffer.length>65536)return finish(new Error('Install helper readiness packet exceeded bounds'));
   let end;
   while((end=buffer.indexOf('\n'))>=0){
    const line=buffer.slice(0,end);buffer=buffer.slice(end+1);
    if(!line.startsWith(READY))continue;
    try{const packet=JSON.parse(line.slice(READY.length));
     if(packet.pid!==child.pid||packet.current_pid!==currentPid||packet.version!==prepared.receipt.target_version||packet.archive_sha256!==prepared.receipt.archive_sha256)throw new Error('Install helper readiness identity differs');
     finish();
    }catch(error){finish(error);}
   }
  });
 });
 child.stdout.unref?.();child.stderr.unref?.();child.unref();
 return {ready:true,helperPid:child.pid,resultPath};
}
async function restoreTestingPriorBundle({app,manifest,prepareQuit,authorizeQuit,run=runFile,spawnHelper=spawn}){
 if(!app?.isPackaged)throw new Error('Restore requires the installed unsigned testing application');
 const executable=await fs.realpath(app.getPath('exe')),installed=enclosingApp(executable);
 const cache=path.join(app.getPath('userData'),'updates','unsigned-testing');
 const prior=await privateReceipt(path.join(cache,'previous.json'),{previous:true});
 const currentPath=path.join(installed,'Contents/Resources/runtime/runtime-manifest.json');
 if(prior.install_path!==installed||prior.current_version!==manifest.application_version)throw new Error('Retained previous app does not belong to this installed version');
 const identity=await processCreationIdentity(process.pid,executable,run);
 if(!identity.alive||await fs.realpath(identity.executable)!==executable)throw new Error('Current app process identity differs');
 const receiptPath=path.join(cache,'restore-'+randomUUID()+'.json');
 await atomicPrivateJSON(receiptPath,{format:'rieke-unsigned-testing-update',version:1,channel:'unsigned-testing',identifier:APP_ID,validated:true,operation:'restore',
  install_path:installed,current_executable:executable,current_pid:process.pid,current_created_at:identity.created_at,
  current_version:manifest.application_version,target_version:prior.previous_version,current_manifest_sha256:await sha256(currentPath),
  runtime_manifest_sha256:prior.previous_manifest_sha256,bundle_path:prior.previous_path,bundle_sha256:prior.previous_bundle_sha256,archive_path:null,archive_sha256:null});
 await validatePrepared({receiptPath,currentExecutable:executable,run});
 const result=await prepareQuit();if(result?.ready!==true)return result;
 const prepared=await launchTestingInstall({receiptPath,currentExecutable:executable,currentPid:process.pid,run,spawnHelper});
 authorizeQuit();app.quit();return {...prepared,restoring:true};
}
async function main(){
 if(process.env.ELECTRON_RUN_AS_NODE!=='1'||process.argv[2]!=='--apply'||process.argv.length!==4)throw new Error('Install helper invocation is invalid');
 const receiptPath=process.argv[3];
 try{await applyTestingInstall({receiptPath});}
 catch(error){
  try{await privateReceipt(receiptPath);await atomicPrivateJSON(receiptPath+'.result.json',{state:'Deferred',...failureDetails(error)});}catch{}
  process.exitCode=1;
 }
}
if(require.main===module)main().catch(()=>{process.exitCode=1;});
module.exports={processCreationIdentity,applyTestingInstall,launchTestingInstall,restoreTestingPriorBundle,sha256,bundleDigest};
