'use strict';
// Exercise the unsigned app's installed entry and real LaunchServices handoff.
// No global keystrokes, bundle-ID lookup, raw process signals or external projects.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {createHash, randomUUID} = require('node:crypto');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {setTimeout: delay} = require('node:timers/promises');
const {packagedSource} = require('./packaged-path.cjs');
const {projectWindowEvidence} = require('./startup-quit-window.cjs');
const {ownedControl} = require('./helpers.cjs');
const {runtimeStore} = require('../runtime-generations.cjs');
const {ServiceSupervisor} = require('../supervisor.cjs');
const {VIEW_COMPATIBILITY} = require('../startup/startup-session.cjs');

const run = promisify(execFile);
const output = path.resolve(__dirname, '../../docs/dev/desktop-ui-e2e/startup-quit-receipt.json');
const receipt = {format:'disco-installed-startup-quit-v1', passed:false, stages:[]};
let fixture, helper, project, registry, services, generation, target, phase;
const profileNonces = new Set(), scienceSessions = new Set();

async function read(file) {
  try { return JSON.parse(await fs.readFile(file, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}
async function poll(label, timeout, observe) {
  const deadline = performance.now() + timeout;
  while (performance.now() < deadline) {
    const observation = await observe();
    if (observation) return observation;
    await delay(40);
  }
  throw Error(label + ' deadline exceeded');
}
async function save() {
  await fs.mkdir(path.dirname(output), {recursive:true});
  const temporary = output+'.'+process.pid+'.tmp';
  await fs.writeFile(temporary, JSON.stringify(receipt, null, 2) + '\n');
  await fs.rename(temporary,output);
}
async function stage(name, action) {
  phase = name;
  receipt.current_stage = name;
  await save();
  const begin = performance.now(), evidence = await action();
  receipt.stages.push({name, elapsed_ms:Math.round(performance.now()-begin), evidence});
  await save();
}
async function processes() {
  const {stdout} = await run('/bin/ps', ['-ww','-axo','pid=,comm='], {maxBuffer:4*1024*1024});
  return stdout.split('\n').flatMap(line => {
    const match = /^\s*(\d+)\s+(.+)$/.exec(line);
    const executable = match?.[2].replace(/^\/var\//, '/private/var/').replace(/^\/tmp\//, '/private/tmp/');
    return executable?.startsWith(fixture.root+'/') ? [{pid:Number(match[1]), executable}] : [];
  });
}
async function open(app, args) {
  // Pass the same isolation to both shell and first LaunchServices process.
  const env = {...process.env, ...fixture.env};
  const flags = Object.entries(fixture.env).flatMap(([key,value]) => ['--env', key+'='+value]);
  await run('/usr/bin/open',['-n','-g','-a',app,...flags,'--args',...args],{env,timeout:30000});
}
async function preflight() {
  helper = path.join(fixture.root, 'startup-quit-probe');
  await run('/usr/bin/clang',['-fobjc-arc','-framework','AppKit','-framework','CoreGraphics','-o',helper,path.join(__dirname,'startup-quit-probe.m')]);
  const apps = [];
  for (const name of ['Parent','Child']) {
    const app = path.join(fixture.root, name+'.app'), contents = path.join(app,'Contents');
    await fs.mkdir(path.join(contents,'MacOS'),{recursive:true});
    await fs.copyFile(helper,path.join(contents,'MacOS','probe'));
    await fs.writeFile(path.join(contents,'Info.plist'),
      '<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>org.disco.test.'+
      randomUUID()+'</string><key>CFBundleExecutable</key><string>probe</string><key>CFBundlePackageType</key><string>APPL</string>'+
      '<key>LSUIElement</key><true/></dict></plist>');
    apps.push(app);
  }
  const proof = path.join(fixture.root,'child-environment.json');
  await open(apps[0], ['probe-parent', apps[1], proof]);
  const observed = await poll('nested LaunchServices environment',15000,()=>read(proof));
  // Cocoa may shorten /private/var to /var for the same physical home.
  observed.cocoa_home = await fs.realpath(observed.cocoa_home);
  assert.deepEqual(observed,{home:fixture.home,cocoa_home:fixture.home,temporary:fixture.env.TMPDIR,preferences:fixture.env.RIEKE_PREFERENCES_DIR},
    'LaunchServices lost the isolated environment; production launch is unsafe on this host');
  return {native_child_home_and_preferences_verified:true};
}
async function install() {
  let source;
  if (process.env.DISCO_STARTUP_QUIT_CANDIDATE) {
    source = await fs.realpath(process.env.DISCO_STARTUP_QUIT_CANDIDATE);
    const temporary = await fs.realpath(os.tmpdir());
    assert.ok(source.startsWith(temporary+'/rieke-packaged-ui-e2e-') && path.basename(source)==='Disco.app',
      'Local candidate must be an owned disposable test build');
    assert.equal((await fs.stat(source)).uid,process.getuid());
  } else {
    source = packagedSource(path.resolve(__dirname,'..'), require('../package.json').build);
  }
  await fs.mkdir(path.dirname(fixture.bundle), {recursive:true});
  await run('/usr/bin/ditto',[source,fixture.bundle],{timeout:120000});
  const runtime = path.join(fixture.bundle,'Contents/Resources/runtime');
  const manifest = await read(path.join(runtime,'runtime-manifest.json'));
  assert.ok(manifest?.source_commit && manifest?.application_version);
  const digest = async filename => createHash('sha256').update(await fs.readFile(filename)).digest('hex');
  Object.assign(receipt,{source_commit:manifest.source_commit,application_version:manifest.application_version,
    asar_sha256:await digest(path.join(fixture.bundle,'Contents/Resources/app.asar')),
    runtime_manifest_sha256:await digest(path.join(runtime,'runtime-manifest.json'))});
  const {stdout} = await run(path.join(runtime,'python/bin/python3.11'),
    ['-I','-B',path.join(__dirname,'startup-quit-fixture.py'),fixture.root,runtime],
    {env:{...fixture.env,PATH:'/usr/bin:/bin'},timeout:60000});
  const seed = JSON.parse(stdout);
  project = seed.project;
  fixture.seed = seed;
  assert.ok(project.path.startsWith(path.join(fixture.home,'projects')+'/'));
  await fs.writeFile(path.join(fixture.userData,'startup-session.json'), JSON.stringify({
    format:'disco-startup-session',version:1,compatibility:VIEW_COMPATIBILITY,mode:'resume',
    projectId:project.uuid,projectPath:project.path,view:'overview'}),{flag:'wx'});
  return {source_commit:manifest.source_commit,project_uuid:project.uuid,synthetic_epochs:seed.epochs};
}
async function start() {
  await open(fixture.bundle,['--user-data-dir='+fixture.userData]);
  const store = runtimeStore(fixture.home);
  const current = await poll('installed front door selecting an owned generation',240000,()=>read(path.join(store,'current.json')));
  assert.match(current.id,/^[a-f0-9]{64}$/);
  generation = path.join(store,'generations', current.id,'Disco.app');
  assert.equal(await fs.realpath(generation),generation);
  const owner = await poll('scientific application claiming fixture profile',60000,async()=>{
    const value=await read(path.join(fixture.userData,'disco-session-owner.json'));
    return value?.state==='running' && value;
  });
  assert.ok(!profileNonces.has(owner.nonce),'Launch did not create a new profile lease');
  profileNonces.add(owner.nonce);
  target = {pid:owner.pid,nonce:owner.nonce};
  return {generation:current.id,profile_nonce:owner.nonce,pid:owner.pid};
}
async function projectClient() {
  const fx = {...fixture,bundle:generation};
  const row = await poll('desktop authorizing restored project',120000,async()=>{
    const value=await read(registry);
    return value?.services?.find(row=>row.bound && row.project_uuid===project.uuid && row.project_path===project.path);
  });
  const authorized = await ownedControl(fx,'authorize-project',{port:row.port});
  assert.equal(authorized.health.project_uuid,project.uuid);
  assert.equal(authorized.health.session_id,row.session_id);
  assert.equal(authorized.health.source_commit,receipt.source_commit);
  assert.equal(authorized.health.pid,row.pid);
  // Reuse the supervisor's exact PID/start-time/path/listener proof before
  // admitting requests to this child. Keep its renderer token in memory only.
  const observer = new ServiceSupervisor({userData:fixture.userData});
  observer.executable = row.executable;
  assert.ok(row.executable.startsWith(generation+'/'));
  const privateKey = await observer.ownedPreviousCapability(row);
  assert.ok(privateKey, 'Owned project listener identity was not verified');
  const renderer = createHash('sha256').update(privateKey+':renderer').digest('hex');
  const query = async (route,body) => {
    const response=await fetch('http://127.0.0.1:'+row.port+route,{method:body?'POST':'GET',
      redirect:'error',signal:AbortSignal.timeout(10000),
      headers:{'X-Rieke-Desktop-Session':renderer,'X-Workspace-Request':'1','Content-Type':'application/json'},
      ...(body?{body:JSON.stringify(body)}:{})});
    if(!response.ok)throw Error(route+' returned '+response.status);
    return response.json();
  };
  await poll('project data initialization',90000,async()=>{
    const value=await query('/api/project/data-status');
    if(value.status==='failed')throw Error('Restored project initialization failed');
    return value.status==='ready';
  });
  return {query,row};
}
async function checkScience(importFixture) {
  const {query,row} = await projectClient();
  const {recording,epoch,epochs} = fixture.seed;
  if(importFixture){
    const job=await query('/api/imports',{source_path:recording});
    assert.ok(job.job_uuid,'Import was not accepted');
    await poll('synthetic recording import',90000,async()=>{
      const found=(await query('/api/jobs')).jobs.find(item=>item.job_uuid===job.job_uuid);
      if(found && ['failed','interrupted','duplicate','complete_with_warnings','cancelled'].includes(found.status))
        throw Error('Synthetic import ended '+found.status);
      return found?.status==='complete';
    });
  }
  const overview=await query('/api/overview');
  assert.equal(overview.counts.epochs,epochs);
  const trace=await query('/api/epochs/'+epoch.uuid+'/trace?stream_uuid='+epoch.stream_uuid+'&start=17&count=4');
  assert.equal(trace.epoch_uuid,epoch.uuid);
  assert.equal(trace.stream_uuid,epoch.stream_uuid);
  assert.equal(trace.units,'pA');
  assert.equal(trace.sample_rate,10000);
  assert.deepEqual(trace.values,[17,18,19,20].map(i=>epoch.ordinal+i/256));
  assert.ok(!scienceSessions.has(row.session_id),'Relaunch must have a fresh scientific session');
  scienceSessions.add(row.session_id);
  const until = performance.now()+30000;
  let window;
  for (;;) {
    const {stdout} = await run(helper,['window',String(target.pid),generation,'-',project.name,project.path],{timeout:5000});
    const observed = JSON.parse(stdout);
    window = projectWindowEvidence(observed.titles,project.name,observed.can_read_titles);
    if (window.state === 'matched-project-title' || window.state === 'visible-window-titles-unavailable') break;
    if (performance.now() >= until) throw Error('Restored project window deadline exceeded: '+JSON.stringify(window));
    await delay(150);
  }
  return {session_id:row.session_id,project_uuid:row.project_uuid,epochs,epoch_uuid:epoch.uuid,
    waveform_oracle:'owned-project-backend',verified_samples:trace.values,window};
}
async function quit(duringStartup) {
  assert.ok(target?.pid>1 && generation);
  // A single native observer waits for this exact child and immediately sends Quit.
  const {stdout}=await run(helper,['quit',String(target.pid),generation,duringStartup?services:'-',project.uuid,project.path],{timeout:duringStartup?95000:5000});
  const began=performance.now(), checkpoint=stdout.trim();
  await poll('ordinary Quit and exit of all owned bundle processes',45000,async()=>!(await processes()).length);
  const quitTarget=target; target=null;
  assert.equal(await read(registry),null,'Root service ownership record survived ordinary Quit');
  const children=await read(services);
  if (children) {
    assert.deepEqual(children.services, [], 'Project service ownership record survived ordinary Quit');
    assert.deepEqual(children.database_operations, [], 'Project database operation survived ordinary Quit');
    assert.deepEqual(children.recovery_required || [], [], 'Project still requires recovery');
  }
  const owner=await read(path.join(fixture.userData,'disco-session-owner.json'));
  assert.equal(owner?.state,'released');
  assert.equal(owner.nonce,quitTarget.nonce);
  const native=await read(path.join(project.path,'database/native-owner.json'));
  assert.equal(native?.clean_shutdown,true,'Native project database lacks clean shutdown proof');
  assert.equal(await read(path.join(project.path,'database/native-runtime.json')),null);
  // OS lock files can remain after a clean exit; prove both locks can be acquired.
  const locks=[path.join(fixture.userData,'backend/desktop-session.lock'),path.join(project.path,'.app-state-session.lock')];
  await run('/usr/bin/python3',['-I','-B','-c',
    'import sys,fcntl\nfor name in sys.argv[1:]:\n with open(name,"rb") as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)',...locks]);
  return {checkpoint,quit_ms:Math.round(performance.now()-began),owned_processes_after:0,profile_released:true,
    root_registry_removed:true,project_services_remaining:0,project_locks_released:true,native_database_clean:true};
}
async function main() {
  assert.equal(process.platform,'darwin');assert.equal(process.arch,'arm64');
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'rieke-packaged-ui-e2e-startup-quit-')));
  const home = path.join(root,'home'), userData=path.join(home,'state');
  fixture={root,home,userData,bundle:path.join(home,'Applications/Disco.app'),env:{
    HOME:home,CFFIXED_USER_HOME:home,TMPDIR:root+'/',RIEKE_PREFERENCES_DIR:path.join(home,'.rieke-os')}};
  await fs.mkdir(userData,{recursive:true,mode:0o700});
  receipt.fixture_root=root;
  registry=path.join(userData,'desktop-service.json');
  services=path.join(userData,'backend/desktop-services.json');
  try {
    await stage('verify nested LaunchServices isolation',preflight);
    await stage('install and seed synthetic project',install);
    await stage('open exact installed entry',start);
    await stage('import recording and verify known samples',()=>checkScience(true));
    await stage('ordinary quit from ready project',()=>quit(false));
    await stage('launch saved project for interruption',start);
    await stage('ordinary quit during project restoration',()=>quit(true));
    await stage('relaunch after interrupted restoration',start);
    await stage('verify saved project and samples after relaunch',()=>checkScience(false));
    await stage('final ordinary quit',()=>quit(false));
    receipt.passed=true;
    receipt.current_stage='complete';
  } catch(error) {
    receipt.failed_stage=phase;
    receipt.error=error.message;
    if(target){
      try {receipt.failure_cleanup=await quit(false);}
      catch(cleanupError){receipt.failure_cleanup_error=cleanupError.message;}
    }
    throw error;
  } finally {
    await save();
    // CI runners otherwise accumulate disposable app generations across suites.
    // Preserve an unclean/failed fixture for diagnosis. Local cleanup policy
    // can retain a green fixture until the compact receipt has been collected.
    if(receipt.passed && !process.env.DISCO_RETAIN_STARTUP_QUIT_FIXTURE)
      await fs.rm(root,{recursive:true});
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
