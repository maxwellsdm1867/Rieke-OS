'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {recoverVerificationFailure, cleanupAfterVerificationRecovery} = require('../verification-recovery.cjs');
const {verifyApplication, repairGuidance} = require('../verify-application.cjs');

test('public recovery blocks immediately and waits for accepted cleanup before presentation', async () => {
  const events = [];
  let finishPause, finishServices;
  const pause = new Promise(resolve => { finishPause = resolve; });
  const services = new Promise(resolve => { finishServices = resolve; });
  const pending = recoverVerificationFailure({
    blockNewWork: () => events.push('blocked'), pause: () => pause,
    saveDrafts: async () => { events.push('drafts'); return {ready:false, reason:'ack missing'}; },
    closeServices: async drafts => { assert.equal(drafts.reason, 'ack missing'); events.push('services'); return services; },
    showRecovery: () => events.push('shown'),
  });
  assert.deepEqual(events, ['blocked']);
  finishPause(); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(events, ['blocked', 'drafts', 'services']);
  finishServices({ready:true, drafts_saved:false});
  const result = await pending;
  assert.deepEqual(events, ['blocked', 'drafts', 'services', 'shown']);
  assert.equal(result.drafts.ready, false);
  assert.equal(cleanupAfterVerificationRecovery(result, () => assert.fail('must retain completed cleanup receipt')), result.services);
  assert.equal(result.services.drafts_saved, false);
});

test('public recovery preserves independent pause, draft and service failures', async () => {
  let shown;
  const result = await recoverVerificationFailure({
    blockNewWork: () => {}, pause: async () => { throw Error('pause refused'); },
    saveDrafts: async () => { throw Error('draft unreadable'); },
    closeServices: async drafts => { assert.equal(drafts.reason, 'draft unreadable'); throw Error('service uncertain'); },
    showRecovery: value => { shown = value; },
  });
  assert.equal(shown, result);
  assert.deepEqual(result, {pauseError:'pause refused', drafts:{ready:false, reason:'draft unreadable'}, services:{ready:false, reason:'service uncertain'}});
});

test('public cleanup retries absent, false and nonboolean readiness', async () => {
  let calls = 0;
  for (const result of [undefined, {services:{ready:false}}, {services:{ready:'true'}}]) {
    assert.equal(await cleanupAfterVerificationRecovery(result, async () => { calls++; return 'retried'; }), 'retried');
  }
  assert.equal(calls, 3);
});

test('public pre-aborted verification rejects before inspecting a bundle or running its seal', async () => {
  const controller = new AbortController(); controller.abort();
  await assert.rejects(verifyApplication({bundle:'/not-read/Disco.app', signed:false,
    signal:controller.signal, run:async () => assert.fail('must not run seal')}), {name:'AbortError'});
  assert.match(repairGuidance('/owned/Disco.app'), /First choose Quit/);
  assert.match(repairGuidance('/owned/Disco.app'), /Leave all project folders and user settings in place/);
});
