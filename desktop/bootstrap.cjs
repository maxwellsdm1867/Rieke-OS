'use strict';
const fs = require('./physical-fs.cjs').promises;
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify, isDeepStrictEqual} = require('node:util');
const {randomUUID, createHash} = require('node:crypto');
const runFile = promisify(execFile);
const {verifyResources, compareVersions, stableVersion, compatibleMacMinimum, safeResource} = require('./updater-validation.cjs');
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
    throw new Error('Install and Open requires the verified Developer ID signed Disco app');
  return {identifier, team};
}
async function assertNotRunning(bundle, run = runFile, ignorePid = null) {
  const {stdout} = await run('/bin/ps', ['-axo', 'pid=,comm=']);
  const prefix = `${bundle}${path.sep}`;
  if (stdout.split('\n').some(line => {
    const match = /^\s*(\d+)\s+(.+)$/.exec(line);
    return match && Number(match[1]) !== ignorePid && match[2].startsWith(prefix);
  }))
    throw new Error('The installed Disco app is running. Quit it before installation.');
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
function quarantinePreserved(source, copied) {
  if (source === null && copied === null) return true;
  const decode = value => {
    if (typeof value !== 'string' || !/^(?:[a-f0-9]{2})+$/.test(value)) return null;
    const text = Buffer.from(value, 'hex').toString('utf8');
    if (Buffer.from(text, 'utf8').toString('hex') !== value) return null;
    const fields = /^([a-fA-F0-9]{4});([a-fA-F0-9]{8});([^;\x00-\x1f\x7f]*);([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})$/.exec(text);
    return fields && {flags: parseInt(fields[1], 16), timestamp: fields[2], agent: fields[3], uuid: fields[4]};
  };
  const original = decode(source), destination = decode(copied);
  // Native copies may preserve flags or add only DO_NOT_TRANSLOCATE (0x0200).
  // Apple copyfile makes that addition conditional on COPYFILE_RUN_IN_PLACE:
  // https://github.com/apple-oss-distributions/copyfile/blob/main/copyfile.3
  // Owned never-launched copies also preserve flags while fully redacting the
  // timestamp/agent pair. Accept only those bounded observed forms. This does
  // not authorize launch, change attributes, or replace macOS approval.
  return Boolean(original && destination &&
    (destination.flags === original.flags || destination.flags === (original.flags | 0x0200)) &&
    destination.uuid === original.uuid &&
    ((destination.timestamp === original.timestamp && destination.agent === original.agent) ||
     (destination.timestamp === '00000000' && destination.agent === '')));
}
async function bundleDigest(bundle, {runtimeManifest, runtimeManifestSha256} = {}) {
  const validateRuntime = runtimeManifest !== undefined || runtimeManifestSha256 !== undefined;
  const runtimePrefix = 'Contents/Resources/runtime/';
  if (validateRuntime) {
    if (!runtimeManifest || typeof runtimeManifest.resources !== 'object' || !runtimeManifest.resources ||
        Array.isArray(runtimeManifest.resources) || !/^[a-f0-9]{64}$/.test(runtimeManifestSha256 || ''))
      throw new Error('Runtime manifest and its raw checksum are required together');
    // Bind the caller's parsed policy to the raw manifest; the traversal below
    // must capture that same hash. Resource bytes are read only by the traversal.
    const raw = await fs.readFile(path.join(bundle, runtimePrefix, 'runtime-manifest.json'));
    if (createHash('sha256').update(raw).digest('hex') !== runtimeManifestSha256 ||
        !isDeepStrictEqual(JSON.parse(raw), runtimeManifest)) throw new Error('Runtime manifest checksum or contents differ');
  }
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
        if (validateRuntime && relative.startsWith(runtimePrefix) &&
            !physical.startsWith(path.join(root, 'Contents/Resources/runtime') + path.sep))
          throw new Error('Runtime resource escapes its bundle');
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
  if (validateRuntime) {
    const byPath = new Map(records.map(record => [record.path, record]));
    for (const directory of ['Contents', 'Contents/Resources', 'Contents/Resources/runtime'])
      if (byPath.get(directory)?.type !== 'directory') throw new Error('Runtime control directories must be regular directories');
    const manifestRecord = byPath.get(runtimePrefix + 'runtime-manifest.json');
    if (manifestRecord?.type !== 'file' || manifestRecord.sha256 !== runtimeManifestSha256)
      throw new Error('Runtime manifest checksum or contents differ');
    const resources = runtimeManifest.resources;
    const runtimeRecords = records.filter(record => record.path.startsWith(runtimePrefix) && record.type !== 'directory' &&
      !['runtime-manifest.json', 'runtime-audit.json'].includes(record.path.slice(runtimePrefix.length)));
    if (JSON.stringify(runtimeRecords.map(record => record.path.slice(runtimePrefix.length)).sort()) !== JSON.stringify(Object.keys(resources).sort()))
      throw new Error('Runtime resource inventory is incomplete or contains unexpected files');
    for (const record of runtimeRecords) {
      const relative = record.path.slice(runtimePrefix.length), expected = resources[relative];
      // Preserve safeResource's policy even though these paths came from disk.
      safeResource(path.join(root, 'Contents/Resources/runtime'), relative);
      if (!expected || typeof expected !== 'object') throw new Error('Runtime resource metadata is invalid');
      if (expected.symlink !== undefined) {
        if (record.type !== 'symlink' || record.target !== expected.symlink || path.isAbsolute(expected.symlink))
          throw new Error('Runtime symlink differs from its manifest');
      } else {
        if (record.type !== 'file' || !/^[a-f0-9]{64}$/.test(expected.sha256 || '') || record.size !== expected.size)
          throw new Error('Runtime resource metadata is invalid');
        if (typeof expected.executable === 'boolean' && expected.executable !== Boolean(record.mode & 0o111))
          throw new Error('Runtime executable permissions differ');
        if (record.sha256 !== expected.sha256) throw new Error('Runtime resource checksum failed');
      }
    }
  }
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
  const executableName = executable.stdout.trim();
  // Legacy retained installations are verified in place; new shipping builds use Disco.
  if (!['Disco', 'Rieke OS'].includes(executableName) || !(await fs.stat(path.join(bundle, 'Contents', 'MacOS', executableName))).isFile()) throw new Error('Unsigned testing app executable is missing');
  return {identifier: APP_ID, team: null, channel: 'unsigned-testing'};
}
async function verifyTestingBundle(bundle, run = runFile) {
  await bundleIdentity(bundle, {channel: 'unsigned-testing'}, run);
  return verifyTestingClosure(bundle, run);
}
// Internal continuation used only after the caller has verified bundleIdentity.
async function verifyTestingClosure(bundle, run) {
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
// A prepared update may be consumed only from its private extraction directory.
// Keep this admission local to installation; a cache hint never skips validation.
async function preparedStaging(source, cache, parentInfo) {
  if (typeof cache !== 'string' || !path.isAbsolute(cache)) throw new Error('Prepared cache must be an absolute private directory');
  const canonicalCache = path.resolve(cache), canonicalSource = path.resolve(source);
  const candidate = path.dirname(canonicalSource);
  if (path.dirname(candidate) !== canonicalCache || !/^candidate-[a-zA-Z0-9]{6}$/.test(path.basename(candidate)) ||
      !['Disco.app', 'Rieke OS.app'].includes(path.basename(canonicalSource)))
    throw new Error('Prepared application must be directly inside its private candidate cache');
  const identities = [];
  for (const directory of [canonicalCache, candidate, canonicalSource]) {
    const stat = await fs.lstat(directory);
    if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== process.getuid() ||
        (directory !== canonicalSource && (stat.mode & 0o077)) || await fs.realpath(directory) !== directory)
      throw new Error('Prepared cache paths must be private owned directories without links');
    identities.push({directory, dev: stat.dev, ino: stat.ino});
  }
  return {source: canonicalSource, sameDevice: identities.at(-1).dev === parentInfo.dev, identities};
}
async function recheckPreparedStaging(prepared, parentInfo) {
  const current = await preparedStaging(prepared.source, prepared.identities[0].directory, parentInfo);
  if (current.identities.some((identity, index) => identity.dev !== prepared.identities[index].dev || identity.ino !== prepared.identities[index].ino))
    throw new Error('Prepared cache path identity changed');
}
async function installCompleteBundle({source, destination = path.join(os.homedir(), 'Applications', 'Disco.app'), run = runFile, allowRollback = false, ignorePid = null, distribution, expectedBundleSha256, expectedCurrentManifestSha256, retainPreviousDigest = false, preparedCache}) {
  const unsignedTesting = testingDistribution(distribution);
  if (expectedCurrentManifestSha256 !== undefined && !/^[a-f0-9]{64}$/.test(expectedCurrentManifestSha256))
    throw new Error('Expected current runtime manifest checksum is invalid');
  if ((preparedCache !== undefined || retainPreviousDigest) && !unsignedTesting)
    throw new Error('Prepared installation optimization requires unsigned testing distribution');
  if (preparedCache !== undefined && !/^[a-f0-9]{64}$/.test(expectedBundleSha256 || ''))
    throw new Error('Prepared installation requires an expected bundle checksum');
  if (ignorePid !== null && (!allowRollback || ignorePid !== process.pid)) throw new Error('Only the dedicated current recovery helper may be exempted from running-app checks');
  if (!source || !source.endsWith('.app')) throw new Error('A complete app bundle is required');
  const parent = path.dirname(destination);
  await fs.mkdir(parent, {recursive: true, mode: 0o700});
  const info = await fs.lstat(parent);
  if (info.isSymbolicLink() || info.uid !== process.getuid()) throw new Error('Installation folder must be owned by the current user');
  const prepared = preparedCache === undefined ? null : await preparedStaging(source, preparedCache, info);
  const consumePrepared = prepared?.sameDevice === true;
  let sourceManifest, sourceRuntime;
  if (unsignedTesting) {
    const raw = await fs.readFile(path.join(source, 'Contents/Resources/runtime/runtime-manifest.json'));
    sourceManifest = JSON.parse(raw);
    sourceRuntime = {runtimeManifest: sourceManifest, runtimeManifestSha256: createHash('sha256').update(raw).digest('hex')};
  }
  let sourceDigest = unsignedTesting && !consumePrepared ? await bundleDigest(source, sourceRuntime) : null;
  const quarantine = unsignedTesting ? await quarantineAttribute(source, run) : null;
  if (!consumePrepared && expectedBundleSha256 !== undefined && sourceDigest !== expectedBundleSha256) throw new Error('Downloaded application bundle checksum differs');
  const sourceIdentity = await bundleIdentity(source, distribution, run);
  await require('./install-name.cjs').assertBundleDestination(source, destination, run);
  if (!unsignedTesting) sourceManifest = await readBundleManifest(source);
  if (unsignedTesting) await verifyTestingClosure(source, run);
  stableVersion(sourceManifest.application_version);
  if (!compatibleManifest(sourceManifest, sourceManifest) || !sourceManifest.source_commit || !sourceManifest.resources ||
      !Array.isArray(sourceManifest.workspace_formats) || !Number.isInteger(sourceManifest.database_compatibility))
    throw new Error('Downloaded app runtime manifest is invalid');
  const sourcePlist = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', path.join(source, 'Contents', 'Info.plist')]);
  if (sourcePlist.stdout.trim() !== sourceManifest.application_version) throw new Error('App and runtime versions differ');
  if (!unsignedTesting) await verifyResources(path.join(source, 'Contents', 'Resources', 'runtime'), sourceManifest.resources);
  const lock = path.join(parent, '.rieke-os-install.lock');
  await fs.mkdir(lock, {mode: 0o700});
  const staging = consumePrepared ? prepared.source : path.join(parent, `.Rieke OS.install-${randomUUID()}.app`);
  const previous = path.join(parent, '.Rieke OS.previous.app');
  let movedPrevious = false, previousDigest = null;
  try {
    let existing = false;
    try {
      const targetInfo = await fs.lstat(destination);
      if (targetInfo.isSymbolicLink() || targetInfo.uid !== process.getuid()) throw new Error('Installed app is not a user-owned bundle');
      const installedIdentity = await bundleIdentity(destination, distribution, run, {verifyTestingSeal: false});
      if (installedIdentity.team !== sourceIdentity.team) throw new Error('Installed app has a different signing identity');
      const installedRaw = await fs.readFile(path.join(destination, 'Contents/Resources/runtime/runtime-manifest.json'));
      const installedManifest = JSON.parse(installedRaw);
      const installedManifestSha256 = createHash('sha256').update(installedRaw).digest('hex');
      if (expectedCurrentManifestSha256 !== undefined && installedManifestSha256 !== expectedCurrentManifestSha256)
        throw new Error('Installed runtime manifest differs from the prepared installation');
      if (!compatibleManifest(sourceManifest, installedManifest)) throw new Error('Installed app uses incompatible workspace or database formats');
      if (!allowRollback && compareVersions(sourceManifest.application_version, installedManifest.application_version) < 0) throw new Error('Install and Open cannot downgrade the installed app');
      if (retainPreviousDigest) previousDigest = await bundleDigest(destination, {runtimeManifest: installedManifest, runtimeManifestSha256: installedManifestSha256});
      else await verifyResources(path.join(destination, 'Contents', 'Resources', 'runtime'), installedManifest.resources);
      await assertNotRunning(destination, run, ignorePid); existing = true;
    } catch (error) { if (error.code !== 'ENOENT' || expectedCurrentManifestSha256 !== undefined) throw error; }
    if (!consumePrepared) {
      await run('/usr/bin/ditto', ['--rsrc', '--extattr', '--acl', source, staging]);
      const copiedIdentity = await bundleIdentity(staging, distribution, run);
      if (copiedIdentity.team !== sourceIdentity.team) throw new Error('Copied app signature differs from downloaded app');
      if (unsignedTesting) {
        if (await bundleDigest(staging, sourceRuntime) !== sourceDigest) throw new Error('Copied application bundle checksum differs');
      } else await verifyResources(path.join(staging, 'Contents', 'Resources', 'runtime'), sourceManifest.resources);
      if (unsignedTesting && !quarantinePreserved(quarantine, await quarantineAttribute(staging, run))) throw new Error('Copied application quarantine attribute differs');
      if (!unsignedTesting) await run('/usr/sbin/spctl', ['--assess', '--type', 'execute', staging]);
    }
    if (consumePrepared) {
      // Read these exact bytes after checking the old app, immediately before
      // consuming them. Directory identity alone cannot witness unchanged files.
      sourceDigest = await bundleDigest(source, sourceRuntime);
      if (sourceDigest !== expectedBundleSha256) throw new Error('Downloaded application bundle checksum differs');
      await recheckPreparedStaging(prepared, info);
    }
    if (existing) {
      await assertNotRunning(destination, run, ignorePid);
      // Retain exactly one verified previous signed bundle, only after the new copy is complete.
      await fs.rm(previous, {recursive: true, force: true});
      await fs.rename(destination, previous); movedPrevious = true;
    }
    let activated = false;
    try {
      await fs.rename(staging, destination); activated = true;
      await bundleIdentity(destination, distribution, run);
      if (consumePrepared && !quarantinePreserved(quarantine, await quarantineAttribute(destination, run)))
        throw new Error('Activated application quarantine attribute differs');
    } catch (error) {
      // Activation is not complete until identity verification succeeds. Move the
      // rejected copy out of the canonical path before restoring the old app.
      // If restoration itself fails, leave the old bundle at `previous`.
      if (activated) await fs.rename(destination, staging);
      if (movedPrevious) await fs.rename(previous, destination);
      throw error;
    }
    return {destination, previous: movedPrevious ? previous : null, ...(retainPreviousDigest ? {previousDigest} : {})};
  } finally {
    if (!consumePrepared) await fs.rm(staging, {recursive: true, force: true});
    await fs.rm(lock, {recursive: true, force: true});
  }
}
module.exports = {APP_ID, enclosingApp, signatureIdentity, assertNotRunning, compatibleManifest, installCompleteBundle, readBundleManifest, bundleDigest, verifyTestingBundle, quarantinePreserved};
