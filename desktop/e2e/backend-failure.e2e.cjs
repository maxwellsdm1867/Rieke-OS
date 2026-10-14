'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path');
const {createHash} = require('node:crypto');
// Enable launch/process and protocol diagnostics before Playwright is loaded.
// A launch failure can occur before application.process() becomes available.
process.env.DEBUG=[process.env.DEBUG,'pw:browser','pw:api','pw:protocol'].filter(Boolean).join(',');
const diagnostic={stage:'starting',node:process.version,os_release:require('node:os').release(),stderr:'',native_events:[],launch_log:''};
const diagnosticFile=path.resolve(__dirname,'../../docs/dev/desktop-ui-e2e/backend-startup-failure-diagnostic.json');
const hostHome=require('node:os').homedir();
const stderrWrite=process.stderr.write;
process.stderr.write=function(chunk,...args){
  diagnostic.launch_log=(diagnostic.launch_log+chunk.toString()).slice(-128000);
  const pid=chunk.toString().match(/<launched> pid=(\d+)/)?.[1];
  if(pid)diagnostic.launch_pid=Number(pid);
  return stderrWrite.call(this,chunk,...args);
};
function failureDiagnostic(error){
  const sync=require('node:fs');
  diagnostic.os_crash_reports=[];
  if(diagnostic.bundle)for(const directory of new Set([path.join(hostHome,'Library/Logs/DiagnosticReports'),
      path.join(diagnostic.fixture_home,'Library/Logs/DiagnosticReports'),'/Library/Logs/DiagnosticReports'])){
    try{for(const name of sync.readdirSync(directory)){
      if(!/\.(ips|crash)$/.test(name))continue;
      const file=path.join(directory,name),stat=sync.statSync(file);
      if(stat.mtimeMs<diagnostic.launch_started_ms||stat.size>2*1024*1024)continue;
      const report=sync.readFileSync(file,'utf8');
      if(report.includes(diagnostic.bundle))diagnostic.os_crash_reports.push({file,report:report.slice(0,64000)});
    }}catch(error){diagnostic.crash_report_read_error=error.message;}
  }
  if(diagnostic.launch_pid)try{
    diagnostic.os_process_log=require('node:child_process').execFileSync('/usr/bin/log',
      ['show','--last','2m','--style','json','--predicate',`processID == ${diagnostic.launch_pid}`],
      {encoding:'utf8',timeout:5000,maxBuffer:1024*1024}).slice(-64000);
  }catch(error){diagnostic.os_process_log_error=error.message;}
  sync.mkdirSync(path.dirname(diagnosticFile),{recursive:true});
  sync.writeFileSync(diagnosticFile,JSON.stringify({...diagnostic,error:error.stack||error.message,failed_at:new Date().toISOString()},null,2)+'\n');
}
process.on('uncaughtExceptionMonitor',failureDiagnostic);
const {createFixture, launch, gracefulQuit, run} = require('./helpers.cjs');
const {resealRuntimeManifest} = require('../sign-runtime.cjs');
const {verifyResources} = require('../updater-validation.cjs');

(async () => {
  const fixture = await createFixture({reuse: false});
  const runtime = path.join(fixture.bundle, 'Contents/Resources/runtime');
  const sourceManifestSha256 = createHash('sha256').update(await fs.readFile(path.join(runtime, 'runtime-manifest.json'))).digest('hex');
  const appAsarSha256 = createHash('sha256').update(await fs.readFile(path.join(fixture.bundle, 'Contents/Resources/app.asar'))).digest('hex');
  await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', fixture.bundle]);
  const sourceEntitlements = (await run('/usr/bin/codesign', ['--display', '--entitlements', '-', fixture.bundle])).stdout;
  const entry = path.join(runtime, 'application/python/workspace_desktop.py');
  // This faulted copy is disposable and never supplies signing/release evidence.
  // The literal statement cannot import project code, bind services or start DB.
  const literalFailure = "raise RuntimeError('Injected packaged backend failure before imports, binding, projects or databases')\n";
  await fs.writeFile(entry, literalFailure);
  const manifest = await resealRuntimeManifest(runtime); await verifyResources(runtime, manifest.resources);
  // Keep the literal backend exception as the only injected fault. Updating
  // sealed resources invalidates the outer app seal, which macOS may enforce
  // differently across hosts. Re-seal only this disposable outer bundle; no
  // --deep signing, native executable changes, or publisher qualification.
  await run('/usr/bin/codesign', ['--force', '--sign', '-', '--timestamp=none',
    '--preserve-metadata=identifier,entitlements,requirements,flags,runtime', fixture.bundle]);
  await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', fixture.bundle]);
  assert.equal((await run('/usr/bin/codesign', ['--display', '--entitlements', '-', fixture.bundle])).stdout, sourceEntitlements);
  await verifyResources(runtime, manifest.resources);
  assert.equal(createHash('sha256').update(await fs.readFile(path.join(fixture.bundle, 'Contents/Resources/app.asar'))).digest('hex'), appAsarSha256);
  diagnostic.stage='launching-faulted-clone';
  diagnostic.bundle=fixture.bundle;diagnostic.fixture_home=fixture.home;diagnostic.launch_started_ms=Date.now();
  const {application, page} = await launch(fixture);
  diagnostic.stage='waiting-for-recovery';
  application.process().stderr.on('data',chunk=>{diagnostic.stderr=(diagnostic.stderr+chunk.toString()).slice(-16000);});
  application.process().stdout.on('data',chunk=>{for(const line of chunk.toString().split('\n'))if(line.startsWith('FAULT_RENDERER_EVENT='))diagnostic.native_events.push(line);});
  await application.evaluate(({BrowserWindow})=>{
    for(const window of BrowserWindow.getAllWindows())window.webContents.on('render-process-gone',(_event,details)=>process.stdout.write('FAULT_RENDERER_EVENT='+JSON.stringify(details)+'\n'));
  });
  await page.getByRole('heading', {name: 'Disco recovery', exact: true}).waitFor({timeout: 90000});
  const status = await page.evaluate(() => window.riekeDesktop.status());
  assert.equal(status.state, 'Recovery'); assert.match(status.detail, /exited before owning its listener/);
  assert.equal(await page.getByRole('heading', {name: 'Your projects', exact: true}).count(), 0);
  const record = JSON.parse(await fs.readFile(path.join(fixture.userData, 'desktop-service.json'), 'utf8'));
  assert.ok(record.executable.startsWith(fixture.bundle + '/'));
  await assert.rejects(run('/bin/ps', ['-p', String(record.pid), '-o', 'comm=']));
  assert.equal((await fs.readdir(path.join(fixture.userData, 'backend'))).length, 0);
  const output = path.resolve(__dirname, '../../docs/dev/desktop-ui-e2e'); await fs.mkdir(output, {recursive: true});
  await page.screenshot({path: path.join(output, 'backend-startup-recovery.png')});
  const receipt = {format: 'rieke-packaged-backend-failure-e2e', version: 1, passed: true, signed_qualification: false,
    method: 'Separate disposable packaged clone; literal raise-before-import backend; clone-only manifest and outer ad-hoc reseal',
    faulted_clone_seal_verified: true, source_entitlements_preserved: true, runtime_unchanged_after_outer_reseal: true,
    source_manifest_sha256: sourceManifestSha256, app_asar_sha256: appAsarSha256,
    fault_code_sha256: createHash('sha256').update(literalFailure).digest('hex'), recovery_before_projects: true,
    backend_exited: true, no_service_or_database_start: true, ordinary_quit_exited: true,
    teardown: 'Actual ordinary Quit acknowledges exit; known literal failed backend is already exited; no workers or databases existed'};
  diagnostic.stage='ordinary-quit';diagnostic.quit_started_at=new Date().toISOString();
  await gracefulQuit(application, page);
  diagnostic.quit_finished_at=new Date().toISOString();
  assert.equal(application.process().exitCode, 0);
  const interrupted = JSON.parse(await fs.readFile(path.join(fixture.userData, 'desktop-service.json'), 'utf8'));
  assert.equal(interrupted.quit.requested, true);
  assert.ok(['interrupted', 'closing'].includes(interrupted.quit.state), 'Abnormal backend exit must retain recovery evidence');
  await fs.writeFile(path.join(output, 'backend-startup-failure.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
})().catch(async error => {
  failureDiagnostic(error);
  console.error(error.message); process.exitCode = 1;
});
