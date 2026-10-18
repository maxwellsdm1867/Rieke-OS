'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {writeLocalizedDisplayName,infoPlistStrings}=require('../display-name.cjs');

test('every bundled language shows DISCO in the menu bar and Dock',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'display-name-')),app=path.join(root,'Disco.app'),resources=path.join(app,'Contents/Resources');
 try{
  for(const folder of ['de.lproj','ja.lproj','runtime'])await fs.mkdir(path.join(resources,folder),{recursive:true});
  assert.deepEqual(await writeLocalizedDisplayName(app),['de.lproj','en.lproj','ja.lproj']);
  for(const folder of ['de.lproj','en.lproj','ja.lproj'])assert.equal(await fs.readFile(path.join(resources,folder,'InfoPlist.strings'),'utf8'),'"CFBundleDisplayName" = "DISCO";\n"CFBundleName" = "DISCO";\n');
  await assert.rejects(fs.stat(path.join(resources,'runtime/InfoPlist.strings')));
 }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('local preview keeps its own shown name',()=>{
 assert.equal(infoPlistStrings('DISCO Preview'),'"CFBundleDisplayName" = "DISCO Preview";\n"CFBundleName" = "DISCO";\n');
});
