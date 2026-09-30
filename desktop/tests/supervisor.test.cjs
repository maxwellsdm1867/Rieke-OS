'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {EventEmitter} = require('node:events');
const {ServiceSupervisor} = require('../supervisor.cjs');
async function fixture(t, request, {bind = true} = {}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-supervisor-test-')); t.after(() => fs.rm(root, {recursive: true, force: true}));
  const runtime = path.join(root, 'runtime');
  await fs.mkdir(path.join(runtime, 'python', 'bin'), {recursive: true});
  await fs.mkdir(path.join(runtime, 'application', 'python'), {recursive: true});
  await fs.writeFile(path.join(runtime, 'python', 'bin', 'python3.11'), 'interpreter');
  await fs.writeFile(path.join(runtime, 'application', 'python', 'workspace_desktop.py'), 'entry');
  const manifest = {format: 'rieke-desktop-runtime', version: 1, platform: process.platform, architecture: process.arch,
    application_version: '0.1.0', source_commit: 'test-source', workspace_formats: [1], database_compatibility: 1};
  await fs.writeFile(path.join(runtime, 'runtime-manifest.json'), JSON.stringify(manifest));
  const child = new EventEmitter(); child.pid = 123456789; child.stdout = new EventEmitter(); child.stdout.resume = () => {}; let spawned;
  const supervisor = new ServiceSupervisor({resourcesPath: root, userData: path.join(root, 'state'), appVersion: '0.1.0', startupTimeout: 5, drainTimeout: 5,
    spawnProcess: (...args) => {
      spawned = args;
      if (bind) process.nextTick(() => child.stdout.emit('data', Buffer.from('RIEKE_DESKTOP_BOUND=' + JSON.stringify({pid: child.pid, session_id: supervisor.sessionId,
        port: Number(args[1][args[1].indexOf('--port') + 1]), application_version: '0.1.0', source_commit: 'test-source'}) + '\n')));
      return child;
    }, request: (...args) => request(supervisor, child, ...args)});
  return {supervisor, child, manifest, root, spawned: () => spawned};
}
const response = (value, ok = true, status = 200) => ({ok, status, json: async () => value});
test('readiness validates owned process/release/session; launch never relies on PATH', async t => {
  const {supervisor, spawned} = await fixture(t, sup => response({...sup.expectedHealth(), ready: true}));
  assert.match(await supervisor.start(), /^http:\/\/127\.0\.0\.1:/);
  const [executable, args, options] = spawned();
  assert.ok(executable.startsWith(await fs.realpath(supervisor.resourcesPath))); assert.equal(args[0], '-B');
  assert.equal(options.env.PATH, undefined); assert.equal(options.env.PYTHONDONTWRITEBYTECODE, '1');
  assert.notEqual(supervisor.rendererCapability, supervisor.capability);
});
test('occupied port receives zero capability requests without private owned bind handshake', async t => {
  let requests = 0;
  const {supervisor, child} = await fixture(t, () => { requests++; return response({ready: true, pid: 99, session_id: 'foreign'}); }, {bind: false});
  let killed = false; child.kill = () => { killed = true; };
  await assert.rejects(supervisor.start(), /deadline/); assert.equal(supervisor.ready, false); assert.equal(killed, false); assert.equal(requests, 0);
});
test('busy writer drain keeps backend alive and resumes it without kill', async t => {
  const routes = [];
  const {supervisor, child} = await fixture(t, (sup, _child, url) => {
    routes.push(url);
    if (url.endsWith('/drain')) return response({error: 'busy'}, false, 409);
    return response({...sup.expectedHealth(), ready: true});
  });
  child.kill = () => assert.fail('writer must never be killed');
  await supervisor.start(); assert.equal((await supervisor.drain()).ready, false);
  assert.equal(supervisor.exited, false); assert.ok(routes.some(route => route.endsWith('/resume')));
});
test('drain acknowledgement alone cannot authorize replacement until actual process exit', async t => {
  const {supervisor, child} = await fixture(t, (sup, _child, url) => response(url.endsWith('/health') ? {...sup.expectedHealth(), ready: true} : {ready: true}));
  await supervisor.start(); assert.equal((await supervisor.drain()).ready, false);
  child.emit('exit', 0); assert.equal((await supervisor.drain()).ready, true);
});
test('unexpected process crash is never interpreted as a service drain', async t => {
  const {supervisor, child} = await fixture(t, sup => response({...sup.expectedHealth(), ready: true}));
  await supervisor.start(); child.emit('exit', 1);
  assert.equal((await supervisor.drain()).ready, false);
});
test('incompatible manifest is rejected before executing any code', async t => {
  const {supervisor, root, manifest, spawned} = await fixture(t, () => assert.fail('no request allowed'));
  manifest.database_compatibility = 'invalid'; await fs.writeFile(path.join(root, 'runtime', 'runtime-manifest.json'), JSON.stringify(manifest));
  await assert.rejects(supervisor.start(), /compatibility/); assert.equal(spawned(), undefined);
});
test('project authorization uses root validated process proof and never sends control token to child port', async t => {
  const requests = [];
  let childRecord;
  const {supervisor} = await fixture(t, (sup, _child, url, options) => {
    requests.push(url);
    const rootHealth = {...sup.expectedHealth(), ready: true, services: childRecord ? [childRecord] : []};
    if (url.endsWith('/authorize-project')) {
      assert.equal(JSON.parse(options.body).port, 12345);
      return response({record: childRecord, health: {...rootHealth, pid: childRecord.pid,
        project_uuid: childRecord.project_uuid, project_path: childRecord.project_path}});
    }
    return response(rootHealth);
  });
  await supervisor.start();
  childRecord = {pid: 87654321, port: 12345, session_id: supervisor.sessionId, application_version: '0.1.0', source_commit: 'test-source',
    project_uuid: 'ec845d76-ce6a-472e-aed5-b3ad651a06b8', project_path: '/physical/project', bound: true};
  assert.equal(await supervisor.authorizeProjectURL('http://127.0.0.1:12345/'), true);
  assert.ok(requests.every(url => url.startsWith(supervisor.origin + '/')));
  await assert.rejects(supervisor.api('/api/desktop/health', {origin: 'http://127.0.0.1:12345'}));
  childRecord.bound = false;
  assert.equal(await supervisor.authorizeProjectURL('http://127.0.0.1:12345/'), false);
  assert.equal(supervisor.origins.has('http://127.0.0.1:12345'), false);
});
