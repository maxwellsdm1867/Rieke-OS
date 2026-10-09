'use strict';
// All app bytes are inert and every command is injected. No host-tool fallback.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {createHash} = require('node:crypto');
const {applyTestingInstall, sha256} = require('../testing-install.cjs');
const {bundleDigest, readBundleManifest} = require('../bootstrap.cjs');

async function fixture(t) {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'disco-helper-boundaries-')));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const installed = path.join(root, 'Applications/Disco.app');
  const cache = path.join(root, 'profile/updates/unsigned-testing');
  const candidate = path.join(cache, 'candidate-ABC123/Disco.app');
  await fs.mkdir(path.dirname(candidate), {recursive: true, mode: 0o700});
  async function bundle(directory, version) {
    const runtime = path.join(directory, 'Contents/Resources/runtime'), resources = {};
    await fs.mkdir(path.join(directory, 'Contents/MacOS'), {recursive: true});
    await fs.writeFile(path.join(directory, 'Contents/MacOS/Disco'), `inert ${version}`);
    await fs.writeFile(path.join(directory, 'Contents/Info.plist'), 'injected property list');
    for (const relative of ['python/bin/python3.11', 'mysql/bin/mysqld', 'mysql/bin/mysql', 'mysql/bin/mysqldump', 'application/python/workspace_desktop.py']) {
      const file = path.join(runtime, relative), bytes = Buffer.from(`inert ${version}`);
      await fs.mkdir(path.dirname(file), {recursive: true}); await fs.writeFile(file, bytes);
      resources[relative] = {size: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex')};
    }
    await fs.writeFile(path.join(runtime, 'runtime-manifest.json'), JSON.stringify({
      format: 'rieke-desktop-runtime', version: 1, application_version: version, platform: 'darwin', architecture: 'arm64',
      source_commit: 'a'.repeat(40), parser_commit: 'b'.repeat(40), python_version: '3.11.13', mysql_version: '8.4.2',
      minimum_macos_version: '14.0', database_compatibility: 1, workspace_formats: [1], resources,
    }));
  }
  await bundle(installed, '0.1.9'); await bundle(candidate, '0.1.10');
  const archive = path.join(cache, 'candidate.zip'); await fs.writeFile(archive, 'inert archive');
  const executable = path.join(installed, 'Contents/MacOS/Disco');
  const receiptPath = path.join(cache, 'install.json');
  const receipt = {format: 'rieke-unsigned-testing-update', version: 1, channel: 'unsigned-testing', identifier: 'org.riekeos.desktop', validated: true, operation: 'update',
    install_path: installed, current_executable: executable, current_pid: 12345, current_created_at: 17, current_version: '0.1.9', target_version: '0.1.10',
    archive_path: archive, archive_sha256: await sha256(archive), bundle_path: candidate, bundle_sha256: await bundleDigest(candidate),
    runtime_manifest_sha256: await sha256(path.join(candidate, 'Contents/Resources/runtime/runtime-manifest.json')),
    current_manifest_sha256: await sha256(path.join(installed, 'Contents/Resources/runtime/runtime-manifest.json'))};
  await fs.writeFile(receiptPath, JSON.stringify(receipt), {mode: 0o600});
  let identities = 0, ready = 0, opens = 0;
  const hooks = {exit: async () => {}, open: async () => {}};
  const calls = [];
  const run = async (command, args, options) => {
    calls.push([command, args]);
    if (command === path.join(installed, 'Contents/Resources/runtime/python/bin/python3.11')) {
      if (++identities > 1) await hooks.exit();
      return {stdout: 'RIEKE_PROCESS_IDENTITY=' + JSON.stringify(identities === 1 ?
        {pid: 12345, alive: true, created_at: 17, executable} : {pid: 12345, alive: false})};
    }
    if (command === '/usr/bin/codesign') {assert.equal(args[0], '--verify'); assert.ok(args.at(-1).startsWith(root + path.sep)); return {stdout: '', stderr: ''};}
    if (command === '/usr/libexec/PlistBuddy') {
      assert.ok(args[2].startsWith(root + path.sep)); assert.equal(args[0], '-c');
      const manifest = await readBundleManifest(path.dirname(path.dirname(args[2])));
      const fields = {'Print :CFBundleIdentifier': 'org.riekeos.desktop', 'Print :CFBundleExecutable': 'Disco',
        'Print :CFBundleShortVersionString': manifest.application_version, 'Print :LSMinimumSystemVersion': '14.0'};
      assert.ok(Object.hasOwn(fields, args[1])); return {stdout: fields[args[1]], stderr: ''};
    }
    if (command === '/usr/bin/xattr') {assert.ok(args.at(-1).startsWith(root + path.sep)); throw Object.assign(Error('absent'), {code: 1, stderr: 'No such xattr'});}
    if (command === '/usr/bin/sw_vers') {assert.deepEqual(args, ['-productVersion']); return {stdout: '14.2'};}
    if (command === '/bin/ps') {assert.deepEqual(args, ['-axo', 'pid=,comm=']); return {stdout: ''};}
    if (command === '/usr/bin/ditto') {
      assert.deepEqual(args.slice(0, 3), ['--rsrc', '--extattr', '--acl']);
      assert.ok(args[3].startsWith(root + path.sep) && args[4].startsWith(root + path.sep));
      await fs.cp(args[3], args[4], {recursive: true}); return {stdout: ''};
    }
    if (command === '/usr/bin/open') {assert.equal(args[2], installed); await hooks.open(++opens, args, options); return {stdout: ''};}
    assert.fail(`Unexpected command rejected: ${command}`);
  };
  return {root, installed, cache, candidate, receipt, receiptPath, executable, hooks, calls,
    digest: await bundleDigest(installed), ready: () => ready, opens: () => opens,
    apply: (options = {}) => applyTestingInstall({receiptPath, currentExecutable: executable, run, publishReady: () => {ready++;}, ...options})};
}

for (const malformed of ['layout', 'cache-permissions', 'candidate-permissions']) test(`${malformed} rejects before readiness`, async t => {
  const f = await fixture(t);
  if (malformed === 'layout') {
    const relocated = path.join(f.cache, 'Disco.app'); await fs.rename(f.candidate, relocated);
    f.receipt.bundle_path = relocated;
    await fs.writeFile(f.receiptPath, JSON.stringify(f.receipt), {mode: 0o600});
  } else await fs.chmod(malformed === 'cache-permissions' ? f.cache : path.dirname(f.candidate), 0o755);
  await assert.rejects(f.apply(), /private candidate cache|private owned directories/);
  assert.equal(f.ready(), 0); assert.equal(f.opens(), 0);
  assert.equal(await bundleDigest(f.installed), f.digest);
});

test('redirected installation ancestor after readiness cannot replace a different physical app', async t => {
  const f = await fixture(t), originalParent = path.dirname(f.installed);
  const redirected = path.join(f.root, 'RedirectedApplications');
  await fs.cp(originalParent, redirected, {recursive: true});
  f.hooks.exit = async () => {
    await fs.rename(originalParent, originalParent + '-original');
    await fs.symlink(redirected, originalParent);
  };
  await assert.rejects(f.apply(), /resolved paths changed after readiness/);
  assert.equal(f.ready(), 1); assert.equal(f.opens(), 0);
  assert.equal(await bundleDigest(path.join(redirected, 'Disco.app')), f.digest);
  assert.equal(await bundleDigest(path.join(originalParent + '-original', 'Disco.app')), f.digest);
  assert.equal((await readBundleManifest(f.candidate)).application_version, '0.1.10');
});

test('receipt changes after readiness are refused even if filesystem paths are unchanged', async t => {
  const f = await fixture(t);
  f.hooks.exit = async () => {await fs.writeFile(f.receiptPath, JSON.stringify({...f.receipt, current_created_at: 18}), {mode: 0o600});};
  await assert.rejects(f.apply(), /receipt changed after readiness/);
  assert.equal(f.ready(), 1); assert.equal(f.opens(), 0); assert.equal(await bundleDigest(f.installed), f.digest);
});

test('cross-device cache does not prevent launch-failure rollback', async t => {
  const f = await fixture(t), originalLstat = fs.lstat, originalRename = fs.rename;
  // Inject device identities and EXDEV for install→cache. No host mounts are created.
  t.mock.method(fs, 'lstat', async function(file, ...args) {
    const stat = await originalLstat.call(this, file, ...args);
    return file === f.candidate ? Object.assign(Object.create(stat), {dev: stat.dev + 1}) : stat;
  });
  t.mock.method(fs, 'rename', async function(from, to) {
    if (from === f.installed && to.startsWith(f.cache + path.sep)) throw Object.assign(Error('cross-device rollback refused'), {code: 'EXDEV'});
    return originalRename.call(this, from, to);
  });
  f.hooks.open = async count => {if (count === 1) throw Error('candidate launch refused');};
  try {
    const outcome = await f.apply();
    assert.equal(outcome.state, 'Restored'); assert.equal(f.opens(), 2);
    assert.equal(await bundleDigest(f.installed), f.digest);
    assert.equal(f.calls.filter(([command]) => command === '/usr/bin/ditto').length, 1);
    const failed = (await fs.readdir(path.dirname(f.installed))).filter(name => name.startsWith('.Rieke OS.failed-candidate-'));
    assert.equal(failed.length, 1);
    assert.equal((await readBundleManifest(path.join(path.dirname(f.installed), failed[0]))).application_version, '0.1.10');
    assert.equal((await readBundleManifest(f.candidate)).application_version, '0.1.10');
  } finally {t.mock.restoreAll();}
});


test('progress and reporter failures cannot block a verified installation', async t => {
  const f = await fixture(t), events = [];
  const outcome = await f.apply({
    publishProgress: packet => {events.push(packet.phase); throw Error('observer unavailable');},
    onPrepared: () => {events.push('reporter'); throw Error('reporter unavailable');},
    publishReady: () => {events.push('ready');},
  });
  assert.equal(outcome.state, 'Installed');
  assert.equal((await readBundleManifest(f.installed)).application_version, '0.1.10');
  assert.equal(f.opens(), 1);
  assert.deepEqual(events.slice(0, 4), ['validate-prepared', 'reporter', 'ready', 'wait-parent-exit']);
  assert.ok(events.indexOf('validate-after-exit') < events.indexOf('replace-bundle'));
  assert.ok(events.indexOf('replace-bundle') < events.indexOf('save-rollback-receipt'));
  assert.ok(events.indexOf('save-rollback-receipt') < events.indexOf('request-launch'));
});

test('stalled initial progress and reporter promises cannot hold installation indefinitely', {timeout: 5000}, async t => {
  const f = await fixture(t), events = [], never = new Promise(() => {});
  const outcome = await f.apply({
    publishProgress: packet => {events.push(packet.phase); return packet.phase === 'validate-prepared' ? never : undefined;},
    onPrepared: () => {events.push('reporter'); return never;},
    publishReady: () => {events.push('ready');},
  });
  assert.equal(outcome.state, 'Installed');
  assert.equal((await readBundleManifest(f.installed)).application_version, '0.1.10');
  assert.equal(f.opens(), 1);
  assert.deepEqual(events.slice(0, 4), ['validate-prepared', 'reporter', 'ready', 'wait-parent-exit']);
  assert.ok(events.includes('request-launch'));
});


for (const restore of [false, true]) test(`${restore ? 'restored' : 'updated'} GUI launch removes helper Node mode without changing helper environment`, async t => {
  const hadFlag = Object.hasOwn(process.env, 'ELECTRON_RUN_AS_NODE');
  const originalFlag = process.env.ELECTRON_RUN_AS_NODE;
  t.after(() => {
    if (hadFlag) process.env.ELECTRON_RUN_AS_NODE = originalFlag;
    else delete process.env.ELECTRON_RUN_AS_NODE;
  });
  process.env.ELECTRON_RUN_AS_NODE = '1';
  const f = await fixture(t), expectedEnvironment = {...process.env};
  delete expectedEnvironment.ELECTRON_RUN_AS_NODE;
  f.hooks.open = async (count, args, options) => {
    assert.equal(process.env.ELECTRON_RUN_AS_NODE, '1', 'Helper must retain Node mode until it exits');
    assert.ok(options && options.env);
    assert.equal(Object.hasOwn(options.env, 'ELECTRON_RUN_AS_NODE'), false);
    assert.notEqual(options.env, process.env);
    assert.deepEqual(options.env, expectedEnvironment, 'Unrelated launch environment remains intact');
    assert.equal(options.env.HOME, process.env.HOME);
    assert.deepEqual(args, ['-n', '-a', f.installed, '--env', 'HOME=' + os.homedir(), '--args', '--user-data-dir=' + path.dirname(path.dirname(f.cache))]);
    if (restore && count === 1) throw Error('candidate launch refused');
  };
  const outcome = await f.apply();
  assert.equal(outcome.state, restore ? 'Restored' : 'Installed');
  assert.equal(f.opens(), restore ? 2 : 1);
  assert.equal((await readBundleManifest(f.installed)).application_version, restore ? '0.1.9' : '0.1.10');
  assert.equal(process.env.ELECTRON_RUN_AS_NODE, '1');
});
