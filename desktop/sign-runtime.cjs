'use strict';
// Pinned electron-builder 26.15.3 mac.sign(opts, packager) hook. Finish native
// signing first; hash final runtime bytes; then seal the outer application once.
const fs = require('node:fs/promises');
const {createReadStream} = require('node:fs');
const path = require('node:path');
const {createHash} = require('node:crypto');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const run = promisify(execFile);
const MACH_O = new Set([0xfeedface, 0xfeedfacf, 0xcefaedfe, 0xcffaedfe, 0xcafebabe, 0xbebafeca, 0xcafebabf, 0xbfbafeca]);
async function sha256(filename) {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(filename)) digest.update(chunk);
  return digest.digest('hex');
}
async function inventory(root) {
  const entries = [];
  async function visit(directory) {
    for (const entry of await fs.readdir(directory, {withFileTypes: true})) {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) await visit(absolute);
      else entries.push({absolute, relative: path.relative(root, absolute).split(path.sep).join('/'), symbolic: entry.isSymbolicLink()});
    }
  }
  await visit(root); return entries.sort((a, b) => a.relative.localeCompare(b.relative));
}
async function resealRuntimeManifest(root) {
  const manifestPath = path.join(root, 'runtime-manifest.json');
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  const resources = {};
  for (const item of await inventory(root)) {
    if (['runtime-manifest.json', 'runtime-audit.json'].includes(item.relative)) continue;
    if (item.symbolic) resources[item.relative] = {symlink: await fs.readlink(item.absolute)};
    else { const stat = await fs.stat(item.absolute); resources[item.relative] = {sha256: await sha256(item.absolute), size: stat.size, executable: Boolean(stat.mode & 0o111)}; }
  }
  manifest.resources = resources;
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  return manifest;
}
async function signRuntime(options) {
  if (!options.identity || options.identity === '-') throw new Error('Production runtime signing requires a Developer ID identity');
  const runtime = path.join(options.app, 'Contents', 'Resources', 'runtime');
  // No signature mutation may follow this inventory seal.
  for (const item of await inventory(runtime)) {
    if (item.symbolic) continue;
    const handle = await fs.open(item.absolute, 'r');
    const magic = Buffer.alloc(4); let bytesRead;
    try { ({bytesRead} = await handle.read(magic, 0, 4, 0)); } finally { await handle.close(); }
    if (bytesRead !== 4 || !MACH_O.has(magic.readUInt32BE())) continue;
    const args = ['--force', '--sign', options.identity, '--timestamp', '--options', 'runtime'];
    if (options.keychain) args.push('--keychain', options.keychain);
    if (item.relative === 'python/bin/python3.11') args.push('--entitlements', path.join(__dirname, 'entitlements.mac.plist'));
    args.push(item.absolute); await run('/usr/bin/codesign', args);
  }
  await resealRuntimeManifest(runtime);
  const {signAsync} = require('@electron/osx-sign');
  const previousIgnore = options.ignore == null ? [] : Array.isArray(options.ignore) ? options.ignore : [options.ignore];
  await signAsync({...options, ignore: [...previousIgnore, filename => filename === runtime || filename.startsWith(runtime + path.sep)]});
  await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', options.app]);
}
module.exports = signRuntime;
module.exports.resealRuntimeManifest = resealRuntimeManifest;
module.exports.inventory = inventory;
