'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {isOwnedURL, validateSender, validateDraft, approvedReleaseURL} = require('../security.cjs');
test('only exact authenticated loopback origins and explicit recovery document are trusted', () => {
  const origins = new Set(['http://127.0.0.1:1234']);
  assert.equal(isOwnedURL('http://127.0.0.1:1234/api/project', origins), true);
  for (const url of ['http://localhost:1234/', 'http://127.0.0.1:1235/', 'https://127.0.0.1:1234/', 'javascript:alert(1)', 'file:///tmp/foreign.html']) assert.equal(isOwnedURL(url, origins), false);
  assert.equal(isOwnedURL('file:///tmp/recovery.html', origins, ['/tmp/recovery.html']), true);
});
test('privileged IPC rejects foreign renderer, subframe and origin', () => {
  const mainFrame = {url: 'http://127.0.0.1:1234/'}; const contents = {mainFrame};
  const window = {isDestroyed: () => false, webContents: contents};
  assert.equal(validateSender({sender: contents, senderFrame: mainFrame}, new Set([window]), 'http://127.0.0.1:1234'), window);
  assert.throws(() => validateSender({sender: {}, senderFrame: mainFrame}, [window], 'http://127.0.0.1:1234'));
  assert.throws(() => validateSender({sender: contents, senderFrame: {...mainFrame}}, [window], 'http://127.0.0.1:1234'));
  mainFrame.url = 'https://evil.example/';
  assert.throws(() => validateSender({sender: contents, senderFrame: mainFrame}, [window], 'http://127.0.0.1:1234'));
});
test('drafts reject path traversal, unknown fields, missing JSON and oversize', () => {
  assert.equal(validateDraft({projectId: 'launcher', value: {route: 'project'}}).projectId, 'launcher');
  for (const payload of [{projectId: '../../evil', value: {}}, {projectId: 'launcher', value: {}, path: '/tmp'}, {projectId: 'launcher', value: undefined}, {projectId: 'launcher', value: 'x'.repeat(2 * 1024 * 1024)}]) assert.throws(() => validateDraft(payload));
});
test('external URLs are restricted to canonical HTTPS release notes', () => {
  assert.equal(approvedReleaseURL('https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/v0.1.0'), true);
  for (const url of ['http://github.com/maxwellsdm1867/Rieke-OS/releases', 'https://github.com.evil.example/maxwellsdm1867/Rieke-OS/releases', 'https://github.com/user/other/releases', 'https://user:pass@github.com/maxwellsdm1867/Rieke-OS/releases']) assert.equal(approvedReleaseURL(url), false);
});
