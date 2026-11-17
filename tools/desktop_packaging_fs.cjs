'use strict';
// The macOS signing walker captures fs.open on load. Queue transient file-limit
// failures before the walker starts, using the desktop lockfile's dependency.
const path = require('node:path');
const adapter = require.resolve('graceful-fs', {paths: [path.resolve(__dirname, '../desktop')]});
require(adapter).gracefulify(require('node:fs'));
