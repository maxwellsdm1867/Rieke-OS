'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path');
const {createHash} = require('node:crypto');
const {createFixture, launch, run} = require('./helpers.cjs');
const {resealRuntimeManifest} = require('../sign-runtime.cjs');
const {verifyResources} = require('../updater-validation.cjs');
(async () => {
  const fixture = await createFixture({reuse: false});
  const runtime = path.join(fixture.bundle, 'Contents/Resources/runtime');
  const sourceManifestSha256 = createHash('sha256').update(await fs.readFile(path.join(runtime, 'runtime-manifest.json'))).digest('hex');
  const appAsarSha256 = createHash('sha256').update(await fs.readFile(path.join(fixture.bundle, 'Contents/Resources/app.asar'))).digest('hex');
  const entry = path.join(runtime, 'application/python/workspace_desktop.py');
  // This faulted copy is disposable and never supplies signing/release evidence.
  // The literal statement cannot import project code, bind services or start DB.
  const literalFailure = "raise RuntimeError('Injected packaged backend failure before imports, binding, projects or databases')\n";
  await fs.writeFile(entry, literalFailure);
  const manifest = await resealRuntimeManifest(runtime); await verifyResources(runtime, manifest.resources);
  const {application, page} = await launch(fixture);
  await page.getByRole('heading', {name: 'Rieke OS recovery', exact: true}).waitFor({timeout: 90000});
  const status = await page.evaluate(() => window.riekeDesktop.status());
  assert.equal(status.state, 'Recovery'); assert.match(status.detail, /exited before owning its listener/);
  assert.equal(await page.getByRole('heading', {name: 'Your projects', exact: true}).count(), 0);
  const record = JSON.parse(await fs.readFile(path.join(fixture.userData, 'desktop-service.json'), 'utf8'));
  assert.ok(record.executable.startsWith(fixture.bundle + '/'));
  await assert.rejects(run('/bin/ps', ['-p', String(record.pid), '-o', 'comm=']));
  assert.equal((await page.evaluate(() => window.riekeDesktop.quit())).ready, false);
  assert.equal((await fs.readdir(path.join(fixture.userData, 'backend'))).length, 0);
  const output = path.resolve(__dirname, '../../docs/dev/desktop-ui-e2e'); await fs.mkdir(output, {recursive: true});
  await page.screenshot({path: path.join(output, 'backend-startup-recovery.png')});
  const receipt = {format: 'rieke-packaged-backend-failure-e2e', version: 1, passed: true, signed_qualification: false,
    method: 'Separate disposable packaged clone; literal raise-before-import backend; clone-only manifest reseal',
    source_manifest_sha256: sourceManifestSha256, app_asar_sha256: appAsarSha256,
    fault_code_sha256: createHash('sha256').update(literalFailure).digest('hex'), recovery_before_projects: true,
    backend_exited: true, no_service_or_database_start: true, unsafe_quit_deferred: true,
    teardown: 'Only this test GUI exits after the known literal failed backend has exited; no workers or databases existed'};
  await fs.writeFile(path.join(output, 'backend-startup-failure.json'), JSON.stringify(receipt, null, 2) + '\n');
  const exited = new Promise(resolve => application.process().once('exit', resolve));
  await application.evaluate(({app}) => app.exit(0)); assert.equal(await exited, 0);
  console.log(JSON.stringify(receipt));
})().catch(error => {console.error(error.message); process.exitCode = 1;});
