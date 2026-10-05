'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {ServiceSupervisor} = require('../supervisor.cjs');
const {localPreview} = require('../local-preview.cjs');

test('supplied resources select the exact packaged executable and entry independently of source location', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'retained-desktop-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  const runtime = path.join(root, 'resources/runtime');
  await fs.mkdir(path.join(runtime, 'python/bin'), {recursive:true});
  await fs.mkdir(path.join(runtime, 'application/python'), {recursive:true});
  const executable = path.join(runtime, 'python/bin/python3.11');
  const entry = path.join(runtime, 'application/python/workspace_desktop.py');
  await fs.writeFile(executable, 'fixture only');
  await fs.writeFile(entry, 'fixture only');
  const manifest = {format:'rieke-desktop-runtime', version:1, platform:process.platform,
    architecture:process.arch, application_version:'1.0.0', source_commit:'a'.repeat(40),
    workspace_formats:[1], database_compatibility:1};
  await fs.writeFile(path.join(runtime, 'runtime-manifest.json'), JSON.stringify(manifest));
  const supervisor = new ServiceSupervisor({resourcesPath:path.join(root, 'resources'),
    userData:path.join(root, 'profile'), appVersion:'1.0.0',
    spawnProcess:() => assert.fail('must not spawn'), request:() => assert.fail('must not request'),
    inspectProcess:() => assert.fail('must not inspect')});
  assert.deepEqual(await supervisor.loadManifest(), manifest);
  assert.equal(supervisor.executable, await fs.realpath(executable));
  assert.equal(supervisor.entry, await fs.realpath(entry));
  assert.equal(supervisor.registryPath, path.join(root, 'profile/desktop-service.json'));
  await fs.unlink(entry);
  await fs.writeFile(path.join(root, 'outside.py'), 'fixture only');
  await fs.symlink(path.join(root, 'outside.py'), entry);
  await assert.rejects(supervisor.loadManifest(), /escapes packaged resources/);
});

test('root control transport rejects unbound, child-origin and non-control requests before using capability', async () => {
  const calls = [];
  const supervisor = new ServiceSupervisor({resourcesPath:'/fixture/resources', userData:'/fixture/profile', appVersion:'1',
    request:async (...args) => { calls.push(args); return {ok:true, json:async () => ({ready:true})}; }});
  supervisor.origin = 'http://127.0.0.1:40001';
  await assert.rejects(supervisor.api('/api/desktop/health'), /listener ownership/);
  supervisor.bound = true;
  await assert.rejects(supervisor.api('/api/desktop/health', {origin:'http://127.0.0.1:40002'}), /exact owned root/);
  await assert.rejects(supervisor.api('/api/project'), /exact owned root/);
  assert.equal(calls.length, 0);
  assert.deepEqual(await supervisor.api('/api/desktop/health'), {ready:true});
  assert.equal(calls[0][0], supervisor.origin + '/api/desktop/health');
  assert.equal(calls[0][1].headers['X-Rieke-Desktop-Capability'], supervisor.capability);
});

test('marked preview requires the isolated profile and returns frozen source-bound identity', () => {
  const root = '/fixture/preview', home = root + '/home', profile = root + '/profile';
  const options = {app:{isPackaged:true, getPath:() => profile, getVersion:() => '1.0.0'},
    executable:home + '/Applications/Disco.app/Contents/MacOS/Disco', platform:'darwin', uid:42,
    env:{HOME:home, TMPDIR:root + '/tmp'}, argv:['electron', '--user-data-dir=' + profile],
    readPlist:() => ({DiscoLocalPreview:true}), filesystem:{
      lstatSync:() => ({isDirectory:() => true, isSymbolicLink:() => false, uid:42}),
      realpathSync:value => value, readFileSync:() => JSON.stringify({format:'rieke-desktop-runtime',
        version:1, application_version:'1.0.0', source_dirty:false, source_commit:'a'.repeat(40)})}};
  const identity = localPreview(options);
  assert.equal(identity.profile, profile);
  assert.equal(identity.source_commit, 'a'.repeat(40));
  assert.equal(Object.isFrozen(identity), true);
  assert.throws(() => localPreview({...options, env:{...options.env, RIEKE_PROJECT_INDEX:'/other/index.json'}}), /isolated home and profile/);
  assert.throws(() => localPreview({...options, argv:[...options.argv, '--user-data-dir=/other']}), /isolated home and profile/);
});
