'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {_electron} = require('playwright');
const run = promisify(execFile);
async function createFixture({reuse = true} = {}) {
  if (reuse && process.env.RIEKE_E2E_FIXTURE_ROOT) {
    const root = await fs.realpath(process.env.RIEKE_E2E_FIXTURE_ROOT);
    if (!root.startsWith(await fs.realpath(os.tmpdir()) + path.sep) || !path.basename(root).startsWith('rieke-packaged-ui-e2e-')) throw new Error('Reusable fixture must be an owned isolated test directory');
    const home = path.join(root, 'home'), bundle = path.join(home, 'Applications', 'Rieke OS.app');
    if ((await fs.stat(root)).uid !== process.getuid()) throw new Error('Test directory owner mismatch');
    return {root, home, bundle, userData: path.join(home, 'state'), executable: path.join(bundle, 'Contents/MacOS/Rieke OS'), projects: path.join(home, 'projects')};
  }
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-packaged-ui-e2e-')));
  const home = path.join(root, 'home');
  const bundle = path.join(home, 'Applications', 'Rieke OS.app');
  const userData = path.join(home, 'state');
  await fs.mkdir(path.dirname(bundle), {recursive: true}); await fs.mkdir(userData, {recursive: true});
  await run('/usr/bin/ditto', [path.resolve(__dirname, '../dist/mac-arm64/Rieke OS.app'), bundle]);
  return {root, home, bundle, userData, executable: path.join(bundle, 'Contents/MacOS/Rieke OS'), projects: path.join(home, 'projects')};
}
async function launch(fixture) {
  const application = await _electron.launch({executablePath: fixture.executable, args: [`--user-data-dir=${fixture.userData}`],
    env: {...process.env, HOME: fixture.home, TMPDIR: fixture.root, XDG_CONFIG_HOME: fixture.userData},
    chromiumSandbox: true, bypassCSP: false, timeout: 45000});
  fixture.activeApplication = application;
  const actual = await application.evaluate(({app}) => ({home: process.env.HOME, userData: app.getPath('userData'),
    appPath: app.getAppPath(), packaged: app.isPackaged, pid: process.pid, electronVersion: process.versions.electron}));
  if (actual.home !== fixture.home || actual.userData !== fixture.userData || !actual.appPath.startsWith(fixture.bundle + '/'))
    throw new Error('Application state is not isolated; no UI interactions are permitted');
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
module.exports = {createFixture, launch, gracefulQuit, ownedControl, run};
