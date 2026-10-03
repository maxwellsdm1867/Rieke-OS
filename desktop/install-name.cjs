'use strict';
const path = require('node:path');
// Each released main process expects its own canonical installation filename.
// A renamed destination would reopen the candidate in installer/bootstrap mode.
function assertInstallNameCompatible(executable, destination) {
  const expected = {Disco:'Disco.app', 'Rieke OS':'Rieke OS.app'}[executable];
  if (!expected || path.basename(destination) !== expected) {
    const error = new Error('This app name cannot be updated or restored into the current installation. Download the matching app and use Install and Open manually; existing projects and profiles stay in place.');
    error.code = 'MANUAL_APP_NAME_TRANSITION';
    throw error;
  }
}
async function assertBundleDestination(bundle, destination, run) {
  const value = await run('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleExecutable', path.join(bundle, 'Contents/Info.plist')]);
  assertInstallNameCompatible(value.stdout.trim(), destination);
}
module.exports = {assertInstallNameCompatible, assertBundleDestination};
