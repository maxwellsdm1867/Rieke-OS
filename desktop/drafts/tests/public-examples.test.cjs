'use strict';
// Executable public usage; writes only fresh disposable directories.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {DraftStore, validStoredDraft, MAX_DRAFT_BYTES} = require('../draft-store.cjs');
const value = {format:'rieke-renderer-draft',version:1,projectId:'launcher',value:{route:{page:'overview'}}};
async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'disco-draft-example-'));
  t.after(() => fs.rm(root, {recursive:true,force:true}));
  return {root, store:new DraftStore(root)};
}

test('public draft usage distinguishes absent state and a valid saved envelope', async t => {
  const {store} = await fixture(t);
  assert.equal(await store.load('launcher'), null);
  assert.equal(validStoredDraft(value, 'launcher'), true);
  assert.equal(validStoredDraft(value, 'another-project'), false);
  assert.equal(MAX_DRAFT_BYTES, 2 * 1024 * 1024);
  assert.deepEqual(await store.save({projectId:'launcher',value}), {saved:true});
  assert.deepEqual(await store.load('launcher'), value);
});

test('public recovery choice preserves original bytes before allowing a new view', async t => {
  const {root,store} = await fixture(t);
  await store.load('launcher');
  const directory = path.join(root,'drafts'), filename = path.join(directory,'launcher.json');
  const corrupt = '{owned example: incomplete';
  await fs.writeFile(filename, corrupt);
  assert.deepEqual(await store.load('launcher'), {
    format:'rieke-draft-recovery',version:1,projectId:'launcher',reason:'saved-draft-unreadable',
  });
  await assert.rejects(store.save({projectId:'launcher',value}), /explicit recovery decision/);
  assert.equal(await fs.readFile(filename,'utf8'), corrupt);
  assert.deepEqual(await store.reset('launcher'), {reset:true});
  assert.equal(await store.load('launcher'), null);
  const archived = (await fs.readdir(directory)).filter(name => name.startsWith('launcher.corrupt-'));
  assert.equal(archived.length,1);
  assert.equal(await fs.readFile(path.join(directory,archived[0]),'utf8'),corrupt);
  await store.save({projectId:'launcher',value});
  assert.deepEqual(await store.load('launcher'),value);
});
