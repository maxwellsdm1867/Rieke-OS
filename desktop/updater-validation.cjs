'use strict';
const fs = require('./physical-fs.cjs').promises;
const path = require('node:path');
const crypto = require('node:crypto');
const {promisify} = require('node:util');
const execFile = promisify(require('node:child_process').execFile);

function stableVersion(value) {
  if (typeof value !== 'string' || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(value)) throw new Error('Only stable semantic versions are accepted.');
  const parts = value.split('.').map(Number);
  if (!parts.every(Number.isSafeInteger)) throw new Error('Invalid release version.');
  return parts;
}
function compareVersions(left, right) {
  const a = stableVersion(left), b = stableVersion(right);
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return Math.sign(a[i] - b[i]);
  return 0;
}
function compatibleMacMinimum(minimum, host) {
  function parts(value) {
    if (typeof value !== 'string' || !/^\d+\.\d+(?:\.\d+)?$/.test(value)) throw new Error('Invalid macOS compatibility declaration.');
    const numbers=value.split('.').map(Number);while(numbers.length<3)numbers.push(0);return numbers;
  }
  const required=parts(minimum), actual=parts(host);
  for(let index=0;index<3;index++){
    if(actual[index]>required[index])return true;
    if(actual[index]<required[index])throw new Error('Update requires a newer macOS version.');
  }
  return true;
}
function compatibleCandidate(candidate, current, expectedVersion) {
  if (candidate?.format !== 'rieke-desktop-runtime' || candidate.version !== 1) throw new Error('Unsupported desktop runtime manifest.');
  if (candidate.source_dirty !== false || !/^[a-f0-9]{40}$/.test(candidate.source_commit || '') || !/^[a-f0-9]{40}$/.test(candidate.parser_commit || '')) throw new Error('Update has no clean source provenance.');
  if (candidate.application_version !== expectedVersion || compareVersions(expectedVersion, current.application_version) <= 0) throw new Error('Update version is mismatched or older than the installed app.');
  if (candidate.platform !== 'darwin' || candidate.architecture !== 'arm64' || current.platform !== candidate.platform || current.architecture !== candidate.architecture) throw new Error('Unsupported update platform.');
  if (candidate.database_compatibility !== current.database_compatibility || candidate.mysql_version !== current.mysql_version || !Array.isArray(candidate.workspace_formats) || !Array.isArray(current.workspace_formats) || !current.workspace_formats.every(format => candidate.workspace_formats.includes(format))) throw new Error('Update requires an unqualified database or workspace migration.');
  if (!candidate.resources || typeof candidate.resources !== 'object' || Array.isArray(candidate.resources) || !Object.keys(candidate.resources).length) throw new Error('Update has no resource inventory.');
  return candidate;
}
function safeResource(root, relative) {
  if (typeof relative !== 'string' || relative.includes('\\') || relative.includes('\0') || relative.split('/').some(part => !part || part === '.' || part === '..') || path.isAbsolute(relative)) throw new Error('Unsafe runtime resource path.');
  return path.join(root, relative);
}
async function verifyResources(root, resources) {
  const resolvedRoot = await fs.realpath(root);
  const actualPaths = [];
  async function inventory(directory) {
    for (const entry of await fs.readdir(directory, {withFileTypes: true})) {
      const file = path.join(directory, entry.name), relative = path.relative(root, file).split(path.sep).join('/');
      if (entry.isDirectory()) await inventory(file);
      else if (!['runtime-manifest.json', 'runtime-audit.json'].includes(relative)) actualPaths.push(relative);
    }
  }
  await inventory(root);
  if (JSON.stringify(actualPaths.sort()) !== JSON.stringify(Object.keys(resources).sort())) throw new Error('Runtime resource inventory is incomplete or contains unexpected files.');
  for (const [relative, expected] of Object.entries(resources)) {
    const file = safeResource(root, relative), stat = await fs.lstat(file);
    const physical = await fs.realpath(file);
    if (!physical.startsWith(resolvedRoot + path.sep)) throw new Error('Runtime resource escapes its bundle.');
    if (expected.symlink !== undefined) {
      if (!stat.isSymbolicLink() || await fs.readlink(file) !== expected.symlink || path.isAbsolute(expected.symlink)) throw new Error('Runtime symlink differs from its manifest.');
    } else {
      if (!stat.isFile() || stat.isSymbolicLink() || !/^[a-f0-9]{64}$/.test(expected.sha256) || stat.size !== expected.size) throw new Error('Runtime resource metadata is invalid.');
      if (typeof expected.executable === 'boolean' && expected.executable !== Boolean(stat.mode & 0o111)) throw new Error('Runtime executable permissions differ.');
      const actual = crypto.createHash('sha256');
      const handle = await fs.open(file, 'r');
      try { for await (const chunk of handle.createReadStream()) actual.update(chunk); } finally { await handle.close(); }
      if (actual.digest('hex') !== expected.sha256) throw new Error('Runtime resource checksum failed.');
    }
  }
}
async function signingIdentity(bundle, run = execFile) {
  await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle]);
  const result = await run('/usr/bin/codesign', ['-dv', '--verbose=4', bundle]);
  const output = `${result.stdout || ''}\n${result.stderr || ''}`;
  const team = output.match(/^TeamIdentifier=([A-Z0-9]+)$/m)?.[1];
  const identifier = output.match(/^Identifier=(.+)$/m)?.[1];
  if (!team || !identifier || !output.includes('Authority=Developer ID Application:')) throw new Error('A verified Developer ID application signature is required.');
  return {team, identifier};
}
// ZIP extraction is always to an isolated disposable directory. Neither the
// manifest nor candidate code is ever executed during validation.
async function validateDownloadedCandidate({downloadedFile, version, manifest, cacheDirectory, installedBundle, run = execFile}) {
  const installed = await signingIdentity(installedBundle, run);
  if (installed.identifier !== 'org.riekeos.desktop') throw new Error('Unexpected installed app identity.');
  await fs.mkdir(cacheDirectory, {recursive: true, mode: 0o700});
  const temporary = await fs.mkdtemp(path.join(cacheDirectory, 'candidate-'));
  try {
    // Reject traversal before allowing a native extractor to touch disk.
    const interpreter = path.join(installedBundle, 'Contents', 'Resources', 'runtime', 'python', 'bin', 'python3.11');
    await run(interpreter, ['-I', '-B', '-c', ARCHIVE_CHECK, downloadedFile], {timeout: 30000});
    await run('/usr/bin/ditto', ['-x', '-k', downloadedFile, temporary], {timeout: 180000});
    const bundles = (await fs.readdir(temporary)).filter(name => name.endsWith('.app'));
    if (bundles.length !== 1 || bundles[0] !== 'Rieke OS.app') throw new Error('Update must contain exactly the expected app.');
    const bundle = path.join(temporary, bundles[0]);
    const identity = await signingIdentity(bundle, run);
    if (identity.team !== installed.team || identity.identifier !== installed.identifier) throw new Error('Update signer or application identity differs.');
    const plist = path.join(bundle, 'Contents', 'Info.plist');
    const declared = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', plist]);
    if (declared.stdout.trim() !== version) throw new Error('App version differs from update metadata.');
    const runtime = path.join(bundle, 'Contents', 'Resources', 'runtime');
    const candidate = compatibleCandidate(JSON.parse(await fs.readFile(path.join(runtime, 'runtime-manifest.json'), 'utf8')), manifest, version);
    const host = await run('/usr/bin/sw_vers', ['-productVersion']);
    const bundleMinimum = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :LSMinimumSystemVersion', plist]);
    compatibleMacMinimum(candidate.minimum_macos_version, host.stdout.trim());
    if(bundleMinimum.stdout.trim() !== candidate.minimum_macos_version)throw new Error('App and runtime macOS minimums differ.');
    await verifyResources(runtime, candidate.resources);
    await run('/usr/sbin/spctl', ['--assess', '--type', 'execute', '--verbose=2', bundle]);
    const hasher = crypto.createHash('sha256');
    const handle = await fs.open(downloadedFile, 'r');
    try {for await (const chunk of handle.createReadStream()) hasher.update(chunk);} finally {await handle.close();}
    return {version, team: identity.team, identifier: identity.identifier, downloadedFile, archive_sha256: hasher.digest('hex'), validated: true, native_staging_verified: false, startup_health_verified: false};
  } finally { await fs.rm(temporary, {recursive: true, force: true}); }
}
const ARCHIVE_CHECK = String.raw`
import posixpath, stat, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    entries=archive.infolist()
    if not entries or len(entries)>100000 or sum(e.file_size for e in entries)>6*1024**3: raise ValueError('Archive bounds')
    names=set(); links={}
    for entry in entries:
        name=entry.filename.rstrip('/')
        if not name or name.startswith('/') or chr(92) in name or chr(0) in name or any(p in ('','..','.') for p in name.split('/')): raise ValueError('Archive path')
        if name in names: raise ValueError('Duplicate archive path')
        names.add(name)
        mode=entry.external_attr>>16
        if stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)): raise ValueError('Archive special file')
        if stat.S_ISLNK(mode):
            if entry.file_size>4096: raise ValueError('Archive link size')
            target=archive.read(entry).decode('utf8')
            if target.startswith('/') or chr(92) in target: raise ValueError('Archive link')
            links[name]=target
    for name in names:
        resolved=name
        for _ in range(40):
            parts=resolved.split('/'); changed=False
            for i in range(1,len(parts)+1):
                prefix='/'.join(parts[:i])
                if prefix in links:
                    resolved=posixpath.normpath(posixpath.join(posixpath.dirname(prefix),links[prefix],*parts[i:]))
                    if resolved=='..' or resolved.startswith('../') or resolved.startswith('/'): raise ValueError('Archive link escape')
                    changed=True; break
            if not changed: break
        else: raise ValueError('Archive link loop')
`;
module.exports = {stableVersion, compareVersions, compatibleMacMinimum, compatibleCandidate, safeResource, verifyResources, signingIdentity, validateDownloadedCandidate, ARCHIVE_CHECK};
