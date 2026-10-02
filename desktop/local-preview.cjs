'use strict';
// Only the explicitly marked local package uses this guard. Run before any
// application-managed profile/branding/lock/bootstrap writes. Electron and
// macOS may already have performed their own initialization before main runs.
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
function readInfoPlist(file) {
  return JSON.parse(execFileSync('/usr/bin/plutil', ['-convert', 'json', '-o', '-', file], {encoding:'utf8', maxBuffer:1024*1024}));
}
function localPreview({app, executable = process.execPath, platform = process.platform,
  env = process.env, argv = process.argv, readPlist = readInfoPlist, filesystem = fs, uid = process.getuid?.()}) {
  if (!app.isPackaged || platform !== 'darwin') return null;
  const bundle = path.resolve(executable, '../../..');
  const info = readPlist(path.join(bundle, 'Contents/Info.plist'));
  if (info.DiscoLocalPreview === undefined) return null;
  const fail = () => { throw new Error('Open this DISCO Preview using “Open DISCO Preview.command” in its preview folder. Its isolated home and profile are required.'); };
  if (info.DiscoLocalPreview !== true) fail();
  const root = path.resolve(bundle, '../../..'), home = path.join(root, 'home');
  const profile = path.join(root, 'profile'), temporary = path.join(root, 'tmp');
  if (bundle !== path.join(home, 'Applications/Rieke OS.app') ||
      env.HOME !== home || env.TMPDIR !== temporary || app.getPath('userData') !== profile ||
      argv.filter(value => value === '--user-data-dir' || value.startsWith('--user-data-dir=')).length !== 1 ||
      !argv.includes('--user-data-dir=' + profile) ||
      (env.RIEKE_PREFERENCES_DIR !== undefined && env.RIEKE_PREFERENCES_DIR !== path.join(home, '.rieke-os')) ||
      env.RIEKE_PROJECT_INDEX !== undefined || env.RECORDING_WORKSPACE_ROOT !== undefined) fail();
  for (const folder of [root, home, path.dirname(bundle), bundle, profile, temporary]) {
    const stat = filesystem.lstatSync(folder);
    if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== uid || filesystem.realpathSync(folder) !== folder) fail();
  }
  const manifest = JSON.parse(filesystem.readFileSync(path.join(bundle, 'Contents/Resources/runtime/runtime-manifest.json'), 'utf8'));
  if (manifest.format !== 'rieke-desktop-runtime' || manifest.version !== 1 ||
      manifest.application_version !== app.getVersion() || manifest.source_dirty !== false ||
      !/^[a-f0-9]{40}$/.test(manifest.source_commit || '')) fail();
  return Object.freeze({root, home, profile, application_version:manifest.application_version,
    source_commit:manifest.source_commit, label:`DISCO Preview · ${manifest.application_version} · ${manifest.source_commit.slice(0, 8)}`});
}
module.exports = {localPreview, readInfoPlist};
