'use strict';
// Inert, owned filesystem fixtures. No command is delegated to a host executable.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {createHash} = require('node:crypto');
const {installCompleteBundle, bundleDigest, readBundleManifest} = require('../bootstrap.cjs');

async function fixture(t, {existing = true, channel = 'unsigned-testing', fault = null} = {}) {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'disco-bootstrap-install-')));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const source = path.join(root, 'download', 'Disco.app');
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
  return {root, source, destination, calls, originalDigest,
    install: () => installCompleteBundle({source, destination, run, distribution: {channel}})};
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
