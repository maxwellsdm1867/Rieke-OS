'use strict';
// Explicit read-only audit. Never reseal a changed inventory or repair user data.
const fs = require('../physical-fs.cjs').promises;
const path = require('node:path');
const {spawn} = require('node:child_process');
const {verifyResources} = require('../updater-validation.cjs');
const {signatureIdentity, readBundleManifest} = require('../bootstrap.cjs');
// Only this read-only audit child is signalled. Resolve/reject on close, not the
// abort event: Quit must know the owned codesign process has actually exited.
function runAuditCommand(command, args, {signal, timeout = 120000} = {}) {
  signal?.throwIfAborted();
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {stdio:['ignore','pipe','pipe']});
    let stdout='', stderr='', failure, escalation;
    const stop = () => {failure ||= signal?.reason || new Error('Application verification timed out'); child.kill('SIGTERM'); escalation ||= setTimeout(()=>child.kill('SIGKILL'),1000);};
    const timer=setTimeout(stop,timeout);
    signal?.addEventListener('abort',stop,{once:true});
    child.stdout.on('data',bytes=>{stdout=(stdout+bytes).slice(-65536);});
    child.stderr.on('data',bytes=>{stderr=(stderr+bytes).slice(-65536);});
    child.on('error',error=>{failure=error;});
    child.on('close',code=>{clearTimeout(timer);clearTimeout(escalation);signal?.removeEventListener('abort',stop);if(failure||code!==0)reject(failure||new Error('Application seal verification failed'));else resolve({stdout,stderr});});
    if(signal?.aborted)stop();
  });
}
async function verifyApplication({bundle, signed, run = runAuditCommand, signal, progress}) {
  signal?.throwIfAborted();
  if (!bundle || !bundle.endsWith('.app')) throw new Error('A complete packaged application is required');
  const runtime = path.join(bundle, 'Contents/Resources/runtime');
  const manifest = await readBundleManifest(bundle);
  if (manifest.format !== 'rieke-desktop-runtime' || manifest.version !== 1 || !manifest.resources || Array.isArray(manifest.resources) || !Object.keys(manifest.resources).length)
    throw new Error('Unsupported application inventory');
  const release = JSON.parse(await fs.readFile(path.join(runtime, 'application/rieke-release.json'), 'utf8'));
  const source = JSON.parse(await fs.readFile(path.join(runtime, 'application/python/workspace-source.json'), 'utf8'));
  for (const [key, expected] of Object.entries({application_version:release.version, workspace_formats:release.workspace_formats,
    database_compatibility:release.database_compatibility, parser_commit:source.commit, python_version:source.python})) {
    if (expected === undefined || JSON.stringify(manifest[key]) !== JSON.stringify(expected)) throw new Error('Mixed application compatibility declarations');
  }
  await verifyResources(runtime, manifest.resources, {signal, progress});
  signal?.throwIfAborted();
  progress?.('Checking application seal');
  const boundedRun=(command,args)=>run(command,args,{signal,timeout:120000});
  if (signed) await signatureIdentity(bundle, boundedRun);
  else await boundedRun('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle]);
  return {verified:true, publisherAuthenticated:Boolean(signed)};
}
function repairGuidance(bundle) {
  return `First choose Quit. Once Disco and all its owned services have closed, move only the damaged application bundle (${bundle}) to a holding folder outside Applications. Do not launch that retained copy. Leave all project folders and user settings in place. Open a newly downloaded complete Disco.app from the trusted release source and choose Install and Open. The installer validates the incoming and staged copy. If closure is unconfirmed, finish service recovery before moving the app.`;
}
module.exports = {verifyApplication, runAuditCommand, repairGuidance};
