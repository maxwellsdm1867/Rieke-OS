'use strict';
const fs = require('./physical-fs.cjs').promises;
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {randomUUID, createHash} = require('node:crypto');
const runFile = promisify(execFile);
const {verifyResources, compareVersions, stableVersion, compatibleMacMinimum} = require('./updater-validation.cjs');
const APP_ID = 'org.riekeos.desktop';
function enclosingApp(executable) {
  const marker = `${path.sep}Contents${path.sep}MacOS${path.sep}`;
  const index = executable.lastIndexOf(marker);
  return index >= 0 ? executable.slice(0, index) : null;
}
async function signatureIdentity(bundle, run = runFile) {
  await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle]);
  const details = await run('/usr/bin/codesign', ['--display', '--verbose=4', bundle]);
  const text = `${details.stdout}\n${details.stderr}`;
  const identifier = /^Identifier=(.+)$/m.exec(text)?.[1];
  const team = /^TeamIdentifier=(.+)$/m.exec(text)?.[1];
  if (identifier !== APP_ID || !team || team === 'not set' || !/^Authority=Developer ID Application:/m.test(text))
    throw new Error('Install and Open requires the verified Developer ID signed Rieke OS app');
  return {identifier, team};
}
async function assertNotRunning(bundle, run = runFile, ignorePid = null) {
  const {stdout} = await run('/bin/ps', ['-axo', 'pid=,comm=']);
  const prefix = `${bundle}${path.sep}`;
  if (stdout.split('\n').some(line => {
    const match = /^\s*(\d+)\s+(.+)$/.exec(line);
    return match && Number(match[1]) !== ignorePid && match[2].startsWith(prefix);
  }))
    throw new Error('The installed Rieke OS app is running. Quit it before installation.');
}
async function readBundleManifest(bundle) {
  return JSON.parse(await fs.readFile(path.join(bundle, 'Contents', 'Resources', 'runtime', 'runtime-manifest.json'), 'utf8'));
}
async function quarantineAttribute(bundle, run) {
  try {
    const result = await run('/usr/bin/xattr', ['-px', 'com.apple.quarantine', bundle]);
    return result.stdout.replace(/\s/g, '').toLowerCase();
  } catch (error) {
    if (error.code === 1 && /No such xattr/i.test(error.stderr || '')) return null;
    throw error;
  }
}
async function bundleDigest(bundle) {
  const info = await fs.lstat(bundle);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('A regular complete application bundle is required');
  const root = await fs.realpath(bundle), records = [];
  let bytes = 0;
  async function visit(directory) {
    for (const name of (await fs.readdir(directory)).sort()) {
      const file = path.join(directory, name), stat = await fs.lstat(file);
      const relative = path.relative(root, file).split(path.sep).join('/');
      if (records.length >= 120000) throw new Error('Application bundle exceeds inventory bounds');
      const record = {path: relative, mode: stat.mode & 0o777};
      if (stat.isSymbolicLink()) {
        const target = await fs.readlink(file), physical = await fs.realpath(file);
        if (path.isAbsolute(target) || (!physical.startsWith(root + path.sep) && physical !== root)) throw new Error('Application symlink escapes its bundle');
        records.push({...record, type: 'symlink', target});
      } else if (stat.isDirectory()) {
        records.push({...record, type: 'directory'}); await visit(file);
      } else if (stat.isFile()) {
        bytes += stat.size;
        if (bytes > 8 * 1024 ** 3) throw new Error('Application bundle exceeds size bounds');
        const digest = createHash('sha256'), handle = await fs.open(file, 'r');
        try { for await (const chunk of handle.createReadStream()) digest.update(chunk); } finally { await handle.close(); }
        records.push({...record, type: 'file', size: stat.size, sha256: digest.digest('hex')});
      } else throw new Error('Application contains a special file');
    }
  }
  await visit(root);
  return createHash('sha256').update(JSON.stringify(records)).digest('hex');
}
function testingDistribution(distribution) {
  if (distribution === undefined || distribution === null || distribution.channel === 'signed') return false;
  if (distribution.channel !== 'unsigned-testing') throw new Error('Unsupported application distribution policy');
  return true;
}
async function bundleIdentity(bundle, distribution, run, {verifyTestingSeal = true} = {}) {
  if (!testingDistribution(distribution)) return signatureIdentity(bundle, run);
  if (verifyTestingSeal) await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle]);
  const plist = path.join(bundle, 'Contents', 'Info.plist');
  const declared = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleIdentifier', plist]);
  if (declared.stdout.trim() !== APP_ID) throw new Error('Unsigned testing app identifier differs');
  const executable = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleExecutable', plist]);
  if (executable.stdout.trim() !== 'Rieke OS' || !(await fs.stat(path.join(bundle, 'Contents', 'MacOS', 'Rieke OS'))).isFile()) throw new Error('Unsigned testing app executable is missing');
  return {identifier: APP_ID, team: null, channel: 'unsigned-testing'};
}
async function verifyTestingBundle(bundle, run = runFile) {
  await bundleIdentity(bundle, {channel: 'unsigned-testing'}, run);
  const manifest = await readBundleManifest(bundle);
  const required = ['python/bin/python3.11', 'mysql/bin/mysqld', 'mysql/bin/mysql', 'mysql/bin/mysqldump', 'application/python/workspace_desktop.py'];
  if (!compatibleManifest(manifest, manifest) || !/^[a-f0-9]{40}$/.test(manifest.source_commit || '') || !/^[a-f0-9]{40}$/.test(manifest.parser_commit || '') ||
      !/^3\.11\.\d+$/.test(manifest.python_version || '') || !/^8\.4\.\d+$/.test(manifest.mysql_version || '') || !Array.isArray(manifest.workspace_formats) || !manifest.workspace_formats.length ||
      !Number.isInteger(manifest.database_compatibility) || !required.every(name => manifest.resources?.[name])) throw new Error('Unsigned testing runtime closure is incomplete');
  stableVersion(manifest.application_version);
  const plist = path.join(bundle, 'Contents', 'Info.plist');
  const version = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', plist]);
  const minimum = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :LSMinimumSystemVersion', plist]);
  if (version.stdout.trim() !== manifest.application_version || minimum.stdout.trim() !== manifest.minimum_macos_version) throw new Error('Unsigned testing app and runtime versions differ');
  const host = await run('/usr/bin/sw_vers', ['-productVersion']);
  compatibleMacMinimum(manifest.minimum_macos_version, host.stdout.trim());
  return manifest;
}
function compatibleManifest(candidate, current) {
  return candidate.format === 'rieke-desktop-runtime' && candidate.version === 1 && candidate.platform === 'darwin' && candidate.architecture === 'arm64' &&
    candidate.mysql_version === current.mysql_version &&
    candidate.database_compatibility === current.database_compatibility &&
    JSON.stringify(candidate.workspace_formats) === JSON.stringify(current.workspace_formats);
}
async function installCompleteBundle({source, destination = path.join(os.homedir(), 'Applications', 'Rieke OS.app'), run = runFile, allowRollback = false, ignorePid = null, distribution, expectedBundleSha256}) {
  const unsignedTesting = testingDistribution(distribution);
  if (ignorePid !== null && (!allowRollback || ignorePid !== process.pid)) throw new Error('Only the dedicated current recovery helper may be exempted from running-app checks');
  if (!source || !source.endsWith('.app')) throw new Error('A complete app bundle is required');
  const parent = path.dirname(destination);
  await fs.mkdir(parent, {recursive: true, mode: 0o700});
  const info = await fs.lstat(parent);
  if (info.isSymbolicLink() || info.uid !== process.getuid()) throw new Error('Installation folder must be owned by the current user');
  const sourceDigest = unsignedTesting ? await bundleDigest(source) : null;
  const quarantine = unsignedTesting ? await quarantineAttribute(source, run) : null;
  if (expectedBundleSha256 !== undefined && sourceDigest !== expectedBundleSha256) throw new Error('Downloaded application bundle checksum differs');
  const sourceIdentity = await bundleIdentity(source, distribution, run);
  const sourceManifest = await readBundleManifest(source);
  if (unsignedTesting) await verifyTestingBundle(source, run);
  stableVersion(sourceManifest.application_version);
  if (!compatibleManifest(sourceManifest, sourceManifest) || !sourceManifest.source_commit || !sourceManifest.resources ||
      !Array.isArray(sourceManifest.workspace_formats) || !Number.isInteger(sourceManifest.database_compatibility))
    throw new Error('Downloaded app runtime manifest is invalid');
  const sourcePlist = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', path.join(source, 'Contents', 'Info.plist')]);
  if (sourcePlist.stdout.trim() !== sourceManifest.application_version) throw new Error('App and runtime versions differ');
  await verifyResources(path.join(source, 'Contents', 'Resources', 'runtime'), sourceManifest.resources);
  const lock = path.join(parent, '.rieke-os-install.lock');
  await fs.mkdir(lock, {mode: 0o700});
  const staging = path.join(parent, `.Rieke OS.install-${randomUUID()}.app`);
  const previous = path.join(parent, '.Rieke OS.previous.app');
  let movedPrevious = false;
  try {
    let existing = false;
    try {
      const targetInfo = await fs.lstat(destination);
      if (targetInfo.isSymbolicLink() || targetInfo.uid !== process.getuid()) throw new Error('Installed app is not a user-owned bundle');
      const installedIdentity = await bundleIdentity(destination, distribution, run, {verifyTestingSeal: false});
      if (installedIdentity.team !== sourceIdentity.team) throw new Error('Installed app has a different signing identity');
      const installedManifest = await readBundleManifest(destination);
      if (!compatibleManifest(sourceManifest, installedManifest)) throw new Error('Installed app uses incompatible workspace or database formats');
      if (!allowRollback && compareVersions(sourceManifest.application_version, installedManifest.application_version) < 0) throw new Error('Install and Open cannot downgrade the installed app');
      await verifyResources(path.join(destination, 'Contents', 'Resources', 'runtime'), installedManifest.resources);
      await assertNotRunning(destination, run, ignorePid); existing = true;
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await run('/usr/bin/ditto', ['--rsrc', '--extattr', '--acl', source, staging]);
    const copiedIdentity = await bundleIdentity(staging, distribution, run);
    if (copiedIdentity.team !== sourceIdentity.team) throw new Error('Copied app signature differs from downloaded app');
    await verifyResources(path.join(staging, 'Contents', 'Resources', 'runtime'), sourceManifest.resources);
    if (unsignedTesting && await bundleDigest(staging) !== sourceDigest) throw new Error('Copied application bundle checksum differs');
    if (unsignedTesting && await quarantineAttribute(staging, run) !== quarantine) throw new Error('Copied application quarantine attribute differs');
    if (!unsignedTesting) await run('/usr/sbin/spctl', ['--assess', '--type', 'execute', staging]);
    if (existing) {
      await assertNotRunning(destination, run, ignorePid);
      // Retain exactly one verified previous signed bundle, only after the new copy is complete.
      await fs.rm(previous, {recursive: true, force: true});
      await fs.rename(destination, previous); movedPrevious = true;
    }
    try { await fs.rename(staging, destination); }
    catch (error) { if (movedPrevious) await fs.rename(previous, destination); throw error; }
    await bundleIdentity(destination, distribution, run);
    return {destination, previous: movedPrevious ? previous : null};
  } finally {
    await fs.rm(staging, {recursive: true, force: true});
    await fs.rm(lock, {recursive: true, force: true});
  }
}
module.exports = {APP_ID, enclosingApp, signatureIdentity, assertNotRunning, compatibleManifest, installCompleteBundle, readBundleManifest, bundleDigest, verifyTestingBundle};
