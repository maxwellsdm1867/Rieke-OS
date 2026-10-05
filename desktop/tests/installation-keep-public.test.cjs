'use strict';
// Strict injected command/spawn examples. No command fallback or CLI invocation.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {createHash}=require('node:crypto');
const {EventEmitter}=require('node:events');
const {PassThrough}=require('node:stream');
const {bundleDigest}=require('../bootstrap.cjs');
const {restorePriorBundle}=require('../update-recovery.cjs');
const {sha256,applyTestingInstall}=require('../testing-install.cjs');
const rootDesktop=path.resolve(__dirname,'..');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function fixture(t){
 const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'disco-install-keep-')));
 const bundles=new Map(),calls=[],children=[];
 t.after(async()=>{for(const child of children){child.stdout?.destroy();child.stderr?.destroy();}await fs.rm(root,{recursive:true,force:true});});
 async function bundle(location,version){
  const runtime=path.join(location,'Contents/Resources/runtime'),resources={};
  await fs.mkdir(path.join(location,'Contents/MacOS'),{recursive:true});
  await fs.writeFile(path.join(location,'Contents/MacOS/Rieke OS'),'inert owned executable fixture');
  await fs.writeFile(path.join(location,'Contents/Info.plist'),'injected fixture metadata');
  for(const name of ['python/bin/python3.11','mysql/bin/mysqld','mysql/bin/mysql','mysql/bin/mysqldump','application/python/workspace_desktop.py']){
   const file=path.join(runtime,name),bytes=Buffer.from('inert resource');await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,bytes);
   resources[name]={size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
  }
  const manifest={format:'rieke-desktop-runtime',version:1,application_version:version,source_commit:'a'.repeat(40),parser_commit:'b'.repeat(40),platform:'darwin',architecture:'arm64',mysql_version:'8.4.2',python_version:'3.11.13',minimum_macos_version:'14.0',workspace_formats:[1],database_compatibility:1,resources};
  await fs.writeFile(path.join(runtime,'runtime-manifest.json'),JSON.stringify(manifest));bundles.set(location,manifest);return manifest;
 }
 const installed=path.join(root,'Applications','Rieke OS.app'),manifest=await bundle(installed,'1.0.0');
 const executable=path.join(installed,'Contents/MacOS/Rieke OS'),profile=path.join(root,'profile');await fs.mkdir(profile);
 let creation=17,identityReads=0;
 const run=async(command,args)=>{
  calls.push([command,args]);
  if(command==='/usr/bin/codesign'){
   assert.ok(bundles.has(args.at(-1)));assert.ok(['--verify','-dv'].includes(args[0]));
   return{stdout:args[0]==='-dv'?'Identifier=org.riekeos.desktop\nTeamIdentifier=OWNED123\nAuthority=Developer ID Application: Fixture':'',stderr:''};
  }
  if(command==='/usr/libexec/PlistBuddy'){
   const item=bundles.get(path.dirname(path.dirname(args[2])));assert.ok(item);assert.equal(args[0],'-c');
   const fields={'Print :CFBundleIdentifier':'org.riekeos.desktop','Print :CFBundleExecutable':'Rieke OS','Print :CFBundleShortVersionString':item.application_version,'Print :LSMinimumSystemVersion':'14.0'};
   assert.ok(Object.hasOwn(fields,args[1]));return{stdout:fields[args[1]],stderr:''};
  }
  if(command==='/usr/sbin/spctl'){assert.deepEqual(args.slice(0,3),['--assess','--type','execute']);assert.ok(bundles.has(args[3]));return{stdout:'',stderr:''};}
  if(command==='/usr/bin/sw_vers'){assert.deepEqual(args,['-productVersion']);return{stdout:'14.2',stderr:''};}
  if(command===path.join(installed,'Contents/Resources/runtime/python/bin/python3.11')){
   assert.deepEqual(args.slice(0,3),['-I','-B','-c']);assert.equal(args[4],'12345');identityReads++;
   return{stdout:'RIEKE_PROCESS_IDENTITY='+JSON.stringify({pid:12345,alive:true,created_at:typeof creation==='function'?creation(identityReads):creation,executable})+'\n'};
  }
  assert.fail('Unexpected command rejected: '+command); // Never execute anything.
 };
 function child(){const value=new EventEmitter();value.pid=777;value.stdout=new PassThrough();value.stderr=new PassThrough();value.unref=()=>{};value.kill=()=>assert.fail('No signals');children.push(value);return value;}
 async function signed(){const previous=path.join(profile,'updates/previous/Rieke OS.app');await bundle(previous,'0.9.0');await fs.writeFile(path.join(profile,'updates/previous.json'),JSON.stringify({team:'OWNED123',identifier:'org.riekeos.desktop',application_version:'0.9.0',source_commit:'a'.repeat(40)}));return previous;}
 async function testing(){
  const cache=path.join(profile,'updates/unsigned-testing');await fs.mkdir(cache,{recursive:true,mode:0o700});
  const candidate=path.join(cache,'Rieke OS.app');await bundle(candidate,'1.1.0');const archive=path.join(cache,'candidate.zip');await fs.writeFile(archive,'inert archive');
  const directory=path.join(installed,'Contents/Resources/app.asar');await fs.mkdir(directory);
  for(const name of ['testing-install.cjs','bootstrap.cjs','updater-validation.cjs','physical-fs.cjs','install-name.cjs'])await fs.copyFile(path.join(rootDesktop,name),path.join(directory,name));
  const receipt={format:'rieke-unsigned-testing-update',version:1,channel:'unsigned-testing',identifier:'org.riekeos.desktop',validated:true,operation:'update',install_path:installed,current_executable:executable,current_pid:12345,current_created_at:17,current_version:'1.0.0',target_version:'1.1.0',archive_path:archive,archive_sha256:await sha256(archive),bundle_path:candidate,bundle_sha256:await bundleDigest(candidate),runtime_manifest_sha256:await sha256(path.join(candidate,'Contents/Resources/runtime/runtime-manifest.json')),current_manifest_sha256:await sha256(path.join(installed,'Contents/Resources/runtime/runtime-manifest.json'))};
  const receiptPath=path.join(cache,'install.json');await fs.writeFile(receiptPath,JSON.stringify(receipt),{mode:0o600});
  return{directory,receipt,receiptPath,helper:require(path.join(directory,'testing-install.cjs'))};
 }
 return{root,profile,installed,executable,manifest,run,calls,child,signed,testing,setCreation:value=>{creation=value;}};
}
test('signed recovery defers or waits for root helper spawn before quit authorization',async t=>{
 const f=await fixture(t),previous=await f.signed();let authorized=0,quit=0,spawned;
 const app={isPackaged:true,getPath:name=>name==='exe'?f.executable:f.profile,quit:()=>{quit++;}};
 const options={app,manifest:f.manifest,run:f.run,authorizeQuit:()=>{authorized++;},prepareQuit:async()=>({ready:false}),spawnHelper:()=>assert.fail('Deferred recovery must not spawn')};
 assert.deepEqual(await restorePriorBundle(options),{ready:false});assert.equal(authorized,0);assert.equal(quit,0);
 let signalSpawn;const entered=new Promise(resolve=>{signalSpawn=resolve;});
 const pending=restorePriorBundle({...options,prepareQuit:async()=>({ready:true}),spawnHelper:(exe,args,config)=>{
  assert.equal(exe,f.executable);assert.deepEqual(args,[path.join(rootDesktop,'recovery-install.cjs'),String(process.pid),previous,f.installed]);
  assert.equal(config.env.ELECTRON_RUN_AS_NODE,'1');assert.equal(config.detached,true);assert.equal(config.cwd,f.profile);
  spawned=f.child();signalSpawn();return spawned;
 }});
 await entered;assert.equal(authorized,0);assert.equal(quit,0);spawned.emit('spawn');
 assert.deepEqual(await pending,{ready:true,restoring:true});assert.equal(authorized,1);assert.equal(quit,1);
});
test('signed helper spawn failure grants no quit authority',async t=>{
 const f=await fixture(t);await f.signed();let authorized=0;
 await assert.rejects(restorePriorBundle({app:{isPackaged:true,getPath:name=>name==='exe'?f.executable:f.profile,quit:()=>assert.fail('No quit')},manifest:f.manifest,run:f.run,prepareQuit:async()=>({ready:true}),authorizeQuit:()=>{authorized++;},spawnHelper:()=>{const c=f.child();setImmediate(()=>c.emit('error',Error('owned spawn rejected')));return c;}}),/owned spawn rejected/);
 assert.equal(authorized,0);
});
for(const wrong of [false,true])test(`testing root helper requires matching readiness packet (${wrong?'reject':'accept'})`,async t=>{
 const f=await fixture(t),x=await f.testing();let child,entered;const started=new Promise(resolve=>{entered=resolve;});let settled=false;
 const pending=x.helper.launchTestingInstall({receiptPath:x.receiptPath,currentExecutable:f.executable,currentPid:12345,run:f.run,spawnHelper:(exe,args,config)=>{
  assert.equal(exe,f.executable);assert.deepEqual(args,[path.join(x.directory,'testing-install.cjs'),'--apply',x.receiptPath]);assert.equal(config.cwd,path.dirname(x.receiptPath));assert.equal(config.env.ELECTRON_RUN_AS_NODE,'1');
  child=f.child();entered();return child;
 }});pending.then(()=>{settled=true;},()=>{settled=true;});
 await started;child.emit('spawn');await tick();assert.equal(settled,false,'Spawn alone is not testing readiness');
 child.stdout.write('RIEKE_TESTING_INSTALL_READY='+JSON.stringify({pid:child.pid,current_pid:12345,version:wrong?'0.0.0':x.receipt.target_version,archive_sha256:x.receipt.archive_sha256})+'\n');
 if(wrong)await assert.rejects(pending,/readiness identity differs/);else assert.deepEqual(await pending,{ready:true,helperPid:777,resultPath:x.receiptPath+'.result.json'});
});
test('testing creation identity mismatch rejects before helper spawn',async t=>{
 const f=await fixture(t),x=await f.testing();f.setCreation(18);
 await assert.rejects(x.helper.launchTestingInstall({receiptPath:x.receiptPath,currentExecutable:f.executable,currentPid:12345,run:f.run,spawnHelper:()=>assert.fail('No helper for changed identity')}),/process ownership changed/);
});
test('testing readiness does not bypass changed creation identity while waiting for exit',async t=>{
 const f=await fixture(t),x=await f.testing();f.setCreation(n=>n===1?17:18);let packet;
 await assert.rejects(applyTestingInstall({receiptPath:x.receiptPath,currentExecutable:f.executable,run:f.run,timeoutMs:1,pollMs:1,publishReady:value=>{packet=value;}}),/ownership changed while waiting/);
 assert.equal(packet.current_pid,12345);assert.equal(packet.pid,process.pid);
 assert.equal(JSON.parse(await fs.readFile(path.join(f.installed,'Contents/Resources/runtime/runtime-manifest.json'))).application_version,'1.0.0');
});
