'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {Readable}=require('node:stream');
const {configureBranding}=require('../branding.cjs');
const {releaseList,assetURL}=require('../testing-updater.cjs');
const {approvedURL}=require('../testing-update-validation.cjs');
test('Disco preserves established and explicitly selected Electron profiles',()=>{
 for(const explicit of [null,'/tmp/selected-existing-profile']){
  let name='new package name',saved;
  const app={setName:value=>{name=value;},getPath:()=>explicit||`/profiles/${name}`,setPath:(_,value)=>{saved=value;}};
  assert.equal(configureBranding(app),explicit||'/profiles/Rieke OS');
  assert.equal(name,'Disco');assert.equal(saved,explicit||'/profiles/Rieke OS');
 }
});
test('testing feed uses the existing repository once for success and server failures',async()=>{
 for(const code of [200,404,401,403,500]){
  const calls=[];
  const transport=async url=>{calls.push(url);return{statusCode:code,body:Readable.from([Buffer.from('[]')]),headers:{}};};
  if(code===200)assert.deepEqual(await releaseList(transport),[]);
  else await assert.rejects(releaseList(transport));
  assert.deepEqual(calls,['https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1']);
 }
});
test('release assets and redirect policy accept both owned names and reject other repositories',()=>{
 for(const repo of ['disco','Rieke-OS']){
  const url=`https://github.com/maxwellsdm1867/${repo}/releases/download/v1.2.3/release.zip`;
  assert.equal(assetURL({name:'release.zip',browser_download_url:url},'v1.2.3','release.zip'),url);
  assert.equal(approvedURL(`https://api.github.com/repos/maxwellsdm1867/${repo}/releases`,'api',true),true);
 }
 for(const repo of ['foreign','disco-other'])assert.throws(()=>assetURL({name:'release.zip',browser_download_url:`https://github.com/maxwellsdm1867/${repo}/releases/download/v1.2.3/release.zip`},'v1.2.3','release.zip'));
});

test('macOS visible and helper names agree while installation identity stays compatible',()=>{
 const {build}=require('../package.json');
 assert.equal(build.productName,'Disco');
 assert.equal(build.mac.extendInfo.CFBundleName,build.productName);
 assert.equal(build.mac.extendInfo.CFBundleDisplayName,'Disco');
 assert.equal(build.mac.executableName,'Rieke OS');
 assert.equal(build.appId,'org.riekeos.desktop');
});
