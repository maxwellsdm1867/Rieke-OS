'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {DraftBarrier} = require('../draft-barrier.cjs');
const window = () => ({isDestroyed: () => false});
test('every scientific window must acknowledge its own persisted draft before drain', async () => {
  const requests = []; const barrier = new DraftBarrier({timeout: 50, send: (win, request) => requests.push({win, ...request})});
  const a = window(), b = window(); const result = barrier.prepare([a, b]);
  assert.throws(() => barrier.acknowledge({requestId: requests[0].requestId, ok: true}, b));
  barrier.acknowledge({requestId: requests[0].requestId, ok: true}, a);
  barrier.acknowledge({requestId: requests[1].requestId, ok: true}, b);
  assert.deepEqual(await result, {ready: true});
  assert.equal(barrier.pending.size, 0);
});
test('missing, failed and crashed renderer acknowledgements defer quit', async () => {
  const barrier = new DraftBarrier({timeout: 5, send: () => {}});
  assert.equal((await barrier.prepare([window()])).ready, false);
  assert.equal((await barrier.prepare([{isDestroyed: () => false, draftUnavailable: true}])).ready, false);
  assert.equal((await barrier.prepare([{isDestroyed: () => true}])).ready, false);
});
