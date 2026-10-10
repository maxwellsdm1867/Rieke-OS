'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {createHash} = require('node:crypto');
const {bundleDigest, installCompleteBundle} = require('../bootstrap.cjs');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
async function fixture(t) {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'disco-digest-')));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const bundle = path.join(root, 'Disco.app'), runtime = path.join(bundle, 'Contents/Resources/runtime');
  await fs.mkdir(runtime, {recursive: true});
  for (const name of ['Contents', 'Contents/Resources', 'Contents/Resources/runtime']) await fs.chmod(path.join(bundle, name), 0o755);
  const payload = Buffer.from('original resource');
  await fs.writeFile(path.join(runtime, 'payload'), payload, {mode: 0o755});
  await fs.chmod(path.join(runtime, 'payload'), 0o755);
  const manifest = {resources: {payload: {size: payload.length, sha256: sha(payload), executable: true}}};
  async function seal() {
    const raw = Buffer.from(JSON.stringify(manifest, null, 2) + '\n');
    await fs.writeFile(path.join(runtime, 'runtime-manifest.json'), raw, {mode: 0o644});
    await fs.chmod(path.join(runtime, 'runtime-manifest.json'), 0o644);
    return {runtimeManifest: structuredClone(manifest), runtimeManifestSha256: sha(raw)};
  }
  const options = await seal();
  return {root, bundle, runtime, payload, manifest, options, seal};
}

test('fused verifier preserves canonical record digest and reads each resource once', async t => {
  const f = await fixture(t);
  const raw = await fs.readFile(path.join(f.runtime, 'runtime-manifest.json'));
  const expected = sha(JSON.stringify([
    {path: 'Contents', mode: 0o755, type: 'directory'},
    {path: 'Contents/Resources', mode: 0o755, type: 'directory'},
    {path: 'Contents/Resources/runtime', mode: 0o755, type: 'directory'},
    {path: 'Contents/Resources/runtime/payload', mode: 0o755, type: 'file', size: f.payload.length, sha256: sha(f.payload)},
    {path: 'Contents/Resources/runtime/runtime-manifest.json', mode: 0o644, type: 'file', size: raw.length, sha256: sha(raw)},
  ]));
  assert.equal(await bundleDigest(f.bundle), expected);
  const original = fs.open; let payloadOpens = 0;
  fs.open = async function(file, ...args) {
    if (file === path.join(f.runtime, 'payload')) payloadOpens++;
    return original.call(this, file, ...args);
  };
  try {assert.equal(await bundleDigest(f.bundle, f.options), expected);}
  finally {fs.open = original;}
  assert.equal(payloadOpens, 1);
});

test('raw manifest checksum and supplied parsed policy must both match', async t => {
  const f = await fixture(t);
  await assert.rejects(bundleDigest(f.bundle, {runtimeManifest: f.manifest}), /required together/);
  await assert.rejects(bundleDigest(f.bundle, {...f.options, runtimeManifestSha256: '0'.repeat(64)}), /manifest checksum/);
  await assert.rejects(bundleDigest(f.bundle, {...f.options, runtimeManifest: {...f.manifest, unrelated: true}}), /manifest checksum/);
  await fs.appendFile(path.join(f.runtime, 'runtime-manifest.json'), ' ');
  await assert.rejects(bundleDigest(f.bundle, f.options), /manifest checksum/);
});

test('manifest mutation after policy read is rejected by captured inventory hash', async t => {
  const f = await fixture(t), file = path.join(f.runtime, 'runtime-manifest.json');
  const original = fs.open;
  fs.open = async function(target, ...args) {
    if (target === file) await fs.appendFile(file, ' ');
    return original.call(this, target, ...args);
  };
  try {await assert.rejects(bundleDigest(f.bundle, f.options), /manifest checksum/);}
  finally {fs.open = original;}
});

test('matching untrusted whole-bundle checksum cannot authorize invalid resource bytes', async t => {
  const f = await fixture(t);
  await fs.writeFile(path.join(f.runtime, 'payload'), 'modified resource');
  const changedDigest = await bundleDigest(f.bundle);
  await assert.rejects(installCompleteBundle({source: f.bundle, destination: path.join(f.root, 'Applications/Disco.app'),
    distribution: {channel: 'unsigned-testing'}, expectedBundleSha256: changedDigest,
    run: () => assert.fail('Invalid resources must reject before any command')}), /Runtime resource checksum failed/);
});

for (const mutation of ['extra', 'missing', 'size', 'executable', 'directory']) test(`resource ${mutation} mismatch rejects`, async t => {
  const f = await fixture(t), file = path.join(f.runtime, 'payload');
  if (mutation === 'extra') await fs.writeFile(path.join(f.runtime, 'unexpected'), 'extra');
  if (mutation === 'missing') await fs.rm(file);
  if (mutation === 'size') await fs.appendFile(file, 'extra');
  if (mutation === 'executable') await fs.chmod(file, 0o644);
  if (mutation === 'directory') {await fs.rm(file); await fs.mkdir(file);}
  await assert.rejects(bundleDigest(f.bundle, f.options), /Runtime resource inventory|Runtime resource metadata|Runtime executable permissions/);
});

test('runtime links must match manifest and remain inside runtime, not just app', async t => {
  const f = await fixture(t), link = path.join(f.runtime, 'alias');
  await fs.symlink('payload', link); f.manifest.resources.alias = {symlink: 'payload'};
  const options = await f.seal();
  assert.equal(await bundleDigest(f.bundle, options), await bundleDigest(f.bundle));
  await fs.rm(link); await fs.symlink('./payload', link);
  await assert.rejects(bundleDigest(f.bundle, options), /Runtime symlink differs/);
  await fs.writeFile(path.join(f.bundle, 'Contents/outside-runtime'), 'inside bundle');
  await fs.rm(link); await fs.symlink('../../outside-runtime', link);
  f.manifest.resources.alias = {symlink: '../../outside-runtime'};
  await assert.rejects(bundleDigest(f.bundle, await f.seal()), /Runtime resource escapes/);
});

test('runtime control directory links reject even when their target is inside app', async t => {
  const f = await fixture(t);
  await fs.rename(f.runtime, path.join(f.bundle, 'Contents/retained-runtime'));
  await fs.symlink('../retained-runtime', f.runtime);
  await assert.rejects(bundleDigest(f.bundle, f.options), /Runtime control directories/);
});
