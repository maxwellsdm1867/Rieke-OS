'use strict';
// Inert, owned filesystem fixtures. No command is delegated to a host executable.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {createHash} = require('node:crypto');
const {installCompleteBundle, bundleDigest, readBundleManifest} = require('../bootstrap.cjs');

async function fixture(t, {existing = true, channel = 'unsigned-testing', fault = null, prepared = false} = {}) {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'disco-bootstrap-install-')));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const cache = path.join(root, 'profile/updates/unsigned-testing');
  const source = prepared ? path.join(cache, 'candidate-ABC123/Disco.app') : path.join(root, 'download', 'Disco.app');
  if (prepared) {
    await fs.mkdir(path.dirname(source), {recursive: true, mode: 0o700});
    await fs.chmod(cache, 0o700); await fs.chmod(path.dirname(source), 0o700);
  }
  const destination = path.join(root, 'Applications', 'Disco.app');
  const calls = [];
  async function makeBundle(bundle, version) {
    const runtime = path.join(bundle, 'Contents/Resources/runtime'), resources = {};
    await fs.mkdir(path.join(bundle, 'Contents/MacOS'), {recursive: true});
    await fs.writeFile(path.join(bundle, 'Contents/MacOS/Disco'), `inert ${version}`);
    await fs.writeFile(path.join(bundle, 'Contents/Info.plist'), 'inert plist fixture');
    for (const name of ['python/bin/python3.11', 'mysql/bin/mysqld', 'mysql/bin/mysql', 'mysql/bin/mysqldump', 'application/python/workspace_desktop.py']) {
      const file = path.join(runtime, name), bytes = Buffer.from(`inert resource ${version}`);
      await fs.mkdir(path.dirname(file), {recursive: true}); await fs.writeFile(file, bytes);
      resources[name] = {size: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex')};
    }
    await fs.writeFile(path.join(runtime, 'runtime-manifest.json'), JSON.stringify({
      format: 'rieke-desktop-runtime', version: 1, application_version: version,
      source_commit: 'a'.repeat(40), parser_commit: 'b'.repeat(40), platform: 'darwin', architecture: 'arm64',
      mysql_version: '8.4.2', python_version: '3.11.13', minimum_macos_version: '14.0',
      workspace_formats: [1], database_compatibility: 1, resources,
    }));
  }
  await makeBundle(source, '0.1.10');
  if (existing) await makeBundle(destination, '0.1.9');
  const originalDigest = existing ? await bundleDigest(destination) : null;
  const run = async (command, args) => {
    calls.push([command, args]);
    if (command === '/usr/bin/codesign') {
      const bundle = args.at(-1);
      assert.ok(bundle.startsWith(root + path.sep));
      assert.ok(['--verify', '--display'].includes(args[0]));
      const version = (await readBundleManifest(bundle)).application_version;
      if (args[0] === '--verify' && ((fault === 'activation' && bundle === destination && version === '0.1.10') ||
          (fault === 'staging' && path.basename(bundle).startsWith('.Rieke OS.install-')) ||
          (fault === 'source' && bundle === source))) throw new Error(`injected ${fault} signature failure`);
      return {stdout: '', stderr: args[0] === '--display' ?
        'Identifier=org.riekeos.desktop\nTeamIdentifier=OWNED123\nAuthority=Developer ID Application: Fixture' : ''};
    }
    if (command === '/usr/libexec/PlistBuddy') {
      assert.ok(args[2].startsWith(root + path.sep)); assert.equal(args[0], '-c');
      const manifest = await readBundleManifest(path.dirname(path.dirname(args[2])));
      const fields = {'Print :CFBundleIdentifier': 'org.riekeos.desktop', 'Print :CFBundleExecutable': 'Disco',
        'Print :CFBundleShortVersionString': manifest.application_version, 'Print :LSMinimumSystemVersion': '14.0'};
      assert.ok(Object.hasOwn(fields, args[1])); return {stdout: fields[args[1]], stderr: ''};
    }
    if (command === '/usr/bin/ditto') {
      assert.deepEqual(args.slice(0, 3), ['--rsrc', '--extattr', '--acl']); assert.equal(args[3], source);
      assert.equal(path.dirname(args[4]), path.dirname(destination));
      await fs.cp(source, args[4], {recursive: true}); return {stdout: '', stderr: ''};
    }
    if (command === '/usr/bin/xattr') {
      assert.deepEqual(args.slice(0, 2), ['-px', 'com.apple.quarantine']);
      assert.ok(args[2].startsWith(root + path.sep));
      throw Object.assign(new Error('no fixture quarantine'), {code: 1, stderr: 'No such xattr'});
    }
    if (command === '/bin/ps') {assert.deepEqual(args, ['-axo', 'pid=,comm=']); return {stdout: '', stderr: ''};}
    if (command === '/usr/bin/sw_vers') {assert.deepEqual(args, ['-productVersion']); return {stdout: '14.2', stderr: ''};}
    if (command === '/usr/sbin/spctl') {
      assert.deepEqual(args.slice(0, 3), ['--assess', '--type', 'execute']);
      assert.ok(args[3].startsWith(root + path.sep)); return {stdout: '', stderr: ''};
    }
    assert.fail(`Unexpected command rejected: ${command}`);
  };
  const expectedBundleSha256 = await bundleDigest(source);
  return {root, source, destination, calls, originalDigest, cache, run,
    install: (options = {}) => installCompleteBundle({source, destination, run, distribution: {channel},
      ...(prepared ? {preparedCache: cache, expectedBundleSha256} : {}), ...options})};
}

for (const channel of ['signed', 'unsigned-testing']) {
  test(`${channel}: final identity failure restores original complete bundle`, async t => {
    const f = await fixture(t, {channel, fault: 'activation'});
    await assert.rejects(f.install(), /injected activation signature failure/);
    assert.equal(await bundleDigest(f.destination), f.originalDigest);
    assert.deepEqual(await fs.readdir(path.dirname(f.destination)), ['Disco.app']);
    assert.equal((await readBundleManifest(f.source)).application_version, '0.1.10');
  });
  test(`${channel}: failed first installation leaves no rejected canonical app`, async t => {
    const f = await fixture(t, {channel, fault: 'activation', existing: false});
    await assert.rejects(f.install(), /injected activation signature failure/);
    assert.deepEqual(await fs.readdir(path.dirname(f.destination)), []);
  });
  test(`${channel}: successful replacement retains original and verifies source once`, async t => {
    const f = await fixture(t, {channel});
    const result = await f.install();
    assert.equal(result.destination, f.destination);
    assert.equal((await readBundleManifest(f.destination)).application_version, '0.1.10');
    assert.equal(await bundleDigest(result.previous), f.originalDigest);
    const checks = f.calls.filter(([command, args]) => command === '/usr/bin/codesign' && args[0] === '--verify');
    assert.equal(checks.filter(([, args]) => args.at(-1) === f.source).length, 1);
    assert.equal(checks.filter(([, args]) => args.at(-1) === f.destination).length, channel === 'signed' ? 2 : 1);
    assert.equal(f.calls.filter(([command]) => command === '/usr/sbin/spctl').length, channel === 'signed' ? 1 : 0);
  });
}
for (const fault of ['source', 'staging']) test(`${fault} seal failure preserves original app`, async t => {
  const f = await fixture(t, {fault});
  await assert.rejects(f.install(), new RegExp(`injected ${fault} signature failure`));
  assert.equal(await bundleDigest(f.destination), f.originalDigest);
  assert.deepEqual(await fs.readdir(path.dirname(f.destination)), ['Disco.app']);
});


async function currentHash(f) {
  return createHash('sha256').update(await fs.readFile(path.join(f.destination, 'Contents/Resources/runtime/runtime-manifest.json'))).digest('hex');
}

test('prepared same-volume source is consumed without copy and old digest is retained', async t => {
  const f = await fixture(t, {prepared: true});
  const result = await f.install({expectedCurrentManifestSha256: await currentHash(f), retainPreviousDigest: true});
  assert.equal(result.previousDigest, f.originalDigest);
  assert.equal(await bundleDigest(result.previous), f.originalDigest);
  await assert.rejects(fs.lstat(f.source), {code: 'ENOENT'});
  assert.equal((await readBundleManifest(f.destination)).application_version, '0.1.10');
  assert.equal(f.calls.filter(([command]) => command === '/usr/bin/ditto').length, 0);
  assert.equal(f.calls.filter(([command, args]) => command === '/usr/bin/codesign' && args[0] === '--verify').length, 2);
  assert.ok(f.calls.some(([command, args]) => command === '/usr/bin/xattr' && args.at(-1) === f.destination));
});

for (const failure of ['activation', 'rename', 'quarantine']) test(`prepared ${failure} failure preserves both original app and candidate`, async t => {
  const f = await fixture(t, {prepared: true, fault: failure === 'activation' ? 'activation' : null});
  const sourceDigest = await bundleDigest(f.source), originalRename = fs.rename;
  if (failure === 'rename') fs.rename = async function(from, to) {
    if (from === f.source && to === f.destination) throw Object.assign(new Error('injected activation rename failure'), {code: 'EIO'});
    return originalRename.call(this, from, to);
  };
  const run = async (command, args) => {
    if (failure === 'quarantine' && command === '/usr/bin/xattr' && args.at(-1) === f.destination) return {stdout: 'abcd', stderr: ''};
    return f.run(command, args);
  };
  try {await assert.rejects(f.install({run}), /injected activation|quarantine attribute differs/);}
  finally {fs.rename = originalRename;}
  assert.equal(await bundleDigest(f.source), sourceDigest);
  assert.equal(await bundleDigest(f.destination), f.originalDigest);
  assert.deepEqual(await fs.readdir(path.dirname(f.destination)), ['Disco.app']);
});

test('prepared cache requires ownership, private directories, exact layout, and expected digest', async t => {
  const f = await fixture(t, {prepared: true});
  await assert.rejects(f.install({expectedBundleSha256: undefined}), /expected bundle checksum/);
  await assert.rejects(f.install({preparedCache: path.dirname(f.cache)}), /directly inside/);
  for (const directory of [f.cache, path.dirname(f.source)]) {
    await fs.chmod(directory, 0o755);
    await assert.rejects(f.install(), /private owned/);
    await fs.chmod(directory, 0o700);
  }
  const originalLstat = fs.lstat;
  fs.lstat = async function(file, ...args) {
    const stat = await originalLstat.call(this, file, ...args);
    return file === f.cache ? Object.assign(Object.create(stat), {uid: process.getuid() + 1}) : stat;
  };
  try {await assert.rejects(f.install(), /private owned/);}
  finally {fs.lstat = originalLstat;}
  assert.equal(await bundleDigest(f.destination), f.originalDigest);
});

for (const target of ['cache', 'candidate', 'bundle']) test(`prepared ${target} symlink is refused without changes`, async t => {
  const f = await fixture(t, {prepared: true});
  const directory = target === 'cache' ? f.cache : target === 'candidate' ? path.dirname(f.source) : f.source;
  const retained = directory + '-real';
  await fs.rename(directory, retained); await fs.symlink(retained, directory);
  await assert.rejects(f.install(), /without links/);
  assert.equal(await bundleDigest(f.destination), f.originalDigest);
  assert.equal((await readBundleManifest(f.source)).application_version, '0.1.10');
});

test('different-device prepared source uses copied-staging proof and remains cached', async t => {
  const f = await fixture(t, {prepared: true}), originalLstat = fs.lstat;
  // Device identity is injected; this proves fallback selection, not a native cross-volume rename.
  fs.lstat = async function(file, ...args) {
    const stat = await originalLstat.call(this, file, ...args);
    return file === f.source ? Object.assign(Object.create(stat), {dev: stat.dev + 1}) : stat;
  };
  let result;
  try {result = await f.install({retainPreviousDigest: true, expectedCurrentManifestSha256: await currentHash(f)});}
  finally {fs.lstat = originalLstat;}
  assert.equal(f.calls.filter(([command]) => command === '/usr/bin/ditto').length, 1);
  assert.equal((await readBundleManifest(f.source)).application_version, '0.1.10');
  assert.equal(result.previousDigest, f.originalDigest);
  assert.equal(await bundleDigest(result.previous), f.originalDigest);
});

test('expected current manifest mismatch or absent installation rejects before replacement', async t => {
  const f = await fixture(t, {prepared: true});
  const expectedCurrentManifestSha256 = await currentHash(f);
  await fs.appendFile(path.join(f.destination, 'Contents/Resources/runtime/runtime-manifest.json'), ' ');
  await assert.rejects(f.install({expectedCurrentManifestSha256, retainPreviousDigest: true}), /Installed runtime manifest differs/);
  await fs.rm(f.destination, {recursive: true});
  await assert.rejects(f.install({expectedCurrentManifestSha256, retainPreviousDigest: true}), {code: 'ENOENT'});
  assert.equal((await readBundleManifest(f.source)).application_version, '0.1.10');
  assert.equal(f.calls.filter(([command]) => command === '/usr/bin/ditto').length, 0);
});

test('prepared directory inode change before activation refuses replacement', async t => {
  const f = await fixture(t, {prepared: true}), old = path.dirname(f.source) + '-old'; let changed = false;
  const run = async (command, args) => {
    if (command === '/bin/ps' && !changed) {
      changed = true; await fs.rename(path.dirname(f.source), old);
      await fs.mkdir(path.dirname(f.source), {mode: 0o700});
      await fs.rename(path.join(old, 'Disco.app'), f.source);
    }
    return f.run(command, args);
  };
  await assert.rejects(f.install({run}), /Prepared cache path identity changed/);
  assert.equal(await bundleDigest(f.destination), f.originalDigest);
  assert.equal((await readBundleManifest(f.source)).application_version, '0.1.10');
});

for (const relative of ['Contents/Resources/runtime/mysql/bin/mysql', 'Contents/MacOS/Disco']) test(`prepared same-inode mutation during current verification rejects: ${relative}`, async t => {
  const f = await fixture(t, {prepared: true}), file = path.join(f.source, relative);
  const originalFile = await fs.stat(file), originalBundle = await fs.stat(f.source);
  let mutated = false;
  const run = async (command, args) => {
    if (!mutated && command === '/usr/libexec/PlistBuddy' && args[2] === path.join(f.destination, 'Contents/Info.plist')) {
      mutated = true;
      assert.ok(f.calls.some(([priorCommand, priorArgs]) => priorCommand === '/usr/bin/codesign' && priorArgs.at(-1) === f.source));
      const bytes = await fs.readFile(file); bytes[0] ^= 1;
      await fs.writeFile(file, bytes); // Same inode and size: path identity alone cannot detect this.
    }
    return f.run(command, args); // Signature adapter deliberately still accepts the candidate.
  };
  await assert.rejects(f.install({run, retainPreviousDigest: true, expectedCurrentManifestSha256: await currentHash(f)}),
    /Runtime resource checksum failed|Downloaded application bundle checksum differs/);
  assert.equal(mutated, true);
  assert.equal((await fs.stat(file)).ino, originalFile.ino);
  assert.equal((await fs.stat(file)).size, originalFile.size);
  assert.equal((await fs.stat(f.source)).ino, originalBundle.ino);
  assert.equal(await bundleDigest(f.destination), f.originalDigest);
  assert.deepEqual(await fs.readdir(path.dirname(f.destination)), ['Disco.app']);
  assert.equal(f.calls.filter(([command]) => command === '/usr/bin/ditto').length, 0);
});
