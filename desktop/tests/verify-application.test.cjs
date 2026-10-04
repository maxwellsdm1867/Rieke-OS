'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {createHash}=require('node:crypto');
const {verifyApplication}=require('../verify-application.cjs');
async function fixture(t){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'disco-verify-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const bundle=path.join(root,'Disco.app'),runtime=path.join(bundle,'Contents/Resources/runtime');
  const manifest={format:'rieke-desktop-runtime',version:1,application_version:'1.0.0',workspace_formats:[1],database_compatibility:1,parser_commit:'a'.repeat(40),python_version:'3.11.13',resources:{}};
  const files={'unused.txt':'original','application/rieke-release.json':JSON.stringify({version:'1.0.0',workspace_formats:[1],database_compatibility:1}),'application/python/workspace-source.json':JSON.stringify({commit:'a'.repeat(40),python:'3.11.13'})};
  for(const [name,bytes] of Object.entries(files)){const p=path.join(runtime,name);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,bytes);manifest.resources[name]={size:Buffer.byteLength(bytes),sha256:createHash('sha256').update(bytes).digest('hex')};}
  const manifestPath=path.join(runtime,'runtime-manifest.json');await fs.writeFile(manifestPath,JSON.stringify(manifest));
  return {bundle,runtime,manifest,manifestPath};
}
test('explicit verification reads inventory and verifies seal without claiming unsigned publisher identity',async t=>{
  const f=await fixture(t),calls=[];const before=await fs.readFile(f.manifestPath);
  assert.deepEqual(await verifyApplication({...f,signed:false,run:async(...args)=>{calls.push(args);}}),{verified:true,publisherAuthenticated:false});
  assert.deepEqual(calls[0].slice(0,2),['/usr/bin/codesign',['--verify','--deep','--strict',f.bundle]]);
  assert.deepEqual(await fs.readFile(f.manifestPath),before);
});
test('unused same-size corruption fails explicit verification without resealing',async t=>{
  const f=await fixture(t),before=await fs.readFile(f.manifestPath);
  await fs.writeFile(path.join(f.runtime,'unused.txt'),'modified');
  await assert.rejects(verifyApplication({...f,signed:false,run:async()=>assert.fail('seal must not mask corrupt runtime')}),/checksum/);
  assert.deepEqual(await fs.readFile(f.manifestPath),before);
  assert.equal(await fs.readFile(path.join(f.runtime,'unused.txt'),'utf8'),'modified');
});
test('mixed compatibility and failed outer seal fail explicit verification',async t=>{
  const f=await fixture(t);
  await assert.rejects(verifyApplication({...f,signed:false,run:async()=>{throw Error('bad seal');}}),/bad seal/);
  f.manifest.application_version='2.0.0';await fs.writeFile(f.manifestPath,JSON.stringify(f.manifest));
  await assert.rejects(verifyApplication({...f,signed:false}),/Mixed/);
});
test('assembled build refuses corrupt runtime before signing or rewriting its manifest',async t=>{
  const f=await fixture(t),before=await fs.readFile(f.manifestPath);
  await fs.writeFile(path.join(f.runtime,'unused.txt'),'modified');
  await assert.rejects(require('../seal-testing.cjs')({electronPlatformName:'darwin',appOutDir:path.dirname(f.bundle),packager:{appInfo:{productFilename:'Disco'}}}),/checksum/);
  assert.deepEqual(await fs.readFile(f.manifestPath),before);
});
