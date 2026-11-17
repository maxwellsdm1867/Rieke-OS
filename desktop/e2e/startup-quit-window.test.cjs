'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {projectWindowEvidence} = require('./startup-quit-window.cjs');

test('an exact project title can follow an untitled or recovery window', () => {
  const expected = 'Test project · DISCO';
  assert.deepEqual(projectWindowEvidence([null, 'DISCO recovery', expected], 'Test project', false),
    {state:'matched-project-title', title:expected});
});

test('a wrong title keeps waiting even if other titles are redacted', () => {
  const wrong = 'Could not restore Test project';
  assert.deepEqual(projectWindowEvidence([null, wrong], 'Test project', false),
    {state:'unexpected-titles', titles:[wrong]});
});

test('geometry alone distinguishes title redaction from no window and an untitled window', () => {
  assert.equal(projectWindowEvidence([], 'Test project', false).state, 'no-content-window');
  assert.equal(projectWindowEvidence([null], 'Test project', false).state, 'visible-window-titles-unavailable');
  assert.equal(projectWindowEvidence([''], 'Test project', true).state, 'awaiting-project-title');
  assert.throws(() => projectWindowEvidence([' · DISCO'], ' ', true), /Missing expected project name/);
});
