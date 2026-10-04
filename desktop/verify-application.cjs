'use strict';
// Explicit read-only audit. Never reseal a changed inventory or repair user data.
const fs = require('./physical-fs.cjs').promises;
const path = require('node:path');
const runFile = require('node:util').promisify(require('node:child_process').execFile);
const {verifyResources} = require('./updater-validation.cjs');
const {signatureIdentity, readBundleManifest} = require('./bootstrap.cjs');
async function verifyApplication({bundle, signed, run = runFile}) {
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
  await verifyResources(runtime, manifest.resources);
  if (signed) await signatureIdentity(bundle, run);
  else await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle], {timeout:120000});
  return {verified:true, publisherAuthenticated:Boolean(signed)};
}
module.exports = {verifyApplication};
