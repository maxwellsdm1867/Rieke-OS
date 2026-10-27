'use strict';
// A profile lease is not a scientific project lease. Each live GUI owns a
// separate Chromium/profile/backend namespace; project folders arbitrate use.
const fs = require('node:fs');
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const {execFileSync} = require('node:child_process');
const SLOT = /^session-(0|[1-9][0-9]*)$/;
const IDENTITY = 'disco-profile.json';
const OWNER = 'disco-session-owner.json';
function read(file, limit = 1024 * 1024) {
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.uid !== process.getuid() || stat.size > limit) throw Error('Unverified profile record');
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}
function directory(folder) {
  fs.mkdirSync(folder, {recursive:true, mode:0o700});
  const stat = fs.lstatSync(folder);
  if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== process.getuid()) throw Error('Session profiles must be user-owned directories');
  return fs.realpathSync(folder);
}
function atomic(file, value) {
  const temporary = file + '.' + randomUUID() + '.tmp';
  const fd = fs.openSync(temporary, 'wx', 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value) + '\n'); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  try { fs.renameSync(temporary, file); const parent = fs.openSync(path.dirname(file), 'r'); try { fs.fsyncSync(parent); } finally { fs.closeSync(parent); } }
  finally { fs.rmSync(temporary, {force:true}); }
}
function alive(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) return true;
  try { process.kill(pid, 0); return true; } catch (error) { return error.code !== 'ESRCH'; }
}
function runtimeLeaseFree(profile, {runtime, run = execFileSync}) {
  const backend = path.join(profile, 'backend');
  try { const stat = fs.lstatSync(backend); if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== process.getuid()) return false; }
  catch(error) { return error.code === 'ENOENT'; }
  const lock = path.join(backend, 'desktop-session.lock');
  let stat; try { stat = fs.lstatSync(lock); } catch(error) { if(error.code==='ENOENT')return true; return false; }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.uid !== process.getuid()) return false;
  const script = 'import os,sys,fcntl\nf=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW)\ntry:\n fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:\n sys.exit(1)\nfinally:\n os.close(f)\n';
  try { run(path.join(runtime, 'python/bin/python3.11'), ['-I', '-B', '-c', script, lock], {timeout:5000, stdio:'pipe'}); return true; }
  catch { return false; }
}
function reusable(profile, options) {
  try {
    const owner = read(path.join(profile, OWNER), 16384);
    if (owner && (owner.format !== 'disco-session-owner' || owner.version !== 1 || !['running','released'].includes(owner.state) || !Number.isSafeInteger(owner.pid) || owner.pid <= 0 || typeof owner.nonce !== 'string' || !owner.nonce)) return false;
    // An interrupted modern session is retained for explicit recovery, including
    // the window between a spawn and publication of its backend PID record.
    if (owner?.state === 'running') return false;
    const root = read(path.join(profile, 'desktop-service.json'));
    if (root && (!Number.isSafeInteger(root.pid) || root.pid <= 0 || !Number.isInteger(root.port) ||
        !path.isAbsolute(root.executable || '') || !path.isAbsolute(root.entry || '') || !root.session_id || options.alive(root.pid))) return false;
    const children = read(path.join(profile, 'backend/desktop-services.json'));
    if (children && (children.version !== 1 || !Array.isArray(children.services) || children.services.length ||
        (children.database_operations !== undefined && (!Array.isArray(children.database_operations) || children.database_operations.length)) ||
        (children.recovery_required !== undefined && (!Array.isArray(children.recovery_required) || children.recovery_required.length)))) return false;
    if (!children && root?.services?.length) return false;
    return options.probe(profile);
  } catch { return false; }
}
function copyPreferences(base, profile, {runtime, run = execFileSync}) {
  const from = path.join(base, 'backend/preferences'), to = path.join(profile, 'backend/preferences');
  // Only discovery preferences. Never clone Chromium state, drafts, capabilities,
  // ownership records or update receipts into another instance.
  try {
    const value = read(path.join(from, 'workspace-selection.json'), 65536);
    if (value?.version === 1 && typeof value.managed_root === 'string' && path.isAbsolute(value.managed_root) && !value.managed_root.includes('\0')) {
      directory(to); atomic(path.join(to, 'workspace-selection.json'), {version:1, managed_root:value.managed_root});
    }
  } catch {}
  try {
    const file = path.join(from, 'project-index.json');
    if (!read(file)) return;
    // Reuse the owning validator instead of creating another schema in JS.
    const script = 'import sys,json\nsys.path.insert(0,sys.argv[1])\nfrom workspace_startup_registry import _validate_project_index\nprint(json.dumps(_validate_project_index(json.loads(sys.stdin.read()))))\n';
    const value = run(path.join(runtime, 'python/bin/python3.11'), ['-I','-B','-c',script,path.join(runtime,'application/python')],
      {input:JSON.stringify(read(file)), encoding:'utf8', timeout:5000, maxBuffer:1024*1024});
    directory(to); atomic(path.join(to, 'project-index.json'), JSON.parse(value));
  } catch { /* A missing/unreadable discovery hint never prevents a fresh chooser. */ }
}
function preservedProfiles(base, current, skipped, processAlive) {
  const candidates = [base, ...skipped];
  try { for(const name of fs.readdirSync(path.join(base,'sessions')))if(SLOT.test(name))candidates.push(path.join(base,'sessions',name)); } catch {}
  return [...new Set(candidates)].filter(profile=>{
    if(profile===current)return false;
    try {
      const stat=fs.lstatSync(profile);if(!stat.isDirectory()||stat.isSymbolicLink()||stat.uid!==process.getuid())return false;
      const owner=read(path.join(profile,OWNER),16384);
      if(owner?.state==='running'&&processAlive(owner.pid))return false;
      return skipped.includes(profile)||!reusable(profile,{alive:processAlive,probe:()=>true});
    } catch { return true; }
  });
}
function selectSessionProfile({app, runtime, bootstrap = false, preview = false, argv = process.argv,
  processAlive = alive, probe, run = execFileSync}) {
  if (!app.isPackaged || bootstrap || preview) return {acquired:app.requestSingleInstanceLock(), startAtChooser:false, skipped:[], release(){}};
  const requested = directory(app.getPath('userData'));
  // A validated slot restart (including updater --user-data-dir) returns to its
  // own saved view. Structural recognition also prevents nested roots if its
  // identity record is damaged; that slot will be preserved and skipped.
  const isSlot = path.basename(path.dirname(requested)) === 'sessions' && SLOT.test(path.basename(requested));
  const base = isSlot ? directory(path.dirname(path.dirname(requested))) : requested;
  const sessions = path.join(base, 'sessions');
  const fresh = argv.includes('--disco-new-session');
  const recovery = argv.includes('--disco-recover-session');
  const skipped = [], options = {alive:processAlive, probe:probe || (profile => runtimeLeaseFree(profile,{runtime,run}))};
  const candidates = [];
  if (!fresh) candidates.push(requested);
  if (!fresh && requested !== base) candidates.push(base);
  function invalid(profile) {
    if (recovery && profile === requested) throw Error('This preserved session has an invalid profile identity: ' + profile + '. Its files have been kept.');
    skipped.push(profile); return null;
  }
  function attempt(profile, created = false) {
    try { directory(profile); } catch { return invalid(profile); }
    try {
      const stat = fs.lstatSync(path.join(profile,'backend'));
      if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== process.getuid()) return invalid(profile);
    } catch(error) { if(error.code !== 'ENOENT') return invalid(profile); }
    let identity;
    try { identity = read(path.join(profile, IDENTITY),16384); }
    catch { return invalid(profile); }
    if ((profile !== base && !created && !identity) || (identity && (identity.format !== 'disco-profile' || identity.version !== 1 || identity.root !== base || identity.profile !== profile))) {
      return invalid(profile);
    }
    app.setPath('userData', profile); app.setPath('sessionData', profile);
    if (!app.requestSingleInstanceLock({discoIndependentSession:!recovery})) {
      app.releaseSingleInstanceLock();
      if(recovery && profile===requested)return {acquired:false,startAtChooser:false,skipped,release(){}};
      return null;
    }
    if (!(recovery && profile === requested) && !reusable(profile, options)) {
      skipped.push(profile); app.releaseSingleInstanceLock(); return null;
    }
    try {
      if (created) copyPreferences(base,profile,{runtime,run});
      atomic(path.join(profile,IDENTITY),{format:'disco-profile',version:1,root:base,profile});
      const nonce = randomUUID();
      atomic(path.join(profile,OWNER),{format:'disco-session-owner',version:1,state:'running',pid:process.pid,nonce});
      return {acquired:true,base,profile,skipped,recoverable:()=>preservedProfiles(base,profile,skipped,processAlive),startAtChooser:fresh || profile !== requested,
        release(){try {if(read(path.join(profile,OWNER),16384)?.nonce === nonce) atomic(path.join(profile,OWNER),{format:'disco-session-owner',version:1,state:'released',pid:process.pid,nonce});}catch{} }};
    } catch (error) { app.releaseSingleInstanceLock(); throw error; }
  }
  for (const candidate of candidates) { const selected = attempt(candidate); if (selected) return selected; }
  // A broken sessions container cannot prevent a usable base profile.
  directory(sessions);
  for (const name of fs.readdirSync(sessions).filter(name => SLOT.test(name)).sort((a,b)=>Number(a.slice(8))-Number(b.slice(8)))) {
    const candidate = path.join(sessions,name);
    if (!candidates.includes(candidate)) { const selected = attempt(candidate); if (selected) return selected; }
  }
  // mkdir is atomic: simultaneous launches cannot initialize the same new slot.
  for (let index=0;;index++) {
    const profile = path.join(sessions,'session-'+index);
    try { fs.mkdirSync(profile,{mode:0o700}); }
    catch(error){if(error.code==='EEXIST')continue;throw error;}
    const selected = attempt(profile,true); if(selected)return selected;
  }
}
module.exports = {selectSessionProfile, runtimeLeaseFree};
