'use strict';
// A local ad-hoc seal makes the complete bundle structurally valid. It provides
// no Developer ID identity, notarization, or Gatekeeper approval.
const path=require('node:path');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const {distributionPolicy}=require('./distribution.cjs');
module.exports=async context=>{
  const distribution=distributionPolicy(require('./distribution.json'));
  if(distribution.channel!=='unsigned-testing'||context.electronPlatformName!=='darwin')return;
  const app=path.join(context.appOutDir,`${context.packager.appInfo.productFilename}.app`);
  const runtime=path.join(app,'Contents/Resources/runtime');
  const {signAsync}=require('@electron/osx-sign');
  await signAsync({app,identity:'-',identityValidation:false,platform:'darwin',type:'development',
    preAutoEntitlements:false,preEmbedProvisioningProfile:false,gatekeeperAssess:false,
    optionsForFile:()=>({hardenedRuntime:false,timestamp:'none',entitlements:path.join(__dirname,'entitlements.mac.plist')}),
    ignore:filename=>filename===runtime||filename.startsWith(runtime+path.sep)});
  await promisify(execFile)('/usr/bin/codesign',['--verify','--deep','--strict',app]);
};
