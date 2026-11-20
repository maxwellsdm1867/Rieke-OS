'use strict';

const {spawnSync} = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const {setTimeout: wait} = require('node:timers/promises');

function quotaRetryDelay(receipt, now) {
  const check = 'explicit update Check returns an honest valid result';
  const failures = receipt?.failures;
  if (receipt?.format !== 'rieke-packaged-smoke-e2e' || receipt.passed !== false ||
      receipt.failure_cleanup !== 'orderly-exit' || receipt.update_status?.state !== 'Deferred' ||
      receipt.update_connectivity_verified !== false || receipt.update_transport?.actual_requests !== true ||
      !Array.isArray(failures) || !failures.some(item => item.name === check) ||
      !failures.every(item => [check, 'smoke-suite'].includes(item.name) &&
        item.message?.startsWith('This run requires a successful release-feed check'))) return null;
  const response = receipt.update_transport.observations?.at(-1);
  const headers = response?.headers;
  if (response?.kind !== 'release-api' || response.status_code !== 403 ||
      headers?.['x-ratelimit-resource'] !== 'core' || headers['x-ratelimit-remaining'] !== '0' ||
      !/^\d+$/.test(headers['x-ratelimit-reset'] || '')) return null;
  const seconds = Number(headers['x-ratelimit-reset']);
  const untilReset = seconds * 1000 - now;
  if (!Number.isSafeInteger(seconds) || untilReset < -60000 || untilReset > 3600000) return null;
  return Math.max(0, untilReset) + 2000;
}

async function run() {
  const root = path.resolve(__dirname, '../..');
  const receiptPath = path.join(root, 'docs/dev/desktop-smoke-e2e.json');
  function smoke() {
    const result = spawnSync(process.execPath, [path.join(__dirname, 'smoke.e2e.cjs')], {cwd: root, stdio: 'inherit'});
    if (result.error) throw result.error;
    return result.status ?? 1;
  }
  const started = Date.now();
  const first = smoke();
  if (first === 0) return 0;
  const receipt = JSON.parse(await fs.readFile(receiptPath, 'utf8'));
  const finished = Date.now();
  const observed = Date.parse(receipt.started_at);
  if (!Number.isFinite(observed) || observed < started || observed > finished) return first;
  const delay = quotaRetryDelay(receipt, finished);
  if (delay === null) return first;
  const diagnostics = path.join(root, 'desktop/build/native-qualification-diagnostics');
  await fs.mkdir(diagnostics, {recursive: true});
  await fs.copyFile(receiptPath, path.join(diagnostics, 'smoke-release-feed-quota.json'));
  console.log(`GitHub release-feed quota exhausted. Repeating the complete smoke suite after its reset in ${Math.ceil(delay / 1000)} seconds.`);
  await wait(delay);
  return smoke();
}

if (require.main === module) {
  run().then(code => { process.exitCode = code; }).catch(error => { console.error(error); process.exitCode = 1; });
}
module.exports = {quotaRetryDelay};
