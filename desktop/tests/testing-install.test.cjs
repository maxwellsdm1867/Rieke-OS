'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {promisify}=require('node:util');
const execFile=promisify(require('node:child_process').execFile);
const {installCompleteBundle}=require('../bootstrap.cjs');
async function fixture(version='0.1.0') {
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-install-policy-'));
 const source=path.join(root,'Downloads','Rieke OS.app');
 const runtime=path.join(source,'Contents/Resources/runtime');
 await fs.mkdir(runtime,{recursive:true});await fs.mkdir(path.join(source,'Contents/MacOS'),{recursive:true});
 await fs.writeFile(path.join(source,'Contents/MacOS/Rieke OS'),'native executable fixture',{mode:0o755});
 await fs.writeFile(path.join(source,'Contents/Info.plist'),`<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>org.riekeos.desktop</string><key>CFBundleExecutable</key><string>Rieke OS</string><key>CFBundleShortVersionString</key><string>${version}</string><key>LSMinimumSystemVersion</key><string>14.0</string></dict></plist>`);
 const resources={};
 for(const name of ['python/bin/python3.11','mysql/bin/mysqld','mysql/bin/mysql','mysql/bin/mysqldump','application/python/workspace_desktop.py']){
  const file=path.join(runtime,name);await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,'immutable fixture',{mode:0o755});
  resources[name]={sha256:'79c3ce98db9b18e2c5fb3b1e74909c744e4f7b79a6c9ab5e6a0c538b0115cc50',size:17,executable:true};
  resources[name].sha256=crypto.createHash('sha256').update('immutable fixture').digest('hex');
 }
 const manifest={format:'rieke-desktop-runtime',version:1,application_version:version,source_commit:'a'.repeat(40),parser_commit:'b'.repeat(40),source_dirty:false,platform:'darwin',architecture:'arm64',minimum_macos_version:'14.0',mysql_version:'8.4.2',python_version:'3.11.13',workspace_formats:[1],database_compatibility:1,resources};
 await fs.writeFile(path.join(runtime,'runtime-manifest.json'),JSON.stringify(manifest));
 const destination=path.join(root,'Applications','Rieke OS.app');
 const commands=[];
 async function run(command,args,options){
  commands.push([command,...args]);
  if(command==='/usr/bin/codesign'&&args.includes('--verify'))return {stdout:'',stderr:''};
  if(command==='/usr/bin/codesign'||command==='/usr/sbin/spctl')throw new Error('Unsigned fixture is not Developer ID approved');
  if(command==='/bin/ps')return {stdout:'',stderr:''};
  if(command==='/usr/bin/ditto'){await fs.cp(args.at(-2),args.at(-1),{recursive:true,dereference:false});return {stdout:'',stderr:''};}
  return execFile(command,args,options);
 }
 return {root,source,destination,run,commands,manifest};
}
test('explicit unsigned testing Install and Open copies the whole verified app while signed defaults reject it',async()=>{
 const f=await fixture();try{
  await assert.rejects(installCompleteBundle(f),/Unsigned fixture/);
  const result=await installCompleteBundle({...f,distribution:{channel:'unsigned-testing'}});
  assert.equal(result.destination,f.destination);
  assert.equal(await fs.readFile(path.join(f.destination,'Contents/MacOS/Rieke OS'),'utf8'),'native executable fixture');
  assert.equal(await fs.readFile(path.join(f.destination,'Contents/Resources/runtime/mysql/bin/mysqld'),'utf8'),'immutable fixture');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
module.exports={fixture};
test('native unsigned update helper rejects an exposed receipt before changing the installed app',async()=>{
 const {applyTestingInstall}=require('../testing-install.cjs');
 const f=await fixture();try{
  await installCompleteBundle({...f,distribution:{channel:'unsigned-testing'}});
  const receiptPath=path.join(f.root,'update.json');await fs.writeFile(receiptPath,'{}',{mode:0o644});
  await assert.rejects(applyTestingInstall({receiptPath,currentExecutable:path.join(f.destination,'Contents/MacOS/Rieke OS'),run:f.run}),/receipt.*private/i);
  assert.equal(await fs.readFile(path.join(f.destination,'Contents/MacOS/Rieke OS'),'utf8'),'native executable fixture');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
async function updateFixture(){
 const f=await fixture('0.1.0'),fresh=await fixture('0.1.1');
 await installCompleteBundle({...f,distribution:{channel:'unsigned-testing'}});
 const cache=path.join(f.root,'updates','unsigned-testing');await fs.mkdir(cache,{recursive:true,mode:0o700});
 const candidate=path.join(cache,'Rieke OS.app');await fs.rename(fresh.source,candidate);
 await fs.rm(fresh.root,{recursive:true,force:true});
 const archive=path.join(cache,'candidate.zip');await fs.writeFile(archive,'validated ZIP transport fixture',{mode:0o600});
 const {bundleDigest}=require('../bootstrap.cjs'),{sha256}=require('../testing-install.cjs');
 const currentExecutable=path.join(f.destination,'Contents/MacOS/Rieke OS');
 const receipt={format:'rieke-unsigned-testing-update',version:1,channel:'unsigned-testing',identifier:'org.riekeos.desktop',validated:true,
  install_path:f.destination,current_executable:currentExecutable,current_pid:12345,current_created_at:17,current_version:'0.1.0',target_version:'0.1.1',
  current_manifest_sha256:await sha256(path.join(f.destination,'Contents/Resources/runtime/runtime-manifest.json')),
  runtime_manifest_sha256:await sha256(path.join(candidate,'Contents/Resources/runtime/runtime-manifest.json')),
  archive_path:archive,archive_sha256:await sha256(archive),bundle_path:candidate,bundle_sha256:await bundleDigest(candidate)};
 const receiptPath=path.join(cache,'install.json');await fs.writeFile(receiptPath,JSON.stringify(receipt),{mode:0o600});
 return {...f,receipt,receiptPath,currentExecutable,cache};
}
test('native unsigned update acknowledges readiness, waits exact current exit, installs compatible complete bundle and retains previous',async()=>{
 const {applyTestingInstall}=require('../testing-install.cjs'),{readBundleManifest}=require('../bootstrap.cjs');
 const f=await updateFixture();let ready=false,exited=false,identityReads=0;
 try{
  const run=async(command,args,options)=>{
   if(command.endsWith('/python/bin/python3.11')){
    identityReads++;exited=identityReads>1;
    return {stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify(exited?{pid:12345,alive:false}:{pid:12345,alive:true,created_at:17,executable:f.currentExecutable})+'\n'};
   }
   if(command==='/usr/bin/open'){assert.equal(exited,true);assert.equal((await readBundleManifest(f.destination)).application_version,'0.1.1');return {stdout:''};}
   if(command==='/usr/bin/ditto')assert.equal(ready&&exited,true,'No replacement before parent acknowledgement and exit');
   return f.run(command,args,options);
  };
  const result=await applyTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,run,publishReady:()=>{ready=true;}});
  assert.equal(result.state,'Installed');assert.equal((await readBundleManifest(result.previous)).application_version,'0.1.0');
  assert.equal((await readBundleManifest(f.destination)).application_version,'0.1.1');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('failed native launch restores the previous complete app and requests its normal macOS launch',async()=>{
 const {applyTestingInstall}=require('../testing-install.cjs'),{readBundleManifest}=require('../bootstrap.cjs');
 const f=await updateFixture();let identities=0,opens=0;
 try{
  const run=async(command,args,options)=>{
   if(command.endsWith('/python/bin/python3.11'))return {stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify(++identities===1?{pid:12345,alive:true,created_at:17,executable:f.currentExecutable}:{pid:12345,alive:false})+'\n'};
   if(command==='/usr/bin/open'){if(++opens===1)throw new Error('LaunchServices refused candidate');assert.equal((await readBundleManifest(f.destination)).application_version,'0.1.0');return {stdout:''};}
   return f.run(command,args,options);
  };
  const result=await applyTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,run,publishReady:()=>{}});
  assert.equal(result.state,'Restored');assert.equal(opens,2);assert.equal((await readBundleManifest(f.destination)).application_version,'0.1.0');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('controlled restore installs only the retained verified previous bundle and leaves update archive unnecessary',async()=>{
 const {applyTestingInstall,sha256}=require('../testing-install.cjs'),{readBundleManifest,bundleDigest}=require('../bootstrap.cjs');
 const f=await updateFixture();let identities=0;
 try{
  const run=async(command,args,options)=>{
   if(command.endsWith('/python/bin/python3.11'))return {stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify(++identities===1?{pid:12345,alive:true,created_at:17,executable:f.currentExecutable}:{pid:12345,alive:false})+'\n'};
   if(command==='/usr/bin/open')return {stdout:''};
   return f.run(command,args,options);
  };
  const installed=await applyTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,run,publishReady:()=>{}});
  const prior=JSON.parse(await fs.readFile(path.join(f.cache,'previous.json'),'utf8'));
  const restore={...f.receipt,operation:'restore',current_version:'0.1.1',target_version:'0.1.0',bundle_path:installed.previous,
   bundle_sha256:await bundleDigest(installed.previous),current_manifest_sha256:await sha256(path.join(f.destination,'Contents/Resources/runtime/runtime-manifest.json')),
   runtime_manifest_sha256:f.receipt.current_manifest_sha256,archive_path:null,archive_sha256:null};
  const restorePath=path.join(f.cache,'restore.json');await fs.writeFile(restorePath,JSON.stringify(restore),{mode:0o600});identities=0;
  await fs.rm(f.receipt.archive_path);
  const result=await applyTestingInstall({receiptPath:restorePath,currentExecutable:f.currentExecutable,run,publishReady:()=>{}});
  assert.equal(result.state,'Restored');assert.equal((await readBundleManifest(f.destination)).application_version,'0.1.0');
  assert.equal(prior.previous_version,'0.1.0');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('Restore Previous defers a busy scientific session without launching helper or authorizing quit',async()=>{
 const {applyTestingInstall,restoreTestingPriorBundle}=require('../testing-install.cjs'),{readBundleManifest}=require('../bootstrap.cjs');
 const f=await updateFixture();let identities=0;
 try{
  const run=async(command,args,options)=>{
   if(command.endsWith('/python/bin/python3.11'))return {stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify(++identities===1?{pid:12345,alive:true,created_at:17,executable:f.currentExecutable}:{pid:12345,alive:false})+'\n'};
   if(command==='/usr/bin/open')return {stdout:''};return f.run(command,args,options);
  };
  await applyTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,run,publishReady:()=>{}});
  const result=await restoreTestingPriorBundle({app:{isPackaged:true,getPath:name=>name==='exe'?f.currentExecutable:f.root},manifest:await readBundleManifest(f.destination),
   prepareQuit:async()=>({ready:false,busy:true}),authorizeQuit:()=>assert.fail('Busy session cannot quit'),spawnHelper:()=>assert.fail('Busy session cannot spawn helper'),
   run:async(command,args,options)=>command.endsWith('/python/bin/python3.11')?{stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify({pid:Number(args.at(-1)),alive:true,created_at:17,executable:f.currentExecutable})+'\n'}:f.run(command,args,options)});
  assert.equal(result.busy,true);assert.equal((await readBundleManifest(f.destination)).application_version,'0.1.1');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('testing policy never replaces an app with any live installed process',async()=>{
 const f=await updateFixture();try{
  const run=async(command,args,options)=>command==='/bin/ps'?{stdout:' 23456 '+f.currentExecutable+'\n'}:f.run(command,args,options);
  await assert.rejects(installCompleteBundle({source:f.receipt.bundle_path,destination:f.destination,distribution:{channel:'unsigned-testing'},run}),/running/);
  assert.equal((await require('../bootstrap.cjs').readBundleManifest(f.destination)).application_version,'0.1.0');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('testing copy corruption outside runtime is rejected before retaining or replacing current app',async()=>{
 const f=await updateFixture();try{
  await fs.writeFile(path.join(f.receipt.bundle_path,'Contents/Resources/app.asar'),'published app code');
  const run=async(command,args,options)=>{
   const value=await f.run(command,args,options);
   if(command==='/usr/bin/ditto')await fs.writeFile(path.join(args.at(-1),'Contents/Resources/app.asar'),'corrupted copied code');
   return value;
  };
  await assert.rejects(installCompleteBundle({source:f.receipt.bundle_path,destination:f.destination,distribution:{channel:'unsigned-testing'},run}),/Copied application bundle checksum/);
  assert.equal((await require('../bootstrap.cjs').readBundleManifest(f.destination)).application_version,'0.1.0');
  await assert.rejects(fs.stat(path.join(path.dirname(f.destination),'.Rieke OS.previous.app')),{code:'ENOENT'});
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('helper timeout leaves current app installed and never signals it or launches a replacement',async()=>{
 const f=await updateFixture();try{
  const run=async(command,args,options)=>{
   if(command.endsWith('/python/bin/python3.11'))return {stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify({pid:12345,alive:true,created_at:17,executable:f.currentExecutable})+'\n'};
   if(command==='/usr/bin/open')assert.fail('No launch while parent still alive');return f.run(command,args,options);
  };
  await assert.rejects(require('../testing-install.cjs').applyTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,run,publishReady:()=>{},timeoutMs:1,pollMs:1}),/exit was not acknowledged/);
  assert.equal((await require('../bootstrap.cjs').readBundleManifest(f.destination)).application_version,'0.1.0');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('prepared archive changed after readiness cannot replace current app',async()=>{
 const f=await updateFixture();let reads=0;try{
  const run=async(command,args,options)=>{
   if(command.endsWith('/python/bin/python3.11'))return {stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify(++reads===1?{pid:12345,alive:true,created_at:17,executable:f.currentExecutable}:{pid:12345,alive:false})+'\n'};
   return f.run(command,args,options);
  };
  await assert.rejects(require('../testing-install.cjs').applyTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,run,publishReady:()=>{require('node:fs').writeFileSync(f.receipt.archive_path,'modified after acknowledgement');}}),/archive or bundle checksum differs/);
  assert.equal((await require('../bootstrap.cjs').readBundleManifest(f.destination)).application_version,'0.1.0');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('helper readiness must match its spawned PID, current process, target version and archive before quit can proceed',async()=>{
 const f=await updateFixture();try{
  const directory=path.join(f.destination,'Contents/Resources/app.asar');await fs.mkdir(directory);
  for(const file of ['testing-install.cjs','bootstrap.cjs','updater-validation.cjs','physical-fs.cjs'])await fs.copyFile(path.join(__dirname,'..',file),path.join(directory,file));
  const helper=require(await fs.realpath(path.join(directory,'testing-install.cjs')));
  const {EventEmitter}=require('node:events'),{PassThrough}=require('node:stream');
  const spawnHelper=()=>{
   const child=new EventEmitter();child.pid=777;child.stdout=new PassThrough();child.stderr=new PassThrough();child.unref=()=>{};child.kill=()=>assert.fail('No helper or current app force kill');
   setImmediate(()=>child.stdout.write('RIEKE_TESTING_INSTALL_READY='+JSON.stringify({pid:777,current_pid:12345,version:'0.0.1',archive_sha256:f.receipt.archive_sha256})+'\n'));
   return child;
  };
  const run=async(command,args,options)=>command.endsWith('/python/bin/python3.11')?{stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify({pid:12345,alive:true,created_at:17,executable:f.currentExecutable})+'\n'}:f.run(command,args,options);
  await assert.rejects(helper.launchTestingInstall({receiptPath:f.receiptPath,currentExecutable:f.currentExecutable,currentPid:12345,run,spawnHelper}),/readiness identity differs/);
  assert.equal((await require('../bootstrap.cjs').readBundleManifest(f.destination)).application_version,'0.1.0');
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});
test('testing copy cannot silently lose the downloaded app quarantine attribute',async()=>{
 const f=await fixture();try{
  await execFile('/usr/bin/xattr',['-w','com.apple.quarantine','0083;00000001;RiekeFixture;',f.source]);
  await assert.rejects(installCompleteBundle({...f,distribution:{channel:'unsigned-testing'}}),/quarantine attribute differs/);
  await assert.rejects(fs.stat(f.destination),{code:'ENOENT'});
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});

test('actual Electron main and RUN_AS_NODE hash physical ASAR bytes and copy and remove the complete native bundle',async()=>{
 const f=await fixture();try{
  const archive=path.join(f.source,'Contents/Resources/app.asar');
  const contents=path.join(f.root,'asar-content');await fs.mkdir(contents);
  await fs.writeFile(path.join(contents,'main.cjs'),'module.exports="owned archive fixture";');
  await require('@electron/asar').createPackage(contents,archive);
  const expected=await require('../bootstrap.cjs').bundleDigest(f.source);
  const archiveSHA=crypto.createHash('sha256').update(await fs.readFile(archive)).digest('hex');
  const electron=require('electron');const home=path.join(f.root,'home');await fs.mkdir(home);
  const code=`const physical=require('original-fs').promises;const patched=require('node:fs/promises');
   const bootstrap=require(process.argv[1]);const helper=require(process.argv[2]);
   const path=require('node:path');const {promisify}=require('node:util');const native=promisify(require('node:child_process').execFile);
   (async()=>{const source=process.argv[3],home=process.argv[4],archive=path.join(source,'Contents/Resources/app.asar');
    const patchedVirtual=(await patched.lstat(archive)).isDirectory();
    const digest=await bootstrap.bundleDigest(source);const archiveSHA=await helper.sha256(archive);
    const run=async(command,args,options)=>command==='/usr/bin/codesign'?{stdout:'',stderr:''}:native(command,args,options);
    const installed=await bootstrap.installCompleteBundle({source,home,run,distribution:{channel:'unsigned-testing'},expectedBundleSha256:digest});
    const copied=(await physical.lstat(path.join(installed.destination,'Contents/Resources/app.asar'))).isFile();
    const copiedDigest=await bootstrap.bundleDigest(installed.destination);
    await physical.rm(installed.destination,{recursive:true,force:true});
    console.log(JSON.stringify({patchedVirtual,digest,archiveSHA,copied,copiedDigest,removed:!(await physical.readdir(path.dirname(installed.destination))).length}));
   })().catch(error=>{console.error(error);process.exitCode=1;});`;
  const parameters=[path.resolve(__dirname,'../bootstrap.cjs'),path.resolve(__dirname,'../testing-install.cjs'),f.source,home];
  for(const mainProcess of [false,true]){
   const script=path.join(f.root,'owned-main.cjs');
   if(mainProcess)await fs.writeFile(script,`const ownedApp=require('electron').app;ownedApp.setPath('userData',require('node:path').join(process.env.HOME,'main-profile'));process.argv.splice(1,1);`+
    code.replace('process.exitCode=1;});','process.exitCode=1;}).finally(()=>ownedApp.exit(process.exitCode||0));'));
   const result=await execFile(electron,mainProcess?[script,...parameters]:['-e',code,...parameters],
    {env:{HOME:home,PATH:'/usr/bin:/bin',...(mainProcess?{}:{ELECTRON_RUN_AS_NODE:'1'})},timeout:20000});
   const proof=JSON.parse(result.stdout.trim().split('\n').find(line=>line.startsWith('{')));
   assert.equal(proof.patchedVirtual,true,'The actual Electron ASAR patch must be exercised');
   assert.equal(proof.digest,expected);assert.equal(proof.archiveSHA,archiveSHA);
   assert.equal(proof.copied,true);assert.equal(proof.copiedDigest,expected);assert.equal(proof.removed,true);
  }
 }finally{await fs.rm(f.root,{recursive:true,force:true});}
});

test('native helper CLI loads from a real ASAR under Electron RUN_AS_NODE and safely defers an invalid private receipt',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-native-helper-cli-'));try{
  const contents=path.join(root,'helper-content');await fs.mkdir(contents);
  for(const file of ['testing-install.cjs','bootstrap.cjs','updater-validation.cjs','physical-fs.cjs'])
   await fs.copyFile(path.join(__dirname,'..',file),path.join(contents,file));
  const archive=path.join(root,'app.asar');await require('@electron/asar').createPackage(contents,archive);
  const home=path.join(root,'home'),cache=path.join(home,'profile/updates/unsigned-testing');await fs.mkdir(cache,{recursive:true});
  const receipt=path.join(cache,'install-test.json');await fs.writeFile(receipt,JSON.stringify({
   format:'rieke-unsigned-testing-update',version:1,channel:'unsigned-testing',identifier:'org.riekeos.desktop',validated:true}),{mode:0o600});
  const executable=require('electron');
  await assert.rejects(execFile(executable,[path.join(archive,'testing-install.cjs'),'--apply',receipt],
   {env:{HOME:home,PATH:'/usr/bin:/bin',ELECTRON_RUN_AS_NODE:'1'},timeout:10000}),error=>{
    assert.equal(error.code,1);assert.ok(!error.stdout.includes('RIEKE_TESTING_INSTALL_READY='));
    assert.equal(error.stderr,'','Helper must reach its owned receipt failure handler');return true;
   });
  const result=JSON.parse(await fs.readFile(receipt+'.result.json','utf8'));
  assert.equal(result.state,'Deferred');assert.equal((await fs.stat(receipt+'.result.json')).mode&0o077,0);
  assert.ok(!(await fs.readdir(home)).includes('Applications'));
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
