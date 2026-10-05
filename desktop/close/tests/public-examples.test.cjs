'use strict';
// Executable examples linked from ../README.md; public entries only.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {DraftBarrier} = require('../draft-barrier.cjs');
const {QuitCoordinator, bounded} = require('../quit-coordinator.cjs');

test('acknowledgment belongs to one request and exact window', async () => {
  const window = {isDestroyed: () => false};
  const foreignWindow = {isDestroyed: () => false};
  let request;
  const barrier = new DraftBarrier({send: (_window, value) => { request = value; }});
  const result = barrier.prepare([window]);
  try {
    assert.throws(() => barrier.acknowledge({requestId: request.requestId, ok: true}, foreignWindow), /No matching/);
  } finally {
    barrier.acknowledge({requestId: request.requestId, ok: true}, window);
  }
  assert.deepEqual(await result, {ready: true});
});

test('finite explicit Quit preserves recovery and coalesces callers', {timeout: 2000}, async () => {
  const exits = [];
  const quit = new QuitCoordinator({
    deadline: 100, draftDeadline: 5,
    prepareDrafts: () => new Promise(() => {}),
    cleanup: async () => ({ready: false, reason: 'Owned process exit unconfirmed.'}),
    exit: value => exits.push(value),
  });
  const first = quit.quit();
  assert.equal(quit.quit(), first);
  const result = await first;
  assert.equal(exits.length, 1);
  assert.equal(result.ready, true);
  assert.equal(result.clean, false);
  assert.equal(result.drafts_saved, false);
  assert.equal(result.services_closed, false);
  assert.match(result.warnings.join(' '), /last saved view/i);
  assert.match(result.warnings.join(' '), /exit unconfirmed/i);
});

test('bounded takes an action, milliseconds and timeout reason', {timeout: 2000}, async () => {
  assert.deepEqual(await bounded(async () => ({ready: true}), 100, 'unused'), {ready: true});
  assert.deepEqual(await bounded(() => new Promise(() => {}), 5, 'Waiting exceeded budget.'),
    {ready: false, reason: 'Waiting exceeded budget.', timedOut: true});
});
