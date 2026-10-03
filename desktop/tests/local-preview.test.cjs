'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), vm = require('node:vm');
const {EventEmitter} = require('node:events');
const {execFileSync} = require('node:child_process');
const {localPreview} = require('../local-preview.cjs');
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'disco preview ')));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const home = path.join(root, 'home'), profile = path.join(root, 'profile'), tmp = path.join(root, 'tmp');
  const bundle = path.join(home, 'Applications/Disco.app');
  for (const dir of [bundle, profile, tmp, path.join(bundle, 'Contents/Resources/runtime')]) fs.mkdirSync(dir, {recursive:true});
  const manifestPath = path.join(bundle, 'Contents/Resources/runtime/runtime-manifest.json');
  const manifest = {format:'rieke-desktop-runtime', version:1, application_version:'0.1.6', source_dirty:false, source_commit:'6'.repeat(40)};
  fs.writeFileSync(manifestPath, JSON.stringify(manifest));
  const executable = path.join(bundle, 'Contents/MacOS/Disco');
  const app = {isPackaged:true, getPath:() => profile, getVersion:() => '0.1.6'};
  const options = {app, executable, platform:'darwin', env:{HOME:home, TMPDIR:tmp},
    argv:[executable, '--user-data-dir=' + profile], readPlist:() => ({DiscoLocalPreview:true})};
  return {root, home, profile, tmp, bundle, executable, options, manifest, manifestPath};
}
test('unmarked packages and development bypass preview isolation without reading profile state', () => {
  const app = {isPackaged:true, getPath:() => assert.fail('Unmarked app touched profile')};
  assert.equal(localPreview({app, platform:'darwin', readPlist:() => ({})}), null);
  assert.equal(localPreview({app:{isPackaged:false}, readPlist:() => assert.fail('Development read plist')}), null);
});
test('marked package accepts only the owned isolated profile and clean matching manifest', t => {
  const f = fixture(t), result = localPreview(f.options);
  assert.equal(result.label, 'DISCO Preview · 0.1.6 · 66666666');
  assert.equal(result.home, f.home); assert.equal(result.profile, f.profile);
  assert.equal(result.source_commit, f.manifest.source_commit);
});
test('marked package rejects Finder/default-profile launches, overrides, ambiguous arguments and moved bundles', t => {
  const f = fixture(t);
  for (const change of [
    {env:{HOME:os.homedir(), TMPDIR:f.tmp}}, {env:{TMPDIR:f.tmp}},
    {env:{HOME:f.home, TMPDIR:os.tmpdir()}}, {app:{...f.options.app, getPath:() => '/real/profile'}},
    {argv:[]}, {argv:[...f.options.argv, '--user-data-dir=/real/profile']},
    {env:{...f.options.env, RIEKE_PREFERENCES_DIR:'/real/preferences'}},
    {env:{...f.options.env, RIEKE_PROJECT_INDEX:'/real/catalog'}},
    {env:{...f.options.env, RECORDING_WORKSPACE_ROOT:'/real/project'}},
    {executable:path.join(f.root, 'Moved.app/Contents/MacOS/Disco')},
    {readPlist:() => ({DiscoLocalPreview:'true'})}
  ]) assert.throws(() => localPreview({...f.options, ...change}), /Open this DISCO Preview/);
});
test('marked package rejects redirected or foreign-owned state, dirty or mismatched provenance', t => {
  const f = fixture(t);
  fs.rmdirSync(f.profile); fs.symlinkSync(f.tmp, f.profile);
  assert.throws(() => localPreview(f.options), /Open this DISCO Preview/);
  fs.unlinkSync(f.profile); fs.mkdirSync(f.profile);
  assert.throws(() => localPreview({...f.options, uid:process.getuid() + 1}), /Open this DISCO Preview/);
  for (const change of [{source_dirty:true}, {application_version:'0.1.5'}, {source_commit:'bad'}]) {
    fs.writeFileSync(f.manifestPath, JSON.stringify({...f.manifest, ...change}));
    assert.throws(() => localPreview(f.options), /Open this DISCO Preview/);
  }
});
function mainHarness(f, reject = false) {
  const calls = [], handlers = new Map(), app = new EventEmitter();
  Object.assign(app, f.options.app, {enableSandbox(){calls.push('sandbox');}, setName(){calls.push('branding');}, setPath(){calls.push('profile');},
    requestSingleInstanceLock(){calls.push('lock'); return true;}, whenReady:() => new Promise(() => {}), exit:code => calls.push('exit:' + code)});
  const electron = {app, dialog:{showErrorBox:() => calls.push('error-dialog')}, ipcMain:{handle:(name, action) => handlers.set(name, action)}};
  const actualRequire = require('node:module').createRequire(path.join(__dirname, '../main.cjs'));
  const context = {__dirname:path.join(__dirname, '..'), console, process:{...process, execPath:f.executable, env:f.options.env},
    require(name) {
      calls.push('require:' + name);
      if (name === 'electron') return electron;
      if (name === './local-preview.cjs') return {localPreview:() => localPreview({...f.options, app, env:reject ? {} : f.options.env})};
      if (name === 'node:os') return {...os, homedir:() => f.home};
      if (name === './security.cjs') return {...actualRequire(name), validateSender:() => ({})};
      return actualRequire(name);
    }};
  const source = fs.readFileSync(path.join(__dirname, '../main.cjs'), 'utf8');
  const run = () => vm.runInNewContext(source + '\n globalThis.harness={registerIPC,startScientificUI,status,setSupervisor:value=>supervisor=value};', context);
  return {calls, handlers, context, run};
}
test('main rejects unsafe marked launch before branding, lock, bootstrap or further module initialization', t => {
  const h = mainHarness(fixture(t), true);
  assert.throws(h.run, /Open this DISCO Preview/);
  assert.deepEqual(h.calls, ['require:electron', 'require:./local-preview.cjs', 'error-dialog', 'exit:1']);
});
test('marked scientific startup never constructs an updater; install/update/restore IPC remains blocked', async t => {
  const f = fixture(t), h = mainHarness(f); h.run();
  const api = h.context.harness;
  api.setSupervisor({start:async() => 'http://127.0.0.1:12345'});
  await api.startScientificUI(); api.registerIPC();
  assert.equal(h.calls.some(name => /require:\.\/(?:testing-)?updater\.cjs/.test(name)), false);
  const status = api.status();
  assert.equal(status.local_preview, true); assert.equal(status.installed, '0.1.6');
  assert.equal(status.source_commit, f.manifest.source_commit);
  assert.equal(status.can_download, false); assert.equal(status.can_restart, false);
  for (const channel of ['desktop:download-update', 'desktop:restart-to-update', 'desktop:restore-previous', 'desktop:install-and-open'])
    await assert.rejects(h.handlers.get(channel)({}), /disabled in DISCO Preview/);
});
test('preview builder adds the marker/display label and keeps production/helper identity and runtime closure', () => {
  const {build} = require('../package.json'), preview = require('../preview-builder.cjs');
  assert.equal(build.mac.extendInfo.DiscoLocalPreview, undefined);
  assert.equal(preview.mac.extendInfo.DiscoLocalPreview, true);
  assert.equal(preview.mac.extendInfo.CFBundleDisplayName, 'DISCO Preview');
  assert.equal(build.mac.extendInfo.CFBundleDisplayName, 'Disco');
  assert.equal(preview.appId, build.appId);
  assert.equal(preview.mac.extendInfo.CFBundleName, build.mac.extendInfo.CFBundleName);
  assert.deepEqual(preview.files, build.files); assert.deepEqual(preview.extraResources, build.extraResources);
});
test('launcher executes from a spaced portable folder with a clean environment and explicit profile', {skip:process.platform !== 'darwin'}, t => {
  const f = fixture(t), launcher = path.join(f.root, 'Open DISCO Preview.command');
  fs.copyFileSync(path.join(__dirname, '../preview-launcher.command'), launcher);
  fs.mkdirSync(path.dirname(f.executable), {recursive:true});
  fs.writeFileSync(f.executable, '#!/bin/sh\n/usr/bin/env\nprintf "PROFILE_ARG=%s\\n" "$1"\n');
  fs.chmodSync(f.executable, 0o755);
  const info = path.join(f.bundle, 'Contents/Info.plist');
  execFileSync('/usr/bin/plutil', ['-create', 'xml1', info]);
  execFileSync('/usr/bin/plutil', ['-insert', 'DiscoLocalPreview', '-bool', 'true', info]);
  const output = execFileSync('/bin/zsh', ['-f', launcher], {encoding:'utf8', env:{...process.env,
    HOME:'/real/home', RIEKE_PREFERENCES_DIR:'/real/preferences', RIEKE_PROJECT_INDEX:'/real/catalog', RECORDING_WORKSPACE_ROOT:'/real/project'}});
  assert.ok(output.includes('HOME=' + f.home + '\n'));
  assert.ok(output.includes('TMPDIR=' + f.tmp + '\n'));
  assert.ok(output.includes('PROFILE_ARG=--user-data-dir=' + f.profile + '\n'));
  assert.ok(output.includes('DISCO Preview · 0.1.6 · source ' + f.manifest.source_commit));
  assert.doesNotMatch(output, /RIEKE_PREFERENCES_DIR=|RIEKE_PROJECT_INDEX=|RECORDING_WORKSPACE_ROOT=|\/real\//);
  fs.rmdirSync(f.profile); fs.symlinkSync(f.tmp, f.profile);
  assert.throws(() => execFileSync('/bin/zsh', ['-f', launcher], {stdio:'pipe'}), /Command failed/);
});
