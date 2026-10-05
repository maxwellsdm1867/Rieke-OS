'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {Readable}=require('node:stream');
const {createTestingUpdateCoordinator}=require('../testing-updater.cjs');
const {validateDescriptor,approvedURL}=require('../testing-update-validation.cjs');
const current={application_version:'0.1.2',platform:'darwin',architecture:'arm64',mysql_version:'8.4.2',database_compatibility:1,workspace_formats:[1]};
const bytes=Buffer.from('owned synthetic archive');
const descriptor={format:'rieke-desktop-test-release',version:1,channel:'unsigned-testing',repository:'maxwellsdm1867/Rieke-OS',application_version:'0.1.3',platform:'darwin',architecture:'arm64',mysql_version:'8.4.2',database_compatibility:1,workspace_formats:[1],minimum_macos_version:'14.0',archive:{filename:'Rieke-OS-0.1.3-arm64.zip',size:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),sha512:crypto.createHash('sha512').update(bytes).digest('base64')},asar_sha256:'a'.repeat(64),runtime_manifest_sha256:'b'.repeat(64)};
const base='https://github.com/maxwellsdm1867/Rieke-OS/releases/download/desktop-test-v0.1.3/';
async function fixture(t,mode){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'disco-update-example-'));
  const bundle=path.join(root,'Rieke OS.app');
  await fs.mkdir(path.join(bundle,'Contents/Resources/runtime'),{recursive:true});
  await fs.writeFile(path.join(bundle,'Contents/Resources/runtime/runtime-manifest.json'),JSON.stringify(current));
  let downloads=0,handoffs=0,quits=0,authorized=0,revalidations=0,drained=false;
  const release={draft:false,prerelease:true,tag_name:'desktop-test-v0.1.3',assets:[{name:'desktop-release.json',size:1000,browser_download_url:base+'desktop-release.json'},{name:descriptor.archive.filename,size:bytes.length,browser_download_url:base+descriptor.archive.filename}]};
  const transport=async url=>{
    let body;
    if(new URL(url).pathname.endsWith('/releases'))body=Buffer.from(JSON.stringify([release]));
    else if(url.endsWith('/desktop-release.json'))body=Buffer.from(JSON.stringify(descriptor));
    else {downloads++;body=bytes;}
    return {statusCode:200,headers:{},body:Readable.from([body])};
  };
  const coordinator=createTestingUpdateCoordinator({
    app:{isPackaged:true,getPath:name=>name==='exe'?path.join(bundle,'Contents/MacOS/Rieke OS'):root,quit:()=>{quits++;}},manifest:current,
    distribution:{format:'rieke-desktop-distribution',version:1,channel:'unsigned-testing',repository:descriptor.repository},transport,hostVersion:'14.2',
    timers:{setTimeout:()=>({unref(){}}),clearTimeout(){}},
    verifyCandidate:async args=>{const directory=await fs.mkdtemp(path.join(args.cacheDirectory,'candidate-'));const target=path.join(directory,'Rieke OS.app');await fs.mkdir(target);return{version:descriptor.application_version,downloadedFile:args.downloadedFile,bundle_path:target,candidate_directory:directory,bundle_sha256:'c'.repeat(64),archive_sha256:descriptor.archive.sha256,runtime_manifest_sha256:descriptor.runtime_manifest_sha256,validated:true};},
    revalidateCandidate:async()=>{revalidations++;if(mode==='changed'&&drained)throw Error('candidate changed after drain');},
    prepareQuit:async()=>{drained=true;if(mode==='stopped')coordinator.stop();return {ready:mode!=='deferred'};},
    processIdentity:async()=> 'owned-fixture-identity',installHelper:async()=>{handoffs++;return{ready:true};},authorizeQuit:()=>{authorized++;},
  });
  t.after(async()=>{coordinator.stop();await coordinator.flushReceipts();await fs.rm(root,{recursive:true,force:true});});
  return{coordinator,counts:()=>({downloads,handoffs,quits,authorized,revalidations})};
}
test('public validation rejects foreign provenance and untrusted URLs',()=>{
  assert.equal(validateDescriptor(descriptor,current,'14.2'),descriptor);
  assert.throws(()=>validateDescriptor({...descriptor,repository:'foreign/repo'},current,'14.2'),/provenance/);
  assert.throws(()=>approvedURL('https://github.com.evil.invalid/update.zip','asset'));
});
for(const mode of ['deferred','changed','stopped'])test(`testing public ${mode} drain never authorizes handoff`,{skip:process.platform!=='darwin'||process.arch!=='arm64'},async t=>{
  const f=await fixture(t,mode);await f.coordinator.start();
  assert.equal(f.coordinator.getStatus().state,'Available');assert.equal(f.counts().downloads,0);
  await f.coordinator.download();assert.equal(f.coordinator.getStatus().state,'Ready');assert.equal(f.counts().downloads,1);
  assert.equal((await f.coordinator.installPrepared()).ready,false);
  assert.equal(f.counts().handoffs,0);assert.equal(f.counts().authorized,0);assert.equal(f.counts().quits,0);
  assert.equal(f.counts().revalidations,mode==='deferred'?1:2);
});
