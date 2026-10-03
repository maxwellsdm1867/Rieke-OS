'use strict';
const fs = require('node:fs');
const path = require('node:path');
// Test launcher source only. Never search ~/Applications or choose a stale fallback.
function packagedSource(desktop, build) {
  const output = path.resolve(fs.realpathSync(desktop), build.directories.output);
  if (!output.startsWith(fs.realpathSync(desktop) + path.sep)) throw new Error('Packaged output path escape');
  // electron-builder 26.15.3 AppInfo.productFilename gives executableName
  // precedence over productName, including the platform-specific override.
  const filename = build.mac?.executableName ?? build.executableName ?? build.productName;
  if (typeof filename !== 'string' || path.basename(filename) !== filename) throw new Error('Invalid packaged filename');
  const bundle = path.join(output, 'mac-arm64', `${filename}.app`);
  const actual = fs.realpathSync(bundle);
  if (actual !== bundle || !actual.startsWith(fs.realpathSync(output) + path.sep))
    throw new Error('Packaged bundle path escape');
  const executable = path.join(actual, 'Contents/MacOS', filename);
  if (fs.realpathSync(executable) !== executable || !fs.statSync(executable).isFile())
    throw new Error('Invalid packaged executable');
  return actual;
}
module.exports = {packagedSource};
