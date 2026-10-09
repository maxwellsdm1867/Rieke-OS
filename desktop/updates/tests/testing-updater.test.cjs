'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto'),http=require('node:http');
const {Readable}=require('node:stream');
const {validateDescriptor,approvedURL,inspectTestingBundle,validateTestingCandidate,revalidateTestingCandidate,verifyArchive}=require('../testing-update-validation.cjs');
const {createTestingUpdateCoordinator}=require('../testing-updater.cjs');
const current={application_version:'0.1.2',platform:'darwin',architecture:'arm64',mysql_version:'8.4.2',database_compatibility:1,workspace_formats:[1]};
const bytes=Buffer.from('candidate archive bytes');
const descriptor={format:'rieke-desktop-test-release',version:1,channel:'unsigned-testing',repository:'maxwellsdm1867/Rieke-OS',application_version:'0.1.3',platform:'darwin',architecture:'arm64',mysql_version:'8.4.2',database_compatibility:1,workspace_formats:[1],minimum_macos_version:'14.0',archive:{filename:'Rieke-OS-0.1.3-arm64.zip',size:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),sha512:crypto.createHash('sha512').update(bytes).digest('base64')},asar_sha256:'a'.repeat(64),runtime_manifest_sha256:'b'.repeat(64)};
const distribution={format:'rieke-desktop-distribution',version:1,channel:'unsigned-testing',repository:'maxwellsdm1867/Rieke-OS'};
const base='https://github.com/maxwellsdm1867/Rieke-OS/releases/download/desktop-test-v0.1.3/';
test('archive verification requires both digests and rejects changed bytes, truncation and links',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'disco-archive-digests-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const file=path.join(root,'candidate.zip'),payload=crypto.randomBytes(256*1024+17);
  const value={archive:{size:payload.length,sha256:crypto.createHash('sha256').update(payload).digest('hex'),sha512:crypto.createHash('sha512').update(payload).digest('base64')}};
  await fs.writeFile(file,payload,{mode:0o600});
  await verifyArchive(file,value);
  for(const [algorithm,encoding] of [['sha256','hex'],['sha512','base64']]){
    const wrong=crypto.createHash(algorithm).update('different bytes').digest(encoding);
    await assert.rejects(verifyArchive(file,{archive:{...value.archive,[algorithm]:wrong}}),/checksum failed/);
  }
  const changed=Buffer.from(payload);changed[changed.length-1]^=1;
  await fs.writeFile(file,changed);
  await assert.rejects(verifyArchive(file,value),/checksum failed/);
  await fs.writeFile(file,payload.subarray(0,-1));
  await assert.rejects(verifyArchive(file,value),/size or ownership changed/);
  const link=path.join(root,'linked.zip');await fs.symlink(file,link);
  await assert.rejects(verifyArchive(link,value),/size or ownership changed/);
});
test('testing descriptor and URL boundaries reject foreign provenance, migration and nonstable versions',()=>{
  assert.equal(validateDescriptor(descriptor,current,'14.2'),descriptor);
  for(const patch of [{channel:'signed'},{repository:'foreign/repo'},{application_version:'0.1.2'},{application_version:'0.1.3-beta'},{architecture:'x64'},{database_compatibility:2},{workspace_formats:[2]},{minimum_macos_version:'15.0'},{archive:{...descriptor.archive,filename:'../bad.zip'}},{archive:{...descriptor.archive,size:0}},{archive:{...descriptor.archive,sha512:'bad'}}])assert.throws(()=>validateDescriptor({...descriptor,...patch},current,'14.2'));
  assert.equal(approvedURL(base+descriptor.archive.filename,'asset'),true);
  for(const url of ['http://github.com/maxwellsdm1867/Rieke-OS/releases/download/v0.1.3/a.zip','https://github.com/foreign/repo/releases/download/v1/a.zip','https://github.com.evil.invalid/maxwellsdm1867/Rieke-OS/releases/download/v1/a.zip','https://user:secret@github.com/maxwellsdm1867/Rieke-OS/releases/download/v1/a.zip','https://api.github.com/repos/foreign/repo/releases','https://127.0.0.1/releases'])assert.throws(()=>approvedURL(url,'asset'));
});
async function fixture(t,options={}){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-testing-update-'));
  const release={draft:false,prerelease:true,tag_name:'desktop-test-v0.1.3',html_url:'https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.3',assets:[{name:'desktop-release.json',size:1000,browser_download_url:base+'desktop-release.json'},{name:descriptor.archive.filename,size:bytes.length,browser_download_url:base+descriptor.archive.filename}]};
  let archiveCalls=0,helperCalls=0,drains=0,validationCalls=0,failDownload=false,failMetadata=false,metadataCalls=0;
  let archiveBytes=bytes;
  const server=http.createServer((request,response)=>{
    const url=new URL(request.url,'http://fixture');
    if(url.pathname.endsWith('/releases')){metadataCalls++;if(failMetadata){response.writeHead(503);response.end('offline');}else response.end(JSON.stringify([release]));}
    else if(url.pathname.endsWith('/desktop-release.json'))response.end(JSON.stringify(descriptor));
    else {archiveCalls++;if(failDownload){response.writeHead(200,{'Content-Length':bytes.length+10});response.end(bytes.subarray(0,2));}else response.end(archiveBytes);}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const transport=url=>new Promise((resolve,reject)=>{
    const official=new URL(url);
    http.get({hostname:'127.0.0.1',port:server.address().port,path:official.pathname+official.search},response=>resolve({statusCode:response.statusCode,headers:response.headers,body:response})).on('error',reject);
  });
  const app={isPackaged:true,getPath:name=>name==='exe'?path.join(root,'Rieke OS.app/Contents/MacOS/Rieke OS'):root};
  await fs.mkdir(path.join(root,'Rieke OS.app/Contents/Resources/runtime'),{recursive:true});
  await fs.writeFile(path.join(root,'Rieke OS.app/Contents/Resources/runtime/runtime-manifest.json'),JSON.stringify(current));
  const coordinator=createTestingUpdateCoordinator({app,manifest:current,distribution,transport,hostVersion:'14.2',
    timers:{setTimeout:()=>({unref(){}}),clearTimeout(){}},
    verifyCandidate:async args=>{validationCalls++;const directory=await fs.mkdtemp(path.join(args.cacheDirectory,'candidate-'));const bundle=path.join(directory,'Rieke OS.app');await fs.mkdir(bundle);return {version:args.descriptor.application_version,downloadedFile:args.downloadedFile,bundle_path:bundle,candidate_directory:directory,bundle_sha256:'c'.repeat(64),archive_sha256:descriptor.archive.sha256,runtime_manifest_sha256:descriptor.runtime_manifest_sha256,validated:true};},
    revalidateCandidate:async()=>{},
    prepareQuit:async()=>{drains++;return{ready:true};},
    processIdentity:async()=> 'fixture-process-start',
    installHelper:async()=>{helperCalls++;},...options});
  t.after(async()=>{coordinator.stop();await coordinator.flushReceipts();await new Promise(resolve=>server.close(resolve));await fs.rm(root,{recursive:true,force:true});});
  return{root,app,transport,coordinator,archiveCalls:()=>archiveCalls,helperCalls:()=>helperCalls,drains:()=>drains,validationCalls:()=>validationCalls,metadataCalls:()=>metadataCalls,setMetadataFailure:()=>{failMetadata=true;},setDownloadFailure:()=>{failDownload=true;},retryDownload:()=>{failDownload=false;},corruptDownload:()=>{archiveBytes=Buffer.from('corrupt');}};
}
test('startup metadata notice never downloads; explicit download prepares and orderly install runs once',async t=>{
  const f=await fixture(t);await f.coordinator.start();
  assert.equal(f.coordinator.getStatus().state,'Available');assert.equal(f.archiveCalls(),0);
  await f.coordinator.download();assert.equal(f.coordinator.getStatus().state,'Ready');assert.equal(f.archiveCalls(),1);
  const result=await Promise.all([f.coordinator.installPrepared(),f.coordinator.installPrepared()]);
  assert.ok(result.every(r=>r.installing));assert.equal(f.helperCalls(),1);assert.equal(f.drains(),1);
});
test('installer progress is display-only and reports validation before quit',async t=>{
  const statuses=[];let releaseHelper,enteredHelper;
  const entered=new Promise(resolve=>{enteredHelper=resolve;});
  const f=await fixture(t,{publishStatus:status=>statuses.push(status),installHelper:async({onProgress})=>{
    onProgress({phase:'validate-prepared',progress:75});
    onProgress({phase:'untrusted-phase',progress:100});
    enteredHelper();await new Promise(resolve=>{releaseHelper=resolve;});return {ready:true};
  }});
  let quits=0;f.app.quit=()=>{quits++;};
  await f.coordinator.start();await f.coordinator.download();const installing=f.coordinator.installPrepared();await entered;
  assert.equal(quits,0);assert.equal(f.coordinator.getStatus().phase,'validate-prepared');
  assert.equal(f.coordinator.getStatus().phase_progress,null);
  assert.equal(f.coordinator.getStatus().can_restart,false);
  assert.ok(statuses.some(status=>status.state==='Validating'&&status.message.includes('before closing')));
  assert.ok(statuses.some(status=>status.state==='Validating'&&status.message.includes('after scientific')));
  releaseHelper();assert.equal((await installing).ready,true);assert.equal(quits,1);
});
async function lastInstallFixture(f,result){
  const cache=path.join(f.root,'updates/unsigned-testing');await fs.mkdir(cache,{recursive:true,mode:0o700});
  const receipt='install-00000000-0000-4000-8000-000000000001.json';
  const installed=path.join(f.root,'Rieke OS.app');
  await fs.writeFile(path.join(cache,receipt),JSON.stringify({format:'rieke-unsigned-testing-update',version:1,validated:true,channel:'unsigned-testing',identifier:'org.riekeos.desktop',operation:'update',install_path:installed,current_version:'0.1.2',target_version:'0.1.3'}),{mode:0o600});
  await fs.writeFile(path.join(cache,receipt+'.result.json'),JSON.stringify({...result,destination:installed}),{mode:0o600});
  const pointer=path.join(cache,'last-install.json');
  await fs.writeFile(pointer,JSON.stringify({format:'rieke-testing-last-install',version:1,receipt}),{mode:0o600});
  return {cache,receipt,pointer};
}
test('private failed installation outcome remains visible after a successful Current check without exposing stderr',async t=>{
  const f=await fixture(t,{manifest:{...current,application_version:'0.1.3'}});
  await lastInstallFixture(f,{state:'Deferred',phase:'replace-bundle',error:'private command path',stderr:'private stderr'});
  await f.coordinator.start();
  const status=f.coordinator.getStatus();assert.equal(status.state,'Current');
  assert.equal(status.last_install.phase,'replace-bundle');assert.match(status.check_error,/could not complete/);
  assert.doesNotMatch(JSON.stringify(status),/private command path|private stderr/);
  assert.equal(status.can_restart,false);assert.equal(f.helperCalls(),0);
  await f.coordinator.check();assert.match(f.coordinator.getStatus().check_error,/replace-bundle/);
});
test('private rollback result explains the restored previous version',async t=>{
  const f=await fixture(t);
  await lastInstallFixture(f,{state:'Restored',version:'0.1.2',failure:{phase:'request-launch',error:'private path'}});
  await f.coordinator.start();
  assert.equal(f.coordinator.getStatus().last_install.state,'Restored');
  assert.match(f.coordinator.getStatus().check_error,/previous app was restored/);
});
test('unsafe last-install pointers and nonprivate helper results are ignored',async t=>{
  for(const fault of ['traversal','symlink','exposed-result','oversized-result','foreign-install','bad-schema']){
    const f=await fixture(t),record=await lastInstallFixture(f,{state:'Deferred',phase:'replace-bundle'});
    if(fault==='traversal')await fs.writeFile(record.pointer,JSON.stringify({format:'rieke-testing-last-install',version:1,receipt:'../'+record.receipt}));
    if(fault==='symlink'){await fs.rename(record.pointer,record.pointer+'.target');await fs.symlink(record.pointer+'.target',record.pointer);}
    if(fault==='exposed-result')await fs.chmod(path.join(record.cache,record.receipt+'.result.json'),0o644);
    if(fault==='oversized-result')await fs.writeFile(path.join(record.cache,record.receipt+'.result.json'),' '.repeat(65537));
    if(fault==='foreign-install'||fault==='bad-schema'){
      const file=path.join(record.cache,record.receipt),receipt=JSON.parse(await fs.readFile(file));
      if(fault==='foreign-install')receipt.install_path='/another/Disco.app';else receipt.version=999;
      await fs.writeFile(file,JSON.stringify(receipt));
    }
    await f.coordinator.start();assert.equal(f.coordinator.getStatus().last_install,undefined,fault);assert.equal(f.helperCalls(),0);
  }
});
test('helper handoff failures retain private diagnostics and show only their phase',async t=>{
  const f=await fixture(t,{installHelper:async()=>{const error=new Error('private command details');error.stderr='private stderr';error.updatePhase='validate-prepared';throw error;}});
  await f.coordinator.start();await f.coordinator.download();await f.coordinator.installPrepared();
  const status=f.coordinator.getStatus();assert.equal(status.last_install.phase,'validate-prepared');
  assert.doesNotMatch(JSON.stringify(status),/private command details|private stderr/);
  const pointer=path.join(f.root,'updates/unsigned-testing/last-install.json');
  const record=JSON.parse(await fs.readFile(pointer));assert.equal(record.failure.error,'private command details');
  assert.equal((await fs.stat(pointer)).mode&0o077,0);
  const restarted=createTestingUpdateCoordinator({app:f.app,manifest:current,distribution,transport:f.transport,hostVersion:'14.2',timers:{setTimeout:()=>({unref(){}}),clearTimeout(){}}});
  try{
    await restarted.start();assert.equal(restarted.getStatus().last_install.phase,'validate-prepared');
    assert.doesNotMatch(JSON.stringify(restarted.getStatus()),/private command details|private stderr/);
  }finally{restarted.stop();await restarted.flushReceipts();}
});
test('truncated and checksum-failed downloads never validate and permit a fresh explicit retry',async t=>{
  const f=await fixture(t);await f.coordinator.start();f.setDownloadFailure();
  await f.coordinator.download();assert.notEqual(f.coordinator.getStatus().state,'Ready');assert.equal(f.validationCalls(),0);
  f.retryDownload();await f.coordinator.download();assert.equal(f.coordinator.getStatus().state,'Ready');
  const bad=await fixture(t);await bad.coordinator.start();bad.corruptDownload();await bad.coordinator.download();
  assert.notEqual(bad.coordinator.getStatus().state,'Ready');assert.equal(bad.validationCalls(),0);
});
test('cached archive corruption during drain revokes install authority',async t=>{
  let target;
  const f=await fixture(t,{prepareQuit:async()=>{await fs.appendFile(target,'changed');return{ready:true};}});
  await f.coordinator.start();await f.coordinator.download();
  const directories=await fs.readdir(path.join(f.root,'updates/unsigned-testing'));
  const candidate=directories.find(x=>x.startsWith('download-'));
  target=path.join(f.root,'updates/unsigned-testing',candidate,descriptor.archive.filename);
  assert.equal((await f.coordinator.installPrepared()).ready,false);assert.equal(f.helperCalls(),0);
});
test('background metadata retry preserves available notice and never consumes the download choice',async t=>{
  let hourly;
  const f=await fixture(t,{timers:{setTimeout:callback=>{hourly=callback;return{unref(){}};},clearTimeout(){}}});
  await f.coordinator.start();assert.equal(f.coordinator.getStatus().can_download,true);f.setMetadataFailure();
  await hourly();assert.equal(f.coordinator.getStatus().state,'Available');assert.equal(f.coordinator.getStatus().available,'0.1.3');
  assert.equal(f.coordinator.getStatus().can_download,true);assert.equal(f.archiveCalls(),0);
  await f.coordinator.download();assert.equal(f.coordinator.getStatus().state,'Ready');assert.equal(f.coordinator.getStatus().can_restart,true);
  const calls=f.metadataCalls();await f.coordinator.check();assert.equal(f.metadataCalls(),calls);assert.equal(f.coordinator.getStatus().state,'Ready');
});
test('cache corruption before drain offers retry without shutting down current services',async t=>{
  const f=await fixture(t);await f.coordinator.start();await f.coordinator.download();
  const directory=(await fs.readdir(path.join(f.root,'updates/unsigned-testing'))).find(x=>x.startsWith('download-'));
  await fs.appendFile(path.join(f.root,'updates/unsigned-testing',directory,descriptor.archive.filename),'changed');
  assert.equal((await f.coordinator.installPrepared()).ready,false);assert.equal(f.drains(),0);assert.equal(f.helperCalls(),0);
  assert.match(f.coordinator.getStatus().message,/Retry the download/);assert.equal(f.coordinator.getStatus().can_download,true);
});
test('a persisted Ready hint cannot authorize installation after restart or a failed metadata check',async t=>{
  const f=await fixture(t);
  const cache=path.join(f.root,'updates/unsigned-testing');await fs.mkdir(cache,{recursive:true});
  await fs.writeFile(path.join(cache,'status.json'),JSON.stringify({format:'rieke-desktop-testing-update-status',version:1,installed:'0.1.2',available:'0.1.3',state:'Ready'}));
  f.setMetadataFailure();await f.coordinator.start();
  assert.equal((await f.coordinator.installPrepared()).ready,false);assert.equal(f.helperCalls(),0);
  assert.equal(f.coordinator.getStatus().can_download,false);assert.equal(f.coordinator.getStatus().can_restart,false);
});
test('ordinary quit preserves downloaded choice; cold start requires fresh official metadata and complete revalidation',async t=>{
  const f=await fixture(t);await f.coordinator.start();await f.coordinator.download();
  f.coordinator.stop();await f.coordinator.flushReceipts();assert.equal(f.helperCalls(),0);
  let validations=0;
  const resumed=createTestingUpdateCoordinator({app:f.app,manifest:current,distribution,transport:f.transport,hostVersion:'14.2',
    timers:{setTimeout:()=>({unref(){}}),clearTimeout(){}},
    revalidateCandidate:async({candidate,descriptor:live})=>{validations++;assert.equal(live.archive.sha256,descriptor.archive.sha256);assert.equal(candidate.bundle_sha256,'c'.repeat(64));return{source_dirty:true};},
    prepareQuit:async()=>({ready:false})});
  const metadataBefore=f.metadataCalls();await resumed.start();assert.ok(f.metadataCalls()>metadataBefore);
  assert.equal(resumed.getStatus().state,'Ready');assert.equal(resumed.getStatus().source_dirty,true);assert.equal(validations,1);
  assert.equal(f.archiveCalls(),1);assert.equal(f.helperCalls(),0);
  resumed.stop();await resumed.flushReceipts();
});
test('a changed cached archive or linked resume hint offers a fresh download without install authority',async t=>{
  const f=await fixture(t);await f.coordinator.start();await f.coordinator.download();f.coordinator.stop();await f.coordinator.flushReceipts();
  const cache=path.join(f.root,'updates/unsigned-testing'),hint=JSON.parse(await fs.readFile(path.join(cache,'prepared.json'),'utf8'));
  await fs.appendFile(path.join(cache,hint.archive_relative_path),'changed');
  let revalidated=0;
  const options={app:f.app,manifest:current,distribution,transport:f.transport,hostVersion:'14.2',timers:{setTimeout:()=>1,clearTimeout(){}},revalidateCandidate:async()=>{revalidated++;}};
  const resumed=createTestingUpdateCoordinator(options);await resumed.start();assert.equal(resumed.getStatus().state,'Available');assert.equal(resumed.getStatus().can_download,true);
  assert.equal(revalidated,0);assert.equal((await resumed.installPrepared()).ready,false);resumed.stop();await resumed.flushReceipts();
  const unrelated=path.join(f.root,'outside-hint.json');await fs.writeFile(unrelated,JSON.stringify(hint));await fs.symlink(unrelated,path.join(cache,'prepared.json'));
  const linked=createTestingUpdateCoordinator(options);await linked.start();assert.equal(linked.getStatus().state,'Available');assert.equal((await linked.installPrepared()).ready,false);
  assert.equal(await fs.readFile(unrelated,'utf8'),JSON.stringify(hint));linked.stop();await linked.flushReceipts();
});
test('obsolete-cache cleanup removes only old owned generated directories and preserves links/unrelated files',async t=>{
  const f=await fixture(t);await f.coordinator.start();
  const cache=path.join(f.root,'updates/unsigned-testing'),old=new Date(Date.now()-48*3600000);
  for(const name of ['download-old000','candidate-old111','unrelated-user-data']){await fs.mkdir(path.join(cache,name));await fs.writeFile(path.join(cache,name,'retained'),'fixture');await fs.utimes(path.join(cache,name),old,old);}
  const outside=path.join(f.root,'outside');await fs.mkdir(outside);await fs.writeFile(path.join(outside,'keep'),'safe');
  await fs.symlink(outside,path.join(cache,'candidate-link00'));
  await f.coordinator.download();assert.equal(f.coordinator.getStatus().state,'Ready');
  await assert.rejects(fs.access(path.join(cache,'download-old000')));await assert.rejects(fs.access(path.join(cache,'candidate-old111')));
  assert.equal(await fs.readFile(path.join(outside,'keep'),'utf8'),'safe');assert.ok((await fs.lstat(path.join(cache,'candidate-link00'))).isSymbolicLink());
  assert.equal(await fs.readFile(path.join(cache,'unrelated-user-data/retained'),'utf8'),'fixture');
});
test('drain deferral preserves candidate; stopping during acknowledged drain prevents handoff',async t=>{
  const blocked=await fixture(t,{prepareQuit:async()=>({ready:false,reason:'writer active'})});
  await blocked.coordinator.start();await blocked.coordinator.download();assert.equal((await blocked.coordinator.installPrepared()).ready,false);
  assert.equal(blocked.coordinator.getStatus().state,'Ready');assert.equal(blocked.helperCalls(),0);
  let coordinator;
  const stopped=await fixture(t,{prepareQuit:async()=>{coordinator.stop();return{ready:true};}});coordinator=stopped.coordinator;
  await coordinator.start();await coordinator.download();assert.equal((await coordinator.installPrepared()).ready,false);assert.equal(stopped.helperCalls(),0);
});
test('symlinked cache root and foreign explicit distribution never gain update authority',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-test-cache-link-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
  await fs.mkdir(path.join(root,'outside'));await fs.symlink(path.join(root,'outside'),path.join(root,'updates'));
  const f=await fixture(t,{app:{isPackaged:true,getPath:()=>root}});await f.coordinator.start();await f.coordinator.download();
  assert.notEqual(f.coordinator.getStatus().state,'Ready');assert.equal(f.validationCalls(),0);
  const wrong=await fixture(t,{distribution:{...distribution,repository:'foreign/repo'}});await wrong.coordinator.start();
  assert.equal(wrong.coordinator.getStatus().state,'Deferred');assert.equal(wrong.archiveCalls(),0);
});
async function bundleFixture(t){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-testing-bundle-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const bundle=path.join(root,'Rieke OS.app'),runtime=path.join(bundle,'Contents/Resources/runtime');
  const data={
    'python/bin/python3.11':'candidate code must never execute',
    'mysql/bin/mysqld':'candidate native code must never execute',
    'application/python/workspace_desktop.py':'raise Exception("candidate executed")',
    'frontend/index.html':'frontend',
    'application/rieke-release.json':JSON.stringify({version:'0.1.3',workspace_formats:[1],database_compatibility:1}),
    'application/python/workspace-source.json':JSON.stringify({commit:'b'.repeat(40),python:'3.11.13'})};
  const resources={};
  for(const [name,text]of Object.entries(data)){
    const file=path.join(runtime,name);await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,text,{mode:name.includes('/bin/')?0o755:0o644});
    resources[name]={sha256:crypto.createHash('sha256').update(text).digest('hex'),size:Buffer.byteLength(text),executable:name.includes('/bin/')};
  }
  const candidate={...current,format:'rieke-desktop-runtime',version:1,application_version:'0.1.3',minimum_macos_version:'14.0',source_dirty:true,source_commit:'a'.repeat(40),parser_commit:'b'.repeat(40),python_version:'3.11.13',resources};
  const manifestFile=path.join(runtime,'runtime-manifest.json');await fs.writeFile(manifestFile,JSON.stringify(candidate));
  await fs.mkdir(path.join(bundle,'Contents/MacOS'));await fs.writeFile(path.join(bundle,'Contents/MacOS/Rieke OS'),'do not execute',{mode:0o755});
  const plist='<?xml version="1.0"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleExecutable</key><string>Rieke OS</string><key>CFBundleIdentifier</key><string>org.riekeos.desktop</string><key>CFBundleShortVersionString</key><string>0.1.3</string><key>LSMinimumSystemVersion</key><string>14.0</string></dict></plist>';
  await fs.writeFile(path.join(bundle,'Contents/Info.plist'),plist);
  await fs.writeFile(path.join(bundle,'Contents/Resources/app.asar'),'test asar');
  const next={...descriptor,asar_sha256:crypto.createHash('sha256').update('test asar').digest('hex'),runtime_manifest_sha256:crypto.createHash('sha256').update(JSON.stringify(candidate)).digest('hex')};
  const bundleDigest=require('../../bootstrap.cjs').bundleDigest;
  const execute=require('node:util').promisify(require('node:child_process').execFile);
  // Tiny fixture is not Mach-O; all boundaries except structural seal checking
  // use the actual OS tools. Packaged E2E checks the real seal without this seam.
  const run=async(exe,args,options)=>exe==='/usr/bin/codesign'?{stdout:'',stderr:''}:execute(exe,args,options);
  return{root,bundle,runtime,descriptor:next,candidate,bundleDigest,run};
}
test('actual extracted testing bundle permits declared dirty provenance and rejects changed resources/control links',{skip:process.platform!=='darwin'},async t=>{
  const f=await bundleFixture(t);
  const options={bundle:f.bundle,descriptor:f.descriptor,manifest:current,hostVersion:'14.2',bundleDigest:f.bundleDigest,run:f.run};
  const result=await inspectTestingBundle(options);assert.equal(result.source_dirty,true);assert.equal(result.developer_id_verified,false);
  await assert.rejects(inspectTestingBundle({...options,run:async(exe,args,config)=>{if(exe==='/usr/bin/codesign')throw new Error('damaged structural seal');return f.run(exe,args,config);}}),/damaged structural seal/);
  const file=path.join(f.runtime,'frontend/index.html');await fs.appendFile(file,'corrupt');await assert.rejects(inspectTestingBundle(options),/metadata|checksum/);await fs.writeFile(file,'frontend');
  const asar=path.join(f.bundle,'Contents/Resources/app.asar');await fs.rename(asar,asar+'.copy');await fs.symlink('app.asar.copy',asar);
  await assert.rejects(inspectTestingBundle(options),/regular contained/);
});
test('built-in bundle inspection rejects resource or manifest changes at the final scan boundary',{skip:process.platform!=='darwin'},async t=>{
  for(const mutation of ['same-size-resource','manifest-bytes']){
    const f=await bundleFixture(t);
    const run=async(exe,args,options)=>{
      if(exe==='/usr/bin/codesign'){
        if(mutation==='same-size-resource')await fs.writeFile(path.join(f.runtime,'frontend/index.html'),'FrontEnd');
        else await fs.appendFile(path.join(f.runtime,'runtime-manifest.json'),' ');
        return {stdout:'',stderr:''};
      }
      return f.run(exe,args,options);
    };
    await assert.rejects(inspectTestingBundle({bundle:f.bundle,descriptor:f.descriptor,manifest:current,hostVersion:'14.2',run}),/checksum|manifest/i,mutation);
  }
});
test('an injected bundle digest cannot bypass independent resource verification',{skip:process.platform!=='darwin'},async t=>{
  const f=await bundleFixture(t);let calls=0;
  const bundleDigest=async()=>{calls++;return 'c'.repeat(64);};
  const options={bundle:f.bundle,descriptor:f.descriptor,manifest:current,hostVersion:'14.2',run:f.run,bundleDigest};
  await inspectTestingBundle(options);assert.equal(calls,1);
  await fs.writeFile(path.join(f.runtime,'frontend/index.html'),'FrontEnd');
  await assert.rejects(inspectTestingBundle(options),/checksum/);assert.equal(calls,1);
});
test('real ZIP preflight/extraction uses installed interpreter and never executes candidate code',{skip:process.platform!=='darwin'},async t=>{
  const f=await bundleFixture(t);
  const {promisify}=require('node:util'),run=promisify(require('node:child_process').execFile);
  // Keep this legacy-name candidate paired with an owned legacy-name install
  // fixture even when this checkout contains a packaged Disco.app. Only its
  // trusted interpreter is borrowed; candidate bytes are never executed.
  let trustedPython;
  try{
    const packaged=require('../../e2e/packaged-path.cjs').packagedSource(path.resolve(__dirname,'../..'),require('../../package.json').build);
    trustedPython=path.join(packaged,'Contents/Resources/runtime/python/bin/python3.11');await fs.access(trustedPython);
  }catch{trustedPython=(await run('/usr/bin/which',['python3'])).stdout.trim();}
  const installedBundle=path.join(f.root,'installed','Rieke OS.app');
  const python=path.join(installedBundle,'Contents/Resources/runtime/python/bin/python3.11');
  await fs.mkdir(path.dirname(python),{recursive:true});await fs.symlink(trustedPython,python);
  const archive=path.join(f.root,'Rieke-OS-0.1.3-arm64.zip');
  const generate=String.raw`import os,sys,zipfile
from pathlib import Path
root=Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2],'w',zipfile.ZIP_DEFLATED) as z:
 for file in root.rglob('*'):
  if file.is_file():z.write(file,str(file.relative_to(root.parent)))
`;
  await run(python,['-I','-B','-c',generate,f.bundle,archive]);
  const body=await fs.readFile(archive);
  const next={...f.descriptor,archive:{...descriptor.archive,size:body.length,sha256:crypto.createHash('sha256').update(body).digest('hex'),sha512:crypto.createHash('sha512').update(body).digest('base64')}};
  const executed=[];
  const validated=await validateTestingCandidate({downloadedFile:archive,descriptor:next,manifest:current,hostVersion:'14.2',cacheDirectory:f.root,installedBundle,bundleDigest:f.bundleDigest,run:async(exe,args,options)=>{executed.push(exe);return f.run(exe,args,options);}});
  assert.equal(validated.validated,true);assert.equal(validated.bundle_sha256,await f.bundleDigest(f.bundle));
  assert.ok(executed.every(exe=>exe===python||exe==='/usr/bin/ditto'||exe==='/usr/libexec/PlistBuddy'||exe==='/usr/bin/codesign'));
  assert.ok(!executed.some(exe=>exe.startsWith(f.bundle)));
  await fs.writeFile(path.join(validated.bundle_path,'extra-after-validation'),'changed full app closure');
  await assert.rejects(revalidateTestingCandidate({candidate:validated,descriptor:next,manifest:current,hostVersion:'14.2',run:f.run}),/Prepared app bundle changed/);
});

test('default feed discovers and downloads the existing repository release and keeps its live link',async t=>{
 const f=await fixture(t);await f.coordinator.start();
 assert.equal(f.metadataCalls(),1);
 assert.equal(f.coordinator.getStatus().state,'Available');
 assert.equal(f.coordinator.getStatus().release_url,'https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.3');
 await f.coordinator.download();assert.equal(f.coordinator.getStatus().state,'Ready');assert.equal(f.archiveCalls(),1);
});

test('Disco archive schema is accepted alongside exact legacy release names',()=>{
 for(const name of ['Disco-0.1.3-arm64.zip','Rieke-OS-0.1.3-arm64.zip'])
  assert.equal(validateDescriptor({...descriptor,archive:{...descriptor.archive,filename:name}},current,'14.2').archive.filename,name);
 for(const name of ['Disco-0.1.3-x64.zip','Disco-0.1.4-arm64.zip','Other-0.1.3-arm64.zip'])
  assert.throws(()=>validateDescriptor({...descriptor,archive:{...descriptor.archive,filename:name}},current,'14.2'));
});
test('Disco candidate uses its declared executable and rejects mismatched legacy declaration',{skip:process.platform!=='darwin'},async t=>{
 const f=await bundleFixture(t);
 await fs.rename(path.join(f.bundle,'Contents/MacOS/Rieke OS'),path.join(f.bundle,'Contents/MacOS/Disco'));
 const file=path.join(f.bundle,'Contents/Info.plist'),original=await fs.readFile(file,'utf8');
 const options={bundle:f.bundle,descriptor:{...f.descriptor,archive:{...f.descriptor.archive,filename:'Disco-0.1.3-arm64.zip'}},manifest:current,hostVersion:'14.2',bundleDigest:f.bundleDigest,run:f.run};
 await assert.rejects(inspectTestingBundle(options),/property list/);
 await fs.writeFile(file,original.replace('<string>Rieke OS</string>','<string>Disco</string>'));
 assert.equal((await inspectTestingBundle(options)).validated,true);
});

test('legacy-name update offered to Disco requests manual installation before any download',async t=>{
 const f=await fixture(t,{installedBundle:'/owned/Applications/Disco.app'});await f.coordinator.start();
 assert.equal(f.coordinator.getStatus().state,'Deferred');assert.match(f.coordinator.getStatus().message,/Install and Open manually/);
 assert.equal(f.archiveCalls(),0);assert.equal(f.drains(),0);assert.equal(f.helperCalls(),0);
});
