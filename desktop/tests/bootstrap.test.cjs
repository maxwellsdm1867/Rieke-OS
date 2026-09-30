'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {signatureIdentity, assertNotRunning, compatibleManifest, enclosingApp, installCompleteBundle} = require('../bootstrap.cjs');
test('bootstrap accepts only complete Developer ID signed app with exact identity', async () => {
  const run = async (_command, args) => ({stdout: '', stderr: args.includes('--display') ? 'Identifier=org.riekeos.desktop\nTeamIdentifier=EXAMPLETEAM\nAuthority=Developer ID Application: Example\n' : ''});
  assert.deepEqual(await signatureIdentity('/tmp/Rieke OS.app', run), {identifier: 'org.riekeos.desktop', team: 'EXAMPLETEAM'});
  await assert.rejects(signatureIdentity('/tmp/Rieke OS.app', async () => ({stdout: '', stderr: 'Identifier=org.riekeos.desktop\nTeamIdentifier=not set\nSignature=adhoc'})), /Developer ID/);
});
test('any installed app process blocks replacement and only dedicated helper PID is exempt', async () => {
  const run = async () => ({stdout: `  ${process.pid} /tmp/Rieke OS.app/Contents/MacOS/Rieke OS\n  100 /usr/bin/other\n`});
  await assert.rejects(assertNotRunning('/tmp/Rieke OS.app', run), /running/);
  await assertNotRunning('/tmp/Rieke OS.app', run, process.pid);
  await assert.rejects(installCompleteBundle({source: '/tmp/source.app', allowRollback: false, ignorePid: process.pid}), /dedicated/);
});
test('bootstrap refuses MySQL or workspace compatibility changes even in signed apps', () => {
  const current = {format: 'rieke-desktop-runtime', version: 1, platform: 'darwin', architecture: 'arm64', mysql_version: '8.4.2', workspace_formats: [1], database_compatibility: 1};
  assert.equal(compatibleManifest(current, current), true);
  assert.equal(compatibleManifest({...current, mysql_version: '9.0.0'}, current), false);
  assert.equal(compatibleManifest({...current, workspace_formats: [2]}, current), false);
  assert.equal(compatibleManifest({...current, database_compatibility: 2}, current), false);
  assert.equal(enclosingApp('/Applications/Rieke OS.app/Contents/MacOS/Rieke OS'), '/Applications/Rieke OS.app');
});
