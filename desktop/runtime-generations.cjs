'use strict';
// Whole physical runtimes have immutable locations. The current pointer selects
// future sessions; it never changes the files of a running scientific session.
const fs = require('./physical-fs.cjs');
const fsp = fs.promises;
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {spawn, execFile, execFileSync} = require('node:child_process');
const {promisify} = require('node:util');
const run = promisify(execFile);
const {verifyTestingBundle, bundleDigest, readBundleManifest, installCompleteBundle, otherDiscoProcessRunning, quarantinePreserved} = require('./bootstrap.cjs');
const HASH = /^[a-f0-9]{64}$/;
function runtimeStore(home = os.homedir()) {
  return path.join(home, 'Library/Application Support/Rieke OS/application-versions/unsigned-testing/darwin-arm64');
}
function privateDirectory(directory) {
  fs.mkdirSync(directory, {recursive:true, mode:0o700});
  const stat = fs.lstatSync(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== process.getuid() || (stat.mode & 0o022))
    throw Error('Runtime directory must be private and owned by this user');
  if (fs.realpathSync(directory) !== path.resolve(directory)) throw Error('Runtime directory must have a physical path');
}
function bundlePath(root, id) {
  if (!HASH.test(id || '')) throw Error('Invalid runtime identity');
  return path.join(root, 'generations', id, 'Disco.app');
}
function readRecord(root, id) {
  const bundle = bundlePath(root,id);
  const record = JSON.parse(fs.readFileSync(path.join(path.dirname(bundle),'generation.json'),'utf8'));
  if (record.format !== 'disco-runtime-generation' || record.version !== 1 || record.id !== id || !record.manifest)
    throw Error('Invalid runtime generation record');
  return {...record,bundle};
}
function readCurrent(root) {
  const value = JSON.parse(fs.readFileSync(path.join(root,'current.json'),'utf8'));
  if (value.format !== 'disco-current-runtime' || value.version !== 1 || !HASH.test(value.id) || typeof value.revision !== 'string')
    throw Error('Invalid current runtime pointer');
  return {...value, generation:readRecord(root,value.id)};
}
async function atomicJSON(file, value) {
  const temporary = `${file}.${crypto.randomUUID()}.tmp`;
  const handle = await fsp.open(temporary,'wx',0o600);
  try { await handle.writeFile(JSON.stringify(value)+'\n'); await handle.sync(); }
  finally { await handle.close(); }
  await fsp.rename(temporary,file);
  const parent = await fsp.open(path.dirname(file),'r');
  try { await parent.sync(); } finally { await parent.close(); }
}
async function verifiedBundle(bundle) {
  const manifest = await verifyTestingBundle(bundle);
  const bytes = await fsp.readFile(path.join(bundle,'Contents/Resources/runtime/runtime-manifest.json'));
  const manifestHash = crypto.createHash('sha256').update(bytes).digest('hex');
  const id = await bundleDigest(bundle,{runtimeManifest:manifest,runtimeManifestSha256:manifestHash});
  return {manifest,manifestHash,id};
}
class RuntimeGenerations {
  constructor({root=runtimeStore(), python, verify=verifiedBundle, copy, readQuarantine}={}) {
    this.root=root;this.python=python;this.verify=verify;
    this.copy=copy || ((source,destination)=>run('/usr/bin/ditto',[source,destination]));
    this.readQuarantine=readQuarantine || (async bundle=>{
      try{return (await run('/usr/bin/xattr',['-px','com.apple.quarantine',bundle])).stdout.replace(/\s/g,'').toLowerCase();}
      catch(error){if(error.code===1&&/No such xattr/i.test(error.stderr||''))return null;throw error;}
    });
  }
  createFrontDoorProfile() {
    privateDirectory(this.root);
    const parent=path.join(this.root,'front-doors');privateDirectory(parent);
    const directory=fs.mkdtempSync(path.join(parent,'launch-'));
    fs.writeFileSync(path.join(directory,'owner.json'),JSON.stringify({format:'disco-front-door-profile',version:1,pid:process.pid})+'\n',{mode:0o600,flag:'wx'});
    const profile=path.join(directory,'profile');privateDirectory(profile);
    return profile;
  }
  async stage(source, expected={}) {
    privateDirectory(this.root);
    privateDirectory(path.join(this.root,'generations'));
    let sourcePin;
    if(source.startsWith(path.join(this.root,'generations')+path.sep)){
      const id=path.basename(path.dirname(source));
      if(source!==bundlePath(this.root,id))throw Error('Invalid stored runtime source');
      sourcePin=await this.transaction({operation:'prepare',id});
    }
    const identity=await this.verify(source);
    if(sourcePin&&sourcePin.id!==identity.id)throw Error('Stored runtime has changed');
    if((expected.bundle_sha256 && expected.bundle_sha256!==identity.id)||
      (expected.runtime_manifest_sha256 && expected.runtime_manifest_sha256!==identity.manifestHash)||
      (expected.version && expected.version!==identity.manifest.application_version))
      throw Error('Prepared runtime no longer matches the downloaded update');
    const bundle=bundlePath(this.root,identity.id);
    try {
      const existing=readRecord(this.root,identity.id);
      const prepared=sourcePin||await this.transaction({operation:'prepare',id:existing.id});
      if (!sourcePin&&(await this.verify(existing.bundle)).id !== identity.id) throw Error('Stored runtime has changed');
      return prepared;
    } catch(error) { if(error.code!=='ENOENT')throw error; }
    const staging=await fsp.mkdtemp(path.join(this.root,'staging-'));
    try {
      await atomicJSON(path.join(staging,'stage-owner.json'),{format:'disco-runtime-staging',version:1,pid:process.pid});
      const quarantine=await this.readQuarantine(source);
      await this.copy(source,path.join(staging,'Disco.app'));
      if(!quarantinePreserved(quarantine,await this.readQuarantine(path.join(staging,'Disco.app'))))throw Error('Copied runtime quarantine differs');
      const copied=await this.verify(path.join(staging,'Disco.app'));
      if(copied.id!==identity.id)throw Error('Copied runtime differs from its verified source');
      const record={format:'disco-runtime-generation',version:1,...identity};
      await atomicJSON(path.join(staging,'generation.json'),record);
      return await this.transaction({operation:'publish',staging});
    } finally { await fsp.rm(staging,{recursive:true,force:true}); }
  }
  transaction(request,{sync=false}={}) {
    const script=require('node:fs').readFileSync(path.join(__dirname,'runtime-store.py'),'utf8');
    const args=['-I','-B','-c',script];
    const input=JSON.stringify({root:this.root,runtime_application:path.resolve(path.dirname(this.python),'../../application/python'),...request});
    const failure=error=>{try{return Error(JSON.parse(String(error.stdout)).error);}catch{return error;}};
    if(sync){try{return JSON.parse(execFileSync(this.python,args,{input,encoding:'utf8',timeout:60000,maxBuffer:16*1024*1024}));}catch(error){throw failure(error);}}
    const promise=run(this.python,args,{timeout:120000,maxBuffer:16*1024*1024});
    promise.child.stdin.end(input);
    return promise.then(result=>JSON.parse(result.stdout),error=>{throw failure(error);});
  }
  async activate(generation,{rollbackRevision}={}) {
    return this.transaction({operation:'activate',id:generation.id,preparation:generation.preparation,rollbackRevision});
  }
  current() { return readCurrent(this.root); }
  async restorePrevious() {
    const pointer=this.current();
    if(!pointer.previous)throw Error('No verified previous runtime is retained');
    const prepared=await this.stage(bundlePath(this.root,pointer.previous));
    return this.activate(prepared,{rollbackRevision:pointer.revision});
  }
  async maintain({destination=path.join(os.homedir(),'Applications/Disco.app')}={}) {
    const current=await this.transaction({operation:'pin-current'});
    let canonical;
    try { canonical=await readBundleManifest(destination); } catch {}
    let compatibleFrontDoor=false;
    try { compatibleFrontDoor=(await run('/usr/libexec/PlistBuddy',['-c','Print :DiscoRuntimeGenerationProtocol',path.join(destination,'Contents/Info.plist')])).stdout.trim()==='1'; } catch {}
    let promotion={ready:true};
    if(!compatibleFrontDoor&&(canonical?.application_version!==current.generation.manifest.application_version||canonical?.source_commit!==current.generation.manifest.source_commit)){
      try {
        if(await otherDiscoProcessRunning(run,destination)||await otherDiscoProcessRunning(run,path.join(path.dirname(destination),'.Rieke OS.previous.app')))
          promotion={ready:false,reason:'The existing application is still in use.'};
        else await installCompleteBundle({source:current.generation.bundle,destination,distribution:{channel:'unsigned-testing'}});
      }
      catch(error){promotion={ready:false,reason:error.message};}
    }
    // Promotion is maintenance, never an admission precondition. A live legacy
    // flat installation remains exactly where its lazy imports expect it.
    await this.transaction({operation:'unpin',token:current.pin});
    const retirement=await this.collect();
    return {promotion,retirement};
  }
  async collect() { return this.transaction({operation:'collect'}); }
  async restartAfterExit(generation,profile) {
    const identity=await require('./testing-install.cjs').processCreationIdentity(process.pid,process.execPath);
    if(!identity.alive)throw Error('Current session identity is unavailable');
    const {nonce,file}=await this.transaction({operation:'restart-handoff',id:generation.id,preparation:generation.preparation,profile,identity});
    const child=spawn(process.execPath,[path.join(__dirname,'generation-restart.cjs'),file],
      {env:{...process.env,ELECTRON_RUN_AS_NODE:'1'},detached:true,stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{
      let output='';
      const timer=setTimeout(()=>{child.kill('SIGTERM');reject(Error('Runtime restart handoff timed out'));},30000);
      child.once('error',error=>{clearTimeout(timer);reject(error);});
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Runtime restart handoff exited before readiness'));});
      child.stdout.on('data',bytes=>{output+=bytes;if(output.includes(`DISCO_GENERATION_READY=${nonce}\n`)){clearTimeout(timer);resolve();}});
    });
    child.stdout.destroy();child.stderr.destroy();child.unref();
    return {ready:true};
  }
  async prepareLaunch({profile, recover=false, fresh=false, generation,preparation=generation?.preparation,handoff}={}) {
    return this.transaction({operation:'reserve',profile,recover,fresh,id:generation?.id,preparation,handoff});
  }
  async launch(options={}) {
    const prepared=await this.prepareLaunch(options);
    const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
    // An uncertain LaunchServices result retains its reservation. A delayed
    // launch either consumes it or is rejected after its bounded expiry.
    await run(prepared.args[0],prepared.args.slice(1),{env,timeout:30000});
    return {opened:true,generation:prepared.generation};
  }
}
// Synchronous admission happens before Electron ready/profile locks. The ticket
// remains as a retention pin until the launch and its descendants are retired.
function admitRuntime({bundle,argv=process.argv,root=runtimeStore()}) {
  if(!bundle?.startsWith(path.join(root,'generations')+path.sep))return null;
  privateDirectory(root);
  const id=path.basename(path.dirname(bundle));
  const record=readRecord(root,id);
  if(record.bundle!==bundle||fs.realpathSync(bundle)!==bundle)throw Error('Runtime location does not match its identity');
  const tokens=argv.filter(value=>value.startsWith('--disco-runtime-admission='));
  if(tokens.length===0)return null;
  if(tokens.length!==1)throw Error('Invalid runtime admission');
  const token=tokens[0].split('=')[1];
  if(!/^[a-f0-9-]{36}$/.test(token))throw Error('Invalid runtime admission');
  const profiles=argv.filter(value=>value.startsWith('--user-data-dir='));
  if(profiles.length!==1)throw Error('An exact runtime profile is required');
  const store=new RuntimeGenerations({root,python:path.join(bundle,'Contents/Resources/runtime/python/bin/python3.11')});
  const request={token,pid:process.pid};
  store.transaction({...request,operation:'admit',profile:profiles[0].slice('--user-data-dir='.length),
    fresh:argv.includes('--disco-new-session'),recover:argv.includes('--disco-recover-session')},{sync:true});
  return {generation:record,store,
    bindProfile(profile){store.transaction({...request,operation:'bind-profile',profile},{sync:true});},
    retire(){store.transaction({...request,operation:'retire'},{sync:true});}};
}
module.exports={RuntimeGenerations,admitRuntime,runtimeStore};
