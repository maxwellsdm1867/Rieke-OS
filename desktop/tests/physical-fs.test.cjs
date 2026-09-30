'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {promisify}=require('node:util'),run=promisify(require('node:child_process').execFile);
const asar=require('@electron/asar');
test('actual Electron validates physical ASAR bytes and removes its cache without virtual-directory traversal',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-physical-asar-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const content=path.join(root,'content'),cache=path.join(root,'candidate'),archive=path.join(cache,'app.asar');
 await fs.mkdir(content);await fs.mkdir(cache);await fs.writeFile(path.join(content,'package.json'),JSON.stringify({name:'asar-boundary-fixture',version:'1.0.0'}));await fs.writeFile(path.join(content,'payload.txt'),'physical archive byte proof');
 await asar.createPackage(content,archive);const expected=crypto.createHash('sha256').update(await fs.readFile(archive)).digest('hex');
 const driver=path.join(root,'driver.cjs');
 await fs.writeFile(driver,`const assert=require('node:assert/strict'),virtual=require('node:fs'),path=require('node:path');
const physical=require(process.argv[2]),{hashFile}=require(process.argv[3]);
(async()=>{const archive=process.argv[4];assert.equal(virtual.lstatSync(archive).isDirectory(),true);assert.equal(physical.lstatSync(archive).isFile(),true);assert.equal(await hashFile(archive),process.argv[5]);await physical.promises.rm(path.dirname(archive),{recursive:true});console.log('RIEKE_PHYSICAL_ASAR_PASS');})().catch(error=>{console.error(error.stack);process.exitCode=1;});`);
 const result=await run(require('electron'),[driver,path.resolve(__dirname,'../physical-fs.cjs'),path.resolve(__dirname,'../testing-update-validation.cjs'),archive,expected],{timeout:30000,env:{...process.env,ELECTRON_RUN_AS_NODE:'1',HOME:root,PATH:'/usr/bin:/bin'}});
 assert.match(result.stdout,/RIEKE_PHYSICAL_ASAR_PASS/);await assert.rejects(fs.access(cache));
});
test('actual Electron signed candidate rejection cleans extracted ASAR while retaining Developer ID policy',{skip:process.platform!=='darwin'},async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-signed-asar-reject-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const content=path.join(root,'content'),bundle=path.join(root,'Rieke OS.app'),resources=path.join(bundle,'Contents/Resources');await fs.mkdir(content);await fs.mkdir(resources,{recursive:true});
 await fs.writeFile(path.join(content,'never-execute.cjs'),'throw new Error("candidate executed")');await asar.createPackage(content,path.join(resources,'app.asar'));
 const installed=path.join(root,'Installed.app'),bin=path.join(installed,'Contents/Resources/runtime/python/bin');await fs.mkdir(bin,{recursive:true});
 let python=path.resolve(__dirname,'../build/runtime/python/bin/python3.11');try{await fs.access(python);}catch{python=(await run('/usr/bin/which',['python3'])).stdout.trim();}
 await fs.symlink(python,path.join(bin,'python3.11'));
 const archive=path.join(root,'candidate.zip');await run(python,['-I','-B','-c',String.raw`import sys,zipfile
from pathlib import Path
root=Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2],'w') as z:
 for file in root.rglob('*'):
  if file.is_file():z.write(file,str(file.relative_to(root.parent)))`,bundle,archive]);
 const driver=path.join(root,'driver.cjs');
 await fs.writeFile(driver,`const assert=require('node:assert/strict'),path=require('node:path'),fs=require('original-fs').promises,{promisify}=require('node:util');
const realRun=promisify(require('node:child_process').execFile),{validateDownloadedCandidate}=require(process.argv[2]);
const installed=process.argv[3],cache=path.join(process.argv[5],'cache');
let extracted=false;
(async()=>{await assert.rejects(validateDownloadedCandidate({downloadedFile:process.argv[4],version:'1.1.0',manifest:{application_version:'1.0.0'},cacheDirectory:cache,installedBundle:installed,
 run:async(exe,args,options)=>{if(exe==='/usr/bin/codesign'){if(args.at(-1)!==installed){extracted=true;throw new Error('untrusted candidate signer');}return {stdout:'',stderr:'TeamIdentifier=TESTTEAM\\nIdentifier=org.riekeos.desktop\\nAuthority=Developer ID Application: simulated current signature for cleanup boundary'};}return realRun(exe,args,options);}}),/untrusted candidate signer/);
assert.equal(extracted,true);assert.deepEqual(await fs.readdir(cache),[]);console.log('RIEKE_SIGNED_ASAR_REJECT_CLEAN');})().catch(error=>{console.error(error.stack);process.exitCode=1;});`);
 const result=await run(require('electron'),[driver,path.resolve(__dirname,'../updater-validation.cjs'),installed,archive,root],{timeout:30000,env:{...process.env,ELECTRON_RUN_AS_NODE:'1',HOME:root,PATH:'/usr/bin:/bin'}});
 assert.match(result.stdout,/RIEKE_SIGNED_ASAR_REJECT_CLEAN/);
});
