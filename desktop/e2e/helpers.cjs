'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {_electron} = require('playwright');
const run = promisify(execFile);
const {packagedSource} = require('./packaged-path.cjs');
const {RuntimeGenerations,runtimeStore}=require('../runtime-generations.cjs');
async function prepareRuntime(fixture,{selectExact=false}={}){
  const packageMetadata=JSON.parse(require('@electron/asar').extractFile(path.join(fixture.bundle,'Contents/Resources/app.asar'),'package.json').toString());
  if(packageMetadata.main!=='entry.cjs')return fixture;
  const frontDoor=fixture.bundle;
  const store=new RuntimeGenerations({root:runtimeStore(fixture.home),python:path.join(frontDoor,'Contents/Resources/runtime/python/bin/python3.11')});
  const generation=await store.stage(frontDoor);
  let current;if(selectExact)try{current=store.current();}catch(error){if(error.code!=='ENOENT')throw error;}
  const activation=await store.activate(generation,current?{rollbackRevision:current.revision}:{}),selected=activation.generation;
  return {...fixture,frontDoor,bundle:selected.bundle,executable:path.join(selected.bundle,'Contents/MacOS/Disco'),runtimeStore:store,generation:selected};
}
async function createFixture({reuse = true, prepare = true} = {}) {
  if (reuse && process.env.RIEKE_E2E_FIXTURE_ROOT) {
    const root = await fs.realpath(process.env.RIEKE_E2E_FIXTURE_ROOT);
    if (!root.startsWith(await fs.realpath(os.tmpdir()) + path.sep) || !path.basename(root).startsWith('rieke-packaged-ui-e2e-')) throw new Error('Reusable fixture must be an owned isolated test directory');
    const home = path.join(root, 'home'), bundle = path.join(home, 'Applications', 'Disco.app');
    if ((await fs.stat(root)).uid !== process.getuid()) throw new Error('Test directory owner mismatch');
    const fixture={root, home, bundle, userData: path.join(home, 'state'), executable: path.join(bundle, 'Contents/MacOS/Disco'), projects: path.join(home, 'projects')};
    return prepare?prepareRuntime(fixture):fixture;
  }
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-packaged-ui-e2e-')));
  const home = path.join(root, 'home');
  const bundle = path.join(home, 'Applications', 'Disco.app');
  const userData = path.join(home, 'state');
  await fs.mkdir(path.dirname(bundle), {recursive: true}); await fs.mkdir(userData, {recursive: true});
  await run('/usr/bin/ditto', [packagedSource(path.resolve(__dirname, '..'), require('../package.json').build), bundle]);
  const fixture={root, home, bundle, userData, executable: path.join(bundle, 'Contents/MacOS/Disco'), projects: path.join(home, 'projects')};
  return prepare?prepareRuntime(fixture):fixture;
}
async function launch(fixture) {
  const prepared=fixture.preparedLaunch||(fixture.runtimeStore?await fixture.runtimeStore.prepareLaunch({profile:fixture.userData,generation:fixture.generation}):null);
  delete fixture.preparedLaunch;
  if(fixture.generation)fixture.generation={...fixture.generation,preparation:undefined};
  const args=prepared?prepared.args.slice(prepared.args.indexOf('--args')+1):[`--user-data-dir=${fixture.userData}`];
  const application = await _electron.launch({executablePath: fixture.executable, args,
    env: {...process.env, HOME: fixture.home, TMPDIR: fixture.root, XDG_CONFIG_HOME: fixture.userData},
    chromiumSandbox: true, bypassCSP: false, timeout: 45000});
  fixture.activeApplication = application;
  const actual = await application.evaluate(({app}) => ({home: process.env.HOME, userData: app.getPath('userData'),
    appPath: app.getAppPath(), packaged: app.isPackaged, pid: process.pid, electronVersion: process.versions.electron}));
  const selectedSlot=fixture.allowSessionSlot===true&&path.dirname(actual.userData)===path.join(fixture.userData,'sessions')&&/^session-(0|[1-9][0-9]*)$/.test(path.basename(actual.userData));
  if (actual.home !== fixture.home || (actual.userData !== fixture.userData&&!selectedSlot) || !actual.appPath.startsWith(fixture.bundle + '/'))
    throw new Error('Application state is not isolated; no UI interactions are permitted');
  if(selectedSlot){fixture.requestedProfile=fixture.userData;fixture.userData=actual.userData;}
  const page = await application.firstWindow({timeout: 45000});
  return {application, page, actual};
}
async function gracefulQuit(application, page) {
  const exited = new Promise(resolve => application.process().once('exit', resolve));
  await page.evaluate(() => { void window.riekeDesktop.quit(); });
  const code = await Promise.race([exited, new Promise((_resolve, reject) => setTimeout(() => reject(new Error('App did not acknowledge orderly exit')), 45000).unref())]);
  if (code !== 0) throw new Error('App exited without a successful orderly shutdown');
}
async function ownedControl(fixture, endpoint, body) {
  const record = JSON.parse(await fs.readFile(path.join(fixture.userData, 'desktop-service.json'), 'utf8'));
  if (!record.executable.startsWith(fixture.bundle + '/')) throw new Error('Service does not belong to this test bundle');
  const command = await run('/bin/ps', ['eww', '-p', String(record.pid), '-o', 'command=']);
  const capability = command.stdout.match(/(?:^|\s)RIEKE_DESKTOP_CAPABILITY=([a-f0-9]{64})(?:\s|$)/)?.[1];
  if (!capability) throw new Error('No capability for the owned test service');
  const response = await fetch(`http://127.0.0.1:${record.port}/api/desktop/${endpoint}`, {method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Rieke-Desktop-Capability': capability, 'X-Workspace-Request': '1', 'Content-Type': 'application/json'},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(35000)});
  const value = await response.json(); if (!response.ok) throw new Error(value.error || 'Owned test control failed'); return value;
}
module.exports = {createFixture, prepareRuntime, launch, gracefulQuit, ownedControl, run};
