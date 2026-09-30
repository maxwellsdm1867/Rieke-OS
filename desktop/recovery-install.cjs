'use strict';
// Dedicated, app-owned recovery entry point. The parent has already drained all
// services; this helper additionally waits for the main process to actually exit.
const path = require('node:path');
const os = require('node:os');
const fs = require('./physical-fs.cjs').promises;
const {promisify} = require('node:util');
const run = promisify(require('node:child_process').execFile);
const {installCompleteBundle, signatureIdentity, readBundleManifest, enclosingApp} = require('./bootstrap.cjs');
async function main() {
  const [pidText, previous, destination] = process.argv.slice(2);
  const pid = Number(pidText);
  const expected = path.join(os.homedir(), 'Applications', 'Rieke OS.app');
  if (!Number.isSafeInteger(pid) || pid <= 0 || destination !== expected || enclosingApp(process.execPath) !== destination || !previous.endsWith(path.join('updates', 'previous', 'Rieke OS.app'))) throw new Error('Invalid recovery request.');
  const current = await signatureIdentity(destination), prior = await signatureIdentity(previous);
  if (current.team !== prior.team) throw new Error('Recovery signature differs.');
  const deadline = Date.now() + 60000;
  for (;;) {
    let alive = true;
    try { process.kill(pid, 0); } catch (error) { if (error.code === 'ESRCH') alive = false; else throw error; }
    if (!alive) break;
    if (Date.now() >= deadline) throw new Error('App exit was not acknowledged; recovery deferred.');
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  await installCompleteBundle({source: previous, destination, allowRollback: true, ignorePid: process.pid});
  await run('/usr/bin/open', ['-n', destination]);
}
if (require.main === module) main().catch(() => { process.exitCode = 1; });
module.exports = {main};
