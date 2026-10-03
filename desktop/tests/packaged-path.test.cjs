'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {packagedSource} = require('../e2e/packaged-path.cjs');
test('uses configured Disco output, refuses missing or escaping bundles', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'packaged-path-'));
  try {
    const bundle = path.join(root, 'dist/mac-arm64/Disco.app');
    const build = {productName:'Disco', directories:{output:'dist'}};
    assert.throws(() => packagedSource(root, build));
    fs.mkdirSync(path.join(bundle, 'Contents/MacOS'), {recursive:true});
    fs.writeFileSync(path.join(bundle, 'Contents/MacOS/Disco'), 'fixture');
    assert.equal(packagedSource(root, build), fs.realpathSync(bundle));
    assert.throws(() => packagedSource(root, {...build, productName:'Rieke OS'}));
    fs.renameSync(bundle, path.join(root, 'outside.app'));
    fs.symlinkSync(path.join(root, 'outside.app'), bundle);
    assert.throws(() => packagedSource(root, build), /escape/);
  } finally { fs.rmSync(root, {recursive:true, force:true}); }
});
test('mac executableName controls the bundle name in the pinned builder', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'packaged-path-'));
  try {
    const build = require('../package.json').build;
    const bundle = path.join(root, 'dist/mac-arm64/Rieke OS.app');
    fs.mkdirSync(path.join(bundle, 'Contents/MacOS'), {recursive:true});
    fs.writeFileSync(path.join(bundle, 'Contents/MacOS/Rieke OS'), 'fixture');
    assert.equal(packagedSource(root, build), fs.realpathSync(bundle));
  } finally { fs.rmSync(root, {recursive:true, force:true}); }
});
