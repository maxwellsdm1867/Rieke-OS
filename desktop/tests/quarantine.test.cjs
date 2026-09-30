'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {promisify}=require('node:util'),run=promisify(require('node:child_process').execFile);
const {quarantinePreserved}=require('../bootstrap.cjs');
const hex=value=>Buffer.from(value,'utf8').toString('hex');
const original='0083;66000000;Rieke-E2E;00000000-0000-4000-8000-000000000001';
test('native copied quarantine retains source protections and identity despite ditto metadata normalization',()=>{
 assert.equal(quarantinePreserved(hex(original),hex('0283;00000000;;00000000-0000-4000-8000-000000000001')),true);
 assert.equal(quarantinePreserved(hex(original),hex(original)),true);
 assert.equal(quarantinePreserved(null,null),true);
});
test('copy cannot lose quarantine, acquire approval bits or change its quarantine identity',()=>{
 for(const candidate of [null,'0281;00000000;;00000000-0000-4000-8000-000000000001','02c3;00000000;;00000000-0000-4000-8000-000000000001','0283;00000000;;00000000-0000-4000-8000-000000000002','0283;66000001;;00000000-0000-4000-8000-000000000001','0283;00000000;Changed;00000000-0000-4000-8000-000000000001','0283;00000000;;','garbage'])assert.equal(quarantinePreserved(hex(original),candidate===null?null:hex(candidate)),false,String(candidate));
 assert.equal(quarantinePreserved(null,hex(original)),false);
 assert.equal(quarantinePreserved(hex(original),'zz'),false);
 const malformed=hex('0083;66000000;')+'ff'+hex(';00000000-0000-4000-8000-000000000001');
 assert.equal(quarantinePreserved(malformed,hex('0283;00000000;;00000000-0000-4000-8000-000000000001')),false);
});
test('real macOS ditto preserves a quarantined app without writing or clearing copied attributes',{skip:process.platform!=='darwin'},async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-quarantine-copy-'));
 try{
  const source=path.join(root,'source.app'),destination=path.join(root,'copied.app');await fs.mkdir(source);await fs.writeFile(path.join(source,'fixture'),'owned quarantine fixture');
  await run('/usr/bin/xattr',['-w','com.apple.quarantine',original,source]);
  const before=(await run('/usr/bin/xattr',['-px','com.apple.quarantine',source])).stdout.replace(/\s/g,'').toLowerCase();
  await run('/usr/bin/ditto',['--rsrc','--extattr','--acl',source,destination]);
  const after=(await run('/usr/bin/xattr',['-px','com.apple.quarantine',destination])).stdout.replace(/\s/g,'').toLowerCase();
  assert.equal(quarantinePreserved(before,after),true);assert.equal((await run('/usr/bin/xattr',['-p','com.apple.quarantine',source])).stdout.trim(),original);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
