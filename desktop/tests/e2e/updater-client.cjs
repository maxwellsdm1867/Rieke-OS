'use strict';
// Run with the pinned Electron executable. This exercises its real HTTP
// executor, pinned MacUpdater parser/downloader and app coordinator against a
// private fault server. It does not substitute for a signed Squirrel update.
const {app, autoUpdater: nativeUpdater} = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {MacUpdater} = require('electron-updater');
const {ElectronHttpExecutor} = require('electron-updater/out/electronHttpExecutor');
const {createUpdateCoordinator} = require('../../updater.cjs');
const root = path.resolve(__dirname, '../../..');
const payload = Buffer.alloc(256 * 1024, 23);
const unhandled = [];
process.on('unhandledRejection', error => unhandled.push(error.code || error.name || 'unknown'));
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function eventually(predicate, timeout = 10000) {
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){if(predicate())return;await wait(30);}
  throw new Error('Updater scenario deadline exceeded');
}
async function scenario(base, fault, report) {
  const dir=path.join(base,fault);await fs.mkdir(dir,{recursive:true});
  const configuration=path.join(dir,'app-update.yml');
  await fs.writeFile(configuration,'updaterCacheDirName: candidate-cache\n');
  if(fault==='cache-write-failure'){
    await fs.mkdir(path.join(dir,'candidate-cache'));
    await fs.writeFile(path.join(dir,'candidate-cache','pending'),'not a writable directory');
  }
  let requests=0,downloads=0,installs=0;
  const version=fault==='older-version'?'0.0.9':fault==='current-version'?'0.1.0':fault==='invalid-version'?'invalid':'0.1.1';
  const metadata={version,files:[{url:'candidate-arm64.zip',size:payload.length,sha512:crypto.createHash('sha512').update(fault==='bad-checksum'?Buffer.from('bad'):payload).digest('base64')}],path:'candidate-arm64.zip',releaseDate:'2026-09-30T00:00:00.000Z'};
  const server=http.createServer((request,response)=>{
    requests++;
    if(request.url.includes('latest-mac.yml')){
      if(fault==='metadata-unavailable'){response.writeHead(503);response.end('unavailable');return;}
      response.setHeader('Content-Type','application/yaml');
      response.end(fault==='malformed-metadata'?'files: [invalid':JSON.stringify(metadata));return;
    }
    downloads++;
    response.writeHead(200,{'Content-Type':'application/zip','Content-Length':payload.length});
    if(fault==='interrupted-download'||(fault==='interrupted-download-fresh-client'&&downloads===1)){response.write(payload.subarray(0,1024));setTimeout(()=>response.destroy(),25);}
    else response.end(payload);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const feed=`http://127.0.0.1:${server.address().port}/`;
  const adapter={version:'0.1.0',name:'Rieke updater isolated E2E',isPackaged:true,appUpdateConfigPath:configuration,userDataPath:dir,baseCachePath:dir,
    whenReady:()=>app.whenReady(),onQuit:()=>{},quit:()=>assert.fail('Client cannot quit app in rejected scenarios'),relaunch:()=>assert.fail('Client cannot relaunch app')};
  let updater;
  const states=[];
  function createClient(){
  updater=new MacUpdater(undefined,adapter);
  updater.httpExecutor=new ElectronHttpExecutor(()=>{});
  updater.logger=null;
  updater.disableDifferentialDownload=true;
  const setFeed=updater.setFeedURL.bind(updater);
  // Substitute only the delivery destination. The production provider arguments
  // are asserted and every HTTP/metadata/cache operation remains real.
  updater.setFeedURL=provider=>{
    assert.equal(provider.provider,'github');assert.equal(provider.owner,'maxwellsdm1867');assert.equal(provider.repo,'Rieke-OS');
    setFeed({provider:'generic',url:feed});
  };
  updater.quitAndInstall=()=>{installs++;assert.fail('Rejected update cannot install');};
  return createUpdateCoordinator({app:{isPackaged:true,getPath:()=>dir},manifest:{application_version:'0.1.0'},updater,
    verifyInstalled:async()=>({fixture_only:true}),
    // The candidate's real production verifier cannot accept an unsigned test
    // bundle. Transport success must end rejected, with no native installer.
    verifyCandidate:async()=>{throw new Error('No Developer ID test candidate');},retainPrevious:async()=>assert.fail('Rejected candidate cannot retain/activate'),
    prepareQuit:async()=>assert.fail('Rejected candidate cannot drain app'),publishStatus:status=>states.push(status.state),
    timers:{setTimeout:()=>1,clearTimeout:()=>{}}});
  }
  const nativeListeners=new Map(['error','update-downloaded'].map(name=>[name,nativeUpdater.listeners(name)]));
  let coordinator=createClient();
  const initialUnhandled=unhandled.length;
  try{
    await coordinator.start();
    if(['bad-checksum','interrupted-download','interrupted-download-fresh-client','unsigned-candidate','cache-write-failure'].includes(fault))await eventually(()=>states.includes('Deferred'));
    await wait(100);
    if(fault==='interrupted-download-fresh-client'){
      assert.equal(downloads,1);assert.equal(coordinator.getStatus().state,'Deferred');
      coordinator.stop();updater.closeServerIfExists();states.length=0;
      coordinator=createClient();await coordinator.start();
      await eventually(()=>states.includes('Deferred'));await wait(100);
      assert.equal(downloads,2,'A fresh real client must fetch complete bytes instead of using the interrupted cache');
      assert.equal(adapter.version,'0.1.0');
    }
    const final=coordinator.getStatus().state;
    assert.equal(final,['older-version','current-version'].includes(fault)?'Current':'Deferred');
    assert.equal(installs,0);
    assert.equal(updater.autoInstallOnAppQuit,false);
    assert.equal(unhandled.length,initialUnhandled,`Unhandled real downloader rejection for ${fault}`);
    if(['older-version','current-version','invalid-version','malformed-metadata','metadata-unavailable','cache-write-failure'].includes(fault))assert.equal(downloads,0);
    report.scenarios.push({name:fault,passed:true,requests,downloads,final_state:final,native_installs:installs});
  }finally{
    coordinator.stop();updater.closeServerIfExists();
    await new Promise(resolve=>server.close(resolve));
    for(const [event,listeners] of nativeListeners)for(const listener of listeners)nativeUpdater.removeListener(event,listener);
  }
}
async function main(){
  const base=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-updater-client-e2e-'));
  await fs.mkdir(path.join(base,'electron-profile'));
  app.setPath('userData',path.join(base,'electron-profile'));
  await app.whenReady();
  const report={format:'rieke-updater-client-e2e',version:1,production_ready:false,library_version:require('electron-updater/package.json').version,
    scenarios:[],limitations:['Private fixture provider and test app identity; no Developer ID candidate','Real signed Squirrel staging/install/recovery remains unqualified']};
  try{
    for(const fault of ['current-version','older-version','metadata-unavailable','malformed-metadata','invalid-version','bad-checksum','interrupted-download','interrupted-download-fresh-client','cache-write-failure','unsigned-candidate'])await scenario(base,fault,report);
    report.passed=true;
  }catch(error){report.passed=false;report.failure=error.message;process.exitCode=1;}
  report.unhandled_rejections=unhandled;
  await fs.writeFile(path.join(root,'docs/dev/desktop-updater-client-e2e.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
  app.exit(report.passed?0:1);
}
main().catch(error=>{console.error(error.name+': '+error.message);app.exit(1);});
