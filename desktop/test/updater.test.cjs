'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {createUpdateCoordinator} = require('../updater.cjs');
const {compatibleCandidate, compatibleMacMinimum, safeResource, compareVersions, verifyResources, ARCHIVE_CHECK} = require('../updater-validation.cjs');
const manifest = {format: 'rieke-desktop-runtime', version: 1, source_dirty:false,source_commit:'a'.repeat(40),parser_commit:'b'.repeat(40),application_version: '1.0.0', platform: 'darwin', architecture: 'arm64', mysql_version: '8.4.2', workspace_formats: [1], database_compatibility: 1, resources: {'file': {sha256: 'a'.repeat(64), size: 0}}};
test('candidate rejects migrations, downgrades, prereleases and foreign platforms', () => {
  const next = {...manifest, application_version: '1.1.0'};
  assert.equal(compatibleCandidate(next, manifest, '1.1.0'), next);
  for (const patch of [{application_version: '0.9.0'}, {application_version: '1.1.0-beta'}, {mysql_version: '9.0.0'}, {database_compatibility: 2}, {workspace_formats: [2]}, {architecture: 'x64'}, {resources: {}}]) assert.throws(() => compatibleCandidate({...next, ...patch}, manifest, patch.application_version || '1.1.0'));
  assert.equal(compareVersions('1.10.0', '1.9.9'), 1);
  assert.equal(compatibleMacMinimum('14.0','14.2.1'),true);
  assert.throws(()=>compatibleMacMinimum('15.0','14.2.1'));
  for (const unsafe of ['../outside', '/absolute', 'a/../../outside', 'a\\b', 'a//b', './a']) assert.throws(() => safeResource('/tmp/runtime', unsafe));
});
test('resource verification rejects a symlink which resolves outside the bundle', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-resource-test-'));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  await fs.symlink('/etc/hosts', path.join(root, 'escape'));
  await assert.rejects(verifyResources(root, {escape: {symlink: '/etc/hosts'}}), /escapes/);
});
test('archive preflight rejects traversal and escaping symlinks before extraction', async t => {
  const {spawnSync} = require('node:child_process');
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-archive-test-'));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const bundledPython = path.resolve(__dirname, '../build/runtime/python/bin/python3.11');
  const python = require('node:fs').existsSync(bundledPython) ? bundledPython : 'python3';
  const generate = String.raw`
import sys,zipfile,stat
with zipfile.ZipFile(sys.argv[1],'w') as archive:
    kind=sys.argv[2]
    if kind=='traversal': archive.writestr('../escape','data')
    elif kind=='link':
        info=zipfile.ZipInfo('Rieke OS.app/escape');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        archive.writestr(info,'../../escape');archive.writestr('Rieke OS.app/escape/file','data')
    elif kind=='safe':
        archive.writestr('Rieke OS.app/Contents/file','data')
        info=zipfile.ZipInfo('Rieke OS.app/Contents/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        archive.writestr(info,'file')
`;
  for (const kind of ['traversal','link','safe']) {
    const filename = path.join(root, kind+'.zip');
    assert.equal(spawnSync(python,['-I','-B','-c',generate,filename,kind],{encoding:'utf8'}).status,0);
    const result=spawnSync(python,['-I','-B','-c',ARCHIVE_CHECK,filename],{encoding:'utf8'});
    assert.equal(result.status,kind==='safe'?0:1);
  }
});
async function fixture(t, options = {}) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-updater-test-'));
  // Receipt writes are serialized; remove after they have had a turn to settle.
  t.after(async () => {coordinator.stop(); await new Promise(resolve => setTimeout(resolve, 30)); await fs.rm(dir, {recursive: true, force: true});});
  const updater = new EventEmitter();
  updater.setFeedURL = value => {updater.feed = value;};
  updater.checkForUpdates = async () => {};
  let installs = 0, drains = 0;
  updater.quitAndInstall = () => {installs++;};
  const coordinator = createUpdateCoordinator({app: {isPackaged: true, getPath: () => dir}, manifest, updater,
    verifyInstalled: async () => ({team: 'TESTTEAM', identifier: 'org.riekeos.desktop'}),
    verifyCandidate: async ({version}) => ({version, validated: true}),
    retainPrevious: async () => {},
    prepareQuit: async () => {drains++; return {ready: false};},
    timers: {setTimeout: () => 1, clearTimeout: () => {}}, ...options});
  await coordinator.start();
  return {coordinator, updater, installs: () => installs, drains: () => drains};
}
test('source and unsigned builds have no install authority', async t => {
  const {coordinator, updater} = await fixture(t, {enabled: false});
  assert.equal(coordinator.getStatus().state, 'Deferred');
  assert.equal(updater.feed, undefined);
  assert.equal((await coordinator.installPrepared()).ready, false);
});
test('quiet downloads require validation and every drain acknowledgment before install', {skip: process.platform !== 'darwin' || process.arch !== 'arm64'}, async t => {
  let allowDrain = false;
  const {coordinator, updater, installs} = await fixture(t, {prepareQuit: async () => ({ready: allowDrain})});
  assert.equal(updater.autoInstallOnAppQuit, false);
  assert.equal(updater.allowDowngrade, false);
  assert.equal(updater.allowPrerelease, false);
  assert.equal(updater.feed.repo, 'Rieke-OS');
  updater.emit('update-downloaded', {version: '1.1.0', downloadedFile: '/cache/update.zip'});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(coordinator.getStatus().state, 'Ready');
  assert.equal(coordinator.getStatus().native_staging_verified, false);
  assert.equal((await coordinator.installPrepared()).ready, false);
  assert.equal(installs(), 0);
  assert.equal(coordinator.getStatus().state, 'Ready');
  updater.emit('error', new Error('Network failure with secret URL'));
  assert.equal(coordinator.getStatus().state, 'Ready');
  assert.equal(coordinator.getStatus().available, '1.1.0');
  assert.ok(!JSON.stringify(coordinator.getStatus()).includes('secret'));
  allowDrain = true;
  const results = await Promise.all([coordinator.installPrepared(), coordinator.installPrepared()]);
  assert.ok(results.every(result => result.installing));
  assert.equal(installs(), 1);
});
test('rejected candidate never becomes ready or installs', {skip: process.platform !== 'darwin' || process.arch !== 'arm64'}, async t => {
  const {coordinator, updater, installs} = await fixture(t, {verifyCandidate: async () => {throw new Error('invalid signature');}});
  updater.emit('update-downloaded', {version: '1.1.0'});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(coordinator.getStatus().state, 'Deferred');
  assert.equal((await coordinator.installPrepared()).ready, false);
  assert.equal(installs(), 0);
});
test('cache mutation during real drain cannot authorize the native installer', {skip: process.platform !== 'darwin' || process.arch !== 'arm64'}, async t => {
  const crypto=require('node:crypto');
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-drain-cache-test-'));
  t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const downloadedFile=path.join(directory,'candidate.zip');await fs.writeFile(downloadedFile,'verified fixture');
  const archive_sha256=crypto.createHash('sha256').update('verified fixture').digest('hex');
  let recovered=false;
  const {coordinator,updater,installs}=await fixture(t,{
    verifyCandidate:async({version})=>({version,downloadedFile,archive_sha256}),
    prepareQuit:async()=>{await fs.writeFile(downloadedFile,'changed during drain');return {ready:true};},
    onInstallationFailure:()=>{recovered=true;}});
  updater.emit('update-downloaded',{version:'1.1.0'});await new Promise(resolve=>setImmediate(resolve));
  assert.equal((await coordinator.installPrepared()).ready,false);
  assert.equal(installs(),0);assert.equal(recovered,true);assert.equal(coordinator.getStatus().state,'Deferred');
});
