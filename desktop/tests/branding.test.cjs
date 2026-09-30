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
test('testing feed prefers Disco and falls back to the exact migration alias only for404',async()=>{
 for(const code of [404,403,500]){
  const calls=[];
  const transport=async url=>{calls.push(url);return{statusCode:calls.length===1?code:200,body:Readable.from([Buffer.from('[]')]),headers:{}};};
  if(code===404){assert.deepEqual(await releaseList(transport),[]);assert.match(calls[1],/^https:\/\/api.github.com\/repos\/maxwellsdm1867\/Rieke-OS\/releases\?/);}
  else{await assert.rejects(releaseList(transport));assert.equal(calls.length,1);}
  assert.match(calls[0],/^https:\/\/api.github.com\/repos\/maxwellsdm1867\/disco\/releases\?/);
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
