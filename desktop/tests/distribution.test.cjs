'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {distributionPolicy} = require('../distribution.cjs');
test('normal installs retain signed update policy unless an explicit testing build opts in', () => {
  assert.equal(distributionPolicy().channel, 'signed');
  assert.equal(distributionPolicy({format:'rieke-desktop-distribution',version:1,channel:'unsigned-testing',repository:'maxwellsdm1867/Rieke-OS'}).channel,'unsigned-testing');
});
test('a testing build cannot redirect users to a foreign repository or unknown trust channel', () => {
  for(const value of [{format:'rieke-desktop-distribution',version:1,channel:'unsigned-testing',repository:'someone/other'}, {format:'rieke-desktop-distribution',version:1,channel:'anything',repository:'maxwellsdm1867/Rieke-OS'}]) assert.throws(()=>distributionPolicy(value));
});
