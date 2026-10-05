'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {EventEmitter} = require('node:events');
const {StartupSession} = require('../startup/startup-session.cjs');
const {pathToFileURL} = require('node:url');

const projectId = '00000000-0000-0000-0000-000000000001';
const launcher = 'http://127.0.0.1:41001';
const project = 'http://127.0.0.1:41002';
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };
const plain = value => JSON.parse(JSON.stringify(value));

// Exercise registered IPC composition, including real sender validation and
// StartupSession claim semantics. Electron/transport doubles, a controlled clock
// and shortened Quit deadlines keep the test local: no listener, child process,
// user profile or project is opened.
function fixture(options = {}) {
  const handlers = new Map(), calls = [], navigation = [], messages = [];
  let now = 0, quits = 0;
  const app = new EventEmitter();
  Object.assign(app, {enableSandbox() {}, setName() {}, setPath() {},
    getPath: () => '/unused/disco-characterization', getVersion: () => '0.1.8',
    isPackaged: false, requestSingleInstanceLock: () => true,
    whenReady: () => new Promise(() => {}), quit() { quits++; }});
  class Window extends EventEmitter {
    constructor() {
      super(); this.webContents = new EventEmitter();
      Object.assign(this.webContents, {mainFrame: {url: launcher}, getURL: () => this.webContents.mainFrame.url,
        send: (channel, value) => messages.push({channel, value}), setWindowOpenHandler() {}});
    }
    isDestroyed() { return false; }
    async loadFile(file) { this.webContents.mainFrame.url = pathToFileURL(file).href; }
    async loadURL(url) { navigation.push(url); this.webContents.mainFrame.url = url; }
  }
  const record = {bound: true, project_uuid: projectId, project_path: '/owned/saved-project', port: 41002, pid: 200, created_at: 123, ...options.record};
  const expected = {pid: 100, session_id: 'owned-session', ready: true};
  const supervisor = {
    origin: launcher, origins: new Set([launcher]), capability: 'test-private-capability',
    registry: {services: options.missingRecord ? [] : [record]}, ready: true,
    expectedHealth: () => expected,
    async api(route, settings) {
      calls.push({route, settings});
      if (route === '/api/desktop/open-project') return options.open ? options.open() : {url: project + '/workspace'};
      if (route === '/api/desktop/health') return options.health ? options.health() : {...expected, services: []};
      throw Error('Unexpected transport route: ' + route);
    },
    async authorizeProjectURL(url) {
      calls.push({authorize: url});
      const allowed = options.authorize ? await options.authorize(url) : true;
      if (allowed) this.origins.add(new URL(url).origin);
      return allowed;
    },
  };
  const startupSession = new StartupSession('/unused/disco-characterization', '0.1.8:view-v1');
  startupSession.value = {format: 'disco-startup-session', version: 1, compatibility: startupSession.compatibility,
    mode: 'resume', projectId, projectPath: '/owned/saved-project', view: 'cell-qc'};
  const actualRequire = require('node:module').createRequire(path.join(__dirname, '../main.cjs'));
  const electron = {app, BrowserWindow: Window, ipcMain: {handle: (name, handler) => handlers.set(name, handler)},
    dialog: {}, session: {}, shell: {}, Menu: {}, powerMonitor: {}};
  const context = {require: name => name === 'electron' ? electron : name === './close/quit-coordinator.cjs'
      ? {QuitCoordinator: class extends actualRequire(name).QuitCoordinator {
        constructor(settings) { super({...settings, deadline: 25, draftDeadline: 5}); }
      }} : actualRequire(name),
    __dirname: path.join(__dirname, '..'), process, console, URL, AbortSignal,
    Date: class extends Date { static now() { return now; } },
    setTimeout: callback => { now += 11000; return setTimeout(callback, 0); }, clearTimeout,
    async fetch(url, settings) {
      calls.push({close: url, settings});
      return options.close ? options.close() : {ok: true, json: async () => ({state: 'closed'})};
    }, seed: {supervisor, startupSession}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../main.cjs'), 'utf8') + `
    supervisor=seed.supervisor; startupSession=seed.startupSession;
    registerIPC(); globalThis.window=createWindow();
  `, context);
  const window = context.window;
  window.webContents.mainFrame.url = launcher;
  return {supervisor, startupSession, record, calls, navigation, messages, window,
    get quits() { return quits; },
    invoke(channel, payload) {
      return handlers.get('desktop:' + channel)({sender: window.webContents, senderFrame: window.webContents.mainFrame}, payload);
    }};
}
async function claim(h) { assert.equal((await h.invoke('startup-session')).projectId, projectId); }

test('registered restoration claims once from chooser and opens exact saved identity only after authorization', async () => {
  const gate = deferred();
  const h = fixture({authorize: () => gate.promise});
  h.supervisor.origins.add(project); h.window.webContents.mainFrame.url = project;
  assert.equal(await h.invoke('startup-session'), null);
  h.window.webContents.mainFrame.url = launcher;
  await claim(h); assert.equal(await h.invoke('startup-session'), null);
  const opening = h.invoke('open-startup');
  await new Promise(setImmediate);
  assert.deepEqual(h.navigation, []);
  assert.deepEqual(plain(h.calls[0]), {route: '/api/desktop/open-project', settings: {
    method: 'POST', body: {directory: '/owned/saved-project', project_uuid: projectId}, timeout: 90000}});
  await assert.rejects(h.invoke('open-startup'), /No startup restoration is active/);
  gate.resolve(true);
  assert.deepEqual(plain(await opening), {restored: true});
  assert.deepEqual(h.navigation, [project]);
  assert.equal(h.calls.filter(call => call.close).length, 0);
  h.window.webContents.mainFrame.url = launcher;
  await assert.rejects(h.invoke('open-startup'), /No startup restoration is active/);
});

test('registered startup operations reject payloads and cancellation before open never starts a child', async () => {
  const h = fixture();
  await assert.rejects(h.invoke('startup-session', {}), /accepts no payload/);
  await claim(h);
  await assert.rejects(h.invoke('open-startup', {}), /accepts no payload/);
  await h.invoke('cancel-startup');
  assert.deepEqual(plain(await h.invoke('open-startup')), {restored: false});
  assert.deepEqual(h.calls, []); assert.deepEqual(h.navigation, []);
  assert.equal(h.startupSession.value.mode, 'resume');
});

test('ownership rejection never navigates or sends privileged child cleanup', async () => {
  const h = fixture({authorize: () => false}); await claim(h);
  await assert.rejects(h.invoke('open-startup'), /failed ownership verification/);
  assert.deepEqual(h.navigation, []);
  assert.equal(h.calls.some(call => call.close), false);
  assert.equal(h.supervisor.origins.has(project), false);
});

for (const [identity, record] of [['UUID', {project_uuid: '00000000-0000-0000-0000-000000000002'}],
  ['canonical path', {project_path: '/owned/copied-project'}]]) {
  test(`restoration rejects changed ${identity} after confirmed child cleanup`, async () => {
    const h = fixture({record}); await claim(h);
    await assert.rejects(h.invoke('open-startup'), /saved project identity changed/);
    assert.deepEqual(h.navigation, []);
    assert.equal(h.calls.filter(call => call.close).length, 1);
    assert.equal(h.supervisor.origins.has(project), false);
    assert.equal(h.supervisor.registry.services[0], h.record);
  });
}

test('cancellation during accepted open closes the owned child and requires exact process disappearance', async () => {
  const gate = deferred(); let polls = 0;
  const h = fixture({open: () => gate.promise, health: () => ({services: ++polls === 1
    ? [{pid: 200, created_at: 123}] : [{pid: 200, created_at: 456}]})});
  await claim(h); const opening = h.invoke('open-startup');
  await h.invoke('cancel-startup'); gate.resolve({url: project});
  assert.deepEqual(plain(await opening), {restored: false, closed: true});
  assert.equal(polls, 2); assert.deepEqual(h.navigation, []);
  const close = h.calls.find(call => call.close);
  assert.equal(close.close, project + '/api/project/close');
  assert.equal(close.settings.method, 'POST'); assert.equal(close.settings.body, '{}');
  assert.equal(close.settings.headers['X-Rieke-Desktop-Capability'], 'test-private-capability');
  assert.equal(close.settings.headers['X-Workspace-Request'], '1');
  assert.equal(h.supervisor.origins.has(project), false);
  assert.equal(h.supervisor.registry.services[0], h.record);
  assert.equal(h.startupSession.value.mode, 'resume');
});

for (const [failure, options, error] of [
  ['missing ownership record', {missingRecord: true}, /ownership is unavailable/],
  ['refused close', {close: () => ({ok: false, json: async () => ({state: 'closed'})})}, /cleanup requires recovery/],
  ['unconfirmed close', {close: () => ({ok: true, json: async () => ({state: 'closing'})})}, /cleanup requires recovery/],
  ['close acknowledged but process remains', {health: () => ({services: [{pid: 200, created_at: 123}]})}, /has not exited/],
]) {
  test(`cancelled restoration retains recovery evidence on ${failure}`, async () => {
    const gate = deferred(); const h = fixture({...options, open: () => gate.promise});
    await claim(h); const opening = h.invoke('open-startup');
    await h.invoke('cancel-startup'); gate.resolve({url: project});
    await assert.rejects(opening, error);
    assert.deepEqual(h.navigation, []); assert.equal(h.supervisor.origins.has(project), true);
    assert.equal(h.supervisor.registry.services.length, options.missingRecord ? 0 : 1);
    await assert.rejects(h.invoke('open-startup'), /No startup restoration is active/);
  });
}

test('cancellation while URL authorization is pending is checked before navigation', async () => {
  const gate = deferred(); const h = fixture({authorize: () => gate.promise});
  await claim(h); const opening = h.invoke('open-startup');
  await new Promise(setImmediate); await h.invoke('cancel-startup'); gate.resolve(true);
  assert.deepEqual(plain(await opening), {restored: false, closed: true});
  assert.deepEqual(h.navigation, []);
});

test('registered recovery retry refuses an existing backend with mismatched readiness identity', async () => {
  const h = fixture({health: () => ({pid: 101, session_id: 'other', ready: true})});
  h.supervisor.child = {pid: 100}; h.supervisor.exited = false;
  await h.invoke('retry-startup');
  assert.equal((await h.invoke('status')).state, 'Recovery');
  assert.match((await h.invoke('status')).detail, /not ready for recovery/);
  assert.deepEqual(h.navigation, []);
});

test('registered repeated Quit stays bounded while accepted startup is pending and retains unconfirmed cleanup', {timeout: 2000}, async () => {
  const h = fixture({open: () => new Promise(() => {})});
  let cleanups = 0, pendingStartup;
  h.supervisor.quit = async options => { cleanups++; pendingStartup = options.startup; await options.startup; return {ready: true}; };
  await claim(h); void h.invoke('open-startup');
  const first = h.invoke('quit'), second = h.invoke('quit');
  const result = await first;
  assert.deepEqual(plain(await second), plain(result));
  assert.equal(cleanups, 1); assert.equal(h.quits, 1);
  assert.equal(typeof pendingStartup?.then, 'function');
  assert.equal(result.clean, false); assert.equal(result.services_closed, false);
  assert.match(result.warnings.join(' '), /cleanup exceeded the quit deadline/);
  assert.equal(h.startupSession.cancelled, true);
  assert.deepEqual(h.navigation, []);
  assert.equal(h.supervisor.registry.services[0], h.record);
  await assert.rejects(h.invoke('open-startup'), /closing; new work is paused/);
});
