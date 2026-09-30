'use strict';
// Bundle validation and replacement operate on physical files. Electron's
// ordinary fs presents an ASAR archive as a virtual directory for module loads.
// Node-based tooling uses the same physical filesystem API without Electron.
module.exports = process.versions.electron ? require('original-fs') : require('node:fs');
