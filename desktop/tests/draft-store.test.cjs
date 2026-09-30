'use strict';
const {test} = require('node:test'); const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const {DraftStore, MAX_DRAFT_BYTES} = require('../draft-store.cjs');
const payload = () => ({projectId: 'launcher', value: {format: 'rieke-renderer-draft', version: 1, projectId: 'launcher', value: {route: {page: 'overview'}}}});
async function fixture(t) {const root = await fs.mkdtemp(path.join(os.tmpdir(), 'rieke-drafts-')); t.after(() => fs.rm(root, {recursive: true, force: true})); const store = new DraftStore(root); await store.location('launcher'); return {root, store, filename: path.join(root, 'drafts/launcher.json')};}
test('missing drafts are ordinary and valid durable schema roundtrips', async t => {
  const {store} = await fixture(t); assert.equal(await store.load('launcher'), null);
  await store.save(payload()); assert.deepEqual(await store.load('launcher'), payload().value);
  await assert.rejects(store.reset('launcher'), /No verified/);
  await assert.rejects(store.save({projectId: 'launcher', value: {route: 'files'}}), /schema/);
});
test('malformed, mismatched and oversized stored drafts block overwrite until explicit preserved reset', async t => {
  const {store, filename, root} = await fixture(t);
  for (const bytes of ['{corrupted', JSON.stringify({...payload().value, projectId: 'foreign'}), 'x'.repeat(MAX_DRAFT_BYTES + 1)]) {
    await fs.writeFile(filename, bytes);
    assert.equal((await store.load('launcher')).format, 'rieke-draft-recovery');
    await assert.rejects(store.save(payload()), /recovery decision/); assert.equal(await fs.readFile(filename, 'utf8'), bytes);
    await store.reset('launcher'); assert.equal(await store.load('launcher'), null);
    const backups = (await fs.readdir(path.join(root, 'drafts'))).filter(name => name.startsWith('launcher.corrupt-'));
    assert.ok((await Promise.all(backups.map(name => fs.readFile(path.join(root, 'drafts', name), 'utf8')))).includes(bytes));
  }
});
test('symlink draft never reads target and reset preserves link without changing target', async t => {
  const {store, filename, root} = await fixture(t); const target = path.join(root, 'private-target'); await fs.writeFile(target, 'keep target'); await fs.symlink(target, filename);
  assert.equal((await store.load('launcher')).format, 'rieke-draft-recovery'); await assert.rejects(store.save(payload()));
  await store.reset('launcher'); assert.equal(await fs.readFile(target, 'utf8'), 'keep target');
  const backup = (await fs.readdir(path.join(root, 'drafts'))).find(name => name.startsWith('launcher.corrupt-'));
  assert.equal((await fs.lstat(path.join(root, 'drafts', backup))).isSymbolicLink(), true);
});
