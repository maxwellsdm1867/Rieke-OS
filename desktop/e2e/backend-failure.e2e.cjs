'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path');
const {createHash} = require('node:crypto');
const {createFixture, launch, gracefulQuit, run} = require('./qualification-helpers.cjs');
const {resealRuntimeManifest} = require('../sign-runtime.cjs');
const {verifyResources} = require('../updater-validation.cjs');
(async () => {
  const fixture = await createFixture({reuse: false});
  const runtime = path.join(fixture.bundle, 'Contents/Resources/runtime');
  const sourceManifestSha256 = createHash('sha256').update(await fs.readFile(path.join(runtime, 'runtime-manifest.json'))).digest('hex');
  const appAsarSha256 = createHash('sha256').update(await fs.readFile(path.join(fixture.bundle, 'Contents/Resources/app.asar'))).digest('hex');
  const entry = path.join(runtime, 'application/python/workspace_desktop.py');
  // Attach the observer before releasing the startup fault. An immediate exit
  // can reload the initial recovery shell while Playwright attaches its first
  // page, leaving its initial navigation unresolved. Only standard-library
  // polling runs here; no application imports, listener or database can start.
  // The faulted copy is disposable and never supplies signing/release evidence.
  const releaseFault = path.join(fixture.root, 'release-backend-startup-fault');
  const literalFailure = `import pathlib, time\nrelease = pathlib.Path(${JSON.stringify(releaseFault)})\ndeadline = time.monotonic() + 40\nwhile not release.exists():\n    if time.monotonic() >= deadline:\n        raise SystemExit(78)\n    time.sleep(0.02)\nraise RuntimeError('Injected packaged backend failure before application imports, binding, projects or databases')\n`;
  await fs.writeFile(entry, literalFailure);
  const manifest = await resealRuntimeManifest(runtime); await verifyResources(runtime, manifest.resources);
  // The runtime edit also invalidates the outer macOS resource seal. Restore
  // only this disposable clone's ad-hoc seal so the sandboxed renderer can
  // exercise backend recovery instead of failing platform bundle admission.
  await run('/usr/bin/codesign', ['--force', '--sign', '-', '--entitlements', path.resolve(__dirname, '../entitlements.mac.plist'), fixture.bundle]);
  await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', fixture.bundle]);
  const {application, page} = await launch(fixture,{renderer:'shell'});
  await fs.writeFile(releaseFault, 'release\n', {flag:'wx', mode:0o600});
  await page.getByRole('heading', {name: 'Disco recovery', exact: true}).waitFor({timeout: 90000});
  // The initial startup shell can already have this heading. Wait for the
  // actual backend-exit status, not presentation alone, before sampling it.
  await page.waitForFunction(async () => {
    const value = await window.riekeDesktop.status();
    return value.state === 'Recovery' && /exited before owning its listener/.test(value.detail || '');
  }, null, {timeout: 90000});
  const status = await page.evaluate(() => window.riekeDesktop.status());
  assert.equal(status.state, 'Recovery'); assert.match(status.detail, /exited before owning its listener \(1\)/);
  assert.equal(await page.getByRole('heading', {name: 'Your projects', exact: true}).count(), 0);
  const record = JSON.parse(await fs.readFile(path.join(fixture.userData, 'desktop-service.json'), 'utf8'));
  assert.ok(record.executable.startsWith(fixture.bundle + '/'));
  await assert.rejects(run('/bin/ps', ['-p', String(record.pid), '-o', 'comm=']));
  assert.equal((await fs.readdir(path.join(fixture.userData, 'backend'))).length, 0);
  const output = path.resolve(__dirname, '../../docs/dev/desktop-ui-e2e'); await fs.mkdir(output, {recursive: true});
  await page.screenshot({path: path.join(output, 'backend-startup-recovery.png')});
  const receipt = {format: 'rieke-packaged-backend-failure-e2e', version: 1, passed: true, signed_qualification: false,
    method: 'Separate disposable packaged clone; observer-gated raise before application imports; clone-only manifest and ad-hoc macOS resource reseal',
    source_manifest_sha256: sourceManifestSha256, app_asar_sha256: appAsarSha256,
    fault_released_after_observer_attachment: true, fault_wait_timeout_exit_code: 78, expected_backend_exit_code: 1,
    fault_code_sha256: createHash('sha256').update(literalFailure).digest('hex'), recovery_before_projects: true,
    backend_exited: true, no_service_or_database_start: true, ordinary_quit_exited: true,
    teardown: 'Actual ordinary Quit acknowledges exit; known failed backend is already exited; no workers or databases existed'};
  await gracefulQuit(application, page);
  assert.equal(application.process().exitCode, 0);
  const interrupted = JSON.parse(await fs.readFile(path.join(fixture.userData, 'desktop-service.json'), 'utf8'));
  assert.equal(interrupted.quit.requested, true);
  assert.ok(['interrupted', 'closing'].includes(interrupted.quit.state), 'Abnormal backend exit must retain recovery evidence');
  await fs.writeFile(path.join(output, 'backend-startup-failure.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
})().catch(error => {console.error(error.message); process.exitCode = 1;});
