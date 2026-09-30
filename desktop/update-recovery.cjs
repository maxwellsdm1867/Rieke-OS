'use strict';
const fs = require('./physical-fs.cjs').promises;
const path = require('node:path');
const {spawn} = require('node:child_process');
const {promisify} = require('node:util');
const execFile = promisify(require('node:child_process').execFile);
const {signingIdentity, verifyResources} = require('./updater-validation.cjs');
const {enclosingApp, compatibleManifest} = require('./bootstrap.cjs');
const {atomicJSON} = require('./supervisor.cjs');

async function verifyPriorBundle({app, manifest, run = execFile}) {
  const installedBundle = enclosingApp(app.getPath('exe'));
  const directory = path.join(app.getPath('userData'), 'updates');
  const previous = path.join(directory, 'previous', 'Rieke OS.app');
  const receipt = JSON.parse(await fs.readFile(path.join(directory, 'previous.json'), 'utf8'));
  const currentIdentity = await signingIdentity(installedBundle, run);
  const priorIdentity = await signingIdentity(previous, run);
  if (currentIdentity.team !== priorIdentity.team || currentIdentity.identifier !== priorIdentity.identifier || receipt.team !== priorIdentity.team || receipt.identifier !== priorIdentity.identifier) throw new Error('Previous app signing identity differs.');
  const runtime = path.join(previous, 'Contents', 'Resources', 'runtime');
  const previousManifest = JSON.parse(await fs.readFile(path.join(runtime, 'runtime-manifest.json'), 'utf8'));
  if (!compatibleManifest(previousManifest, manifest) || previousManifest.mysql_version !== manifest.mysql_version || receipt.application_version !== previousManifest.application_version || receipt.source_commit !== previousManifest.source_commit) throw new Error('Previous app is incompatible with the current data contract.');
  await verifyResources(runtime, previousManifest.resources);
  await run('/usr/sbin/spctl', ['--assess', '--type', 'execute', previous]);
  return {previous, installedBundle, directory};
}

async function retainPriorBundle({app, manifest, run = execFile}) {
  const installedBundle = enclosingApp(app.getPath('exe'));
  const identity = await signingIdentity(installedBundle, run);
  const directory = path.join(app.getPath('userData'), 'updates');
  await fs.mkdir(directory, {recursive: true, mode: 0o700});
  const staging = await fs.mkdtemp(path.join(directory, 'prior-stage-'));
  const copied = path.join(staging, 'Rieke OS.app');
  try {
    await run('/usr/bin/ditto', ['--rsrc', '--extattr', '--acl', installedBundle, copied], {timeout: 180000});
    const copiedIdentity = await signingIdentity(copied, run);
    if (identity.team !== copiedIdentity.team || identity.identifier !== copiedIdentity.identifier) throw new Error('Previous app could not be retained with its signature intact.');
    const runtime = path.join(copied, 'Contents', 'Resources', 'runtime');
    const copiedManifest = JSON.parse(await fs.readFile(path.join(runtime, 'runtime-manifest.json'), 'utf8'));
    if (copiedManifest.application_version !== manifest.application_version || copiedManifest.source_commit !== manifest.source_commit) throw new Error('Previous app identity differs.');
    await verifyResources(runtime, copiedManifest.resources);
    const previous = path.join(directory, 'previous');
    const old = path.join(directory, 'previous-old');
    await fs.rm(old, {recursive: true, force: true});
    try { await fs.rename(previous, old); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    try { await fs.rename(staging, previous); } catch (error) { try { await fs.rename(old, previous); } catch {} throw error; }
    await atomicJSON(path.join(directory, 'previous.json'), {format: 'rieke-desktop-previous', version: 1, ...identity,
      application_version: manifest.application_version, source_commit: manifest.source_commit,
      workspace_formats: manifest.workspace_formats, database_compatibility: manifest.database_compatibility, mysql_version: manifest.mysql_version});
    await fs.rm(old, {recursive: true, force: true});
  } finally { await fs.rm(staging, {recursive: true, force: true}); }
}

async function restorePriorBundle({app, manifest, prepareQuit, authorizeQuit, run = execFile, spawnHelper = spawn}) {
  if (!app.isPackaged) throw new Error('Recovery installation requires a signed installed app.');
  // No renderer-provided path, version or command participates in this boundary.
  const {previous, installedBundle} = await verifyPriorBundle({app, manifest, run});
  const result = await prepareQuit();
  if (result?.ready !== true) return result;
  const helper = spawnHelper(app.getPath('exe'), [path.join(__dirname, 'recovery-install.cjs'), String(process.pid), previous, installedBundle],
    {detached: true, stdio: 'ignore', cwd: app.getPath('userData'), env: {HOME: process.env.HOME, TMPDIR: process.env.TMPDIR, ELECTRON_RUN_AS_NODE: '1'}});
  await new Promise((resolve, reject) => {helper.once('spawn', resolve); helper.once('error', reject);});
  helper.unref(); authorizeQuit(); app.quit();
  return {ready: true, restoring: true};
}
module.exports = {verifyPriorBundle, retainPriorBundle, restorePriorBundle};
