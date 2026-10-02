'use strict';
// Explicit local preview opt-in. Normal pack/dist commands retain their policy.
const {build} = require('./package.json');
module.exports = {...build, mac:{...build.mac,
  extendInfo:{...build.mac.extendInfo, CFBundleDisplayName:'DISCO Preview', DiscoLocalPreview:true}}};
