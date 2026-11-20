'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {quotaRetryDelay} = require('../e2e/smoke-quota-retry.cjs');

function quotaFailure() {
  return {format:'rieke-packaged-smoke-e2e', passed:false, failure_cleanup:'orderly-exit',
    failures:[{name:'explicit update Check returns an honest valid result',
      message:'This run requires a successful release-feed check\n\nfalse !== true\n'}],
    update_connectivity_verified:false, update_status:{state:'Deferred'},
    update_transport:{actual_requests:true, observations:[{kind:'release-api',status_code:403,
      headers:{'x-ratelimit-resource':'core','x-ratelimit-remaining':'0','x-ratelimit-reset':'1100'}}]}};
}
test('waits until the recorded GitHub reset before retrying an isolated, orderly closed smoke fixture', () => {
  assert.equal(quotaRetryDelay(quotaFailure(), 1000000), 102000);
  assert.equal(quotaRetryDelay(quotaFailure(), 1100500), 2000);
});
test('unrelated failures, invalid reset evidence and incomplete cleanup remain failures', () => {
  for (const mutate of [
    r => { r.failures.push({name:'renderer-pageerror',message:'Unexpected renderer failure'}); },
    r => { r.failure_cleanup='retained'; },
    r => { r.update_transport.observations[0].status_code=500; },
    r => { r.update_transport.observations[0].headers['x-ratelimit-remaining']='1'; },
    r => { r.update_transport.observations[0].headers['x-ratelimit-reset']='999999'; },
    r => { delete r.update_transport.observations[0].headers['x-ratelimit-reset']; },
    r => { r.update_transport.observations.push({kind:'release-asset',status_code:403}); },
  ]) {
    const receipt = quotaFailure();
    mutate(receipt);
    assert.equal(quotaRetryDelay(receipt, 1000000), null);
  }
});
