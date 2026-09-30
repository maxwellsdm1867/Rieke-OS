'use strict';
const physicalFS=require('./physical-fs.cjs');
const fs=physicalFS.promises,path=require('node:path'),crypto=require('node:crypto'),https=require('node:https');
const {constants}=physicalFS;
const {promisify}=require('node:util');
const runFile=promisify(require('node:child_process').execFile);
const {compareVersions}=require('./updater-validation.cjs');
const {REPOSITORY,approvedURL,validateDescriptor,verifyArchive,ensurePrivateCache,validateTestingCandidate,revalidateTestingCandidate,hashFile}=require('./testing-update-validation.cjs');
const API=`https://api.github.com/repos/${REPOSITORY}/releases?per_page=100&page=1`;
async function atomicHint(cache,value){
  const temporary=path.join(cache,`prepared-${crypto.randomUUID()}.tmp`),file=path.join(cache,'prepared.json');
  const handle=await fs.open(temporary,'wx',0o600);
  try{await handle.writeFile(JSON.stringify(value)+'\n');await handle.sync();}finally{await handle.close();}
  try{await fs.rename(temporary,file);const parent=await fs.open(cache,'r');try{await parent.sync();}finally{await parent.close();}}
  finally{await fs.rm(temporary,{force:true});}
}
async function hintPath(cache,relative,kind,filename){
  const parts=typeof relative==='string'?relative.split('/'):[];
  if(parts.length!==2||!new RegExp(`^${kind}-[a-zA-Z0-9]{6}$`).test(parts[0])||parts[1]!==filename)throw new Error('Invalid prepared-cache hint.');
  const parent=path.join(cache,parts[0]),file=path.join(parent,parts[1]);
  for(const item of [parent,file]){const stat=await fs.lstat(item);if(stat.isSymbolicLink()||stat.uid!==process.getuid())throw new Error('Prepared cache link or ownership differs.');}
  if(!((await fs.lstat(parent)).isDirectory())||!((await fs.realpath(file)).startsWith((await fs.realpath(cache))+path.sep)))throw new Error('Prepared cache escapes its owned directory.');
  return file;
}
async function cleanupObsolete(cache,keep=[]){
  // Age protects another still-completing installation. No receipts, previous
  // bundles, user-selected paths, or non-cache directories are ever removed.
  const retained=new Set(keep.map(file=>path.resolve(file)));
  for(const name of await fs.readdir(cache)){
    if(!/^(?:download|candidate)-[a-zA-Z0-9]{6}$/.test(name))continue;
    const file=path.join(cache,name),info=await fs.lstat(file);
    if(!retained.has(file)&&info.isDirectory()&&!info.isSymbolicLink()&&info.uid===process.getuid()&&Date.now()-info.mtimeMs>24*3600000)await fs.rm(file,{recursive:true,force:true});
  }
}
function httpsTransport(url,{kind='asset',redirects=0}={}){
  approvedURL(url,kind,redirects>0);
  return new Promise((resolve,reject)=>{
    const request=https.get(url,{headers:{'User-Agent':'Rieke-OS-desktop-testing-updater','Accept':kind==='api'?'application/vnd.github+json':'application/octet-stream'}},response=>{
      if([301,302,303,307,308].includes(response.statusCode)){
        response.resume();
        if(redirects>=5||!response.headers.location)return reject(new Error('Release redirect limit.'));
        let next;try{next=new URL(response.headers.location,url).href;approvedURL(next,kind,true);}catch(error){return reject(error);}
        resolve(httpsTransport(next,{kind,redirects:redirects+1}));
      }else resolve({statusCode:response.statusCode,headers:response.headers,body:response});
    });
    request.setTimeout(30000,()=>request.destroy(new Error('Testing update network timeout.')));
    request.on('error',reject);
  });
}
async function responseFor(transport,url,kind){
  approvedURL(url,kind);
  const response=await transport(url,{kind});
  if(response.statusCode!==200){response.body?.destroy?.();throw new Error('Release server did not return an asset.');}
  return response;
}
async function jsonAt(transport,url,kind='asset'){
  const response=await responseFor(transport,url,kind),chunks=[];let size=0;
  for await(const chunk of response.body){size+=chunk.length;if(size>1024*1024){response.body.destroy?.();throw new Error('Release metadata exceeds bounds.');}chunks.push(chunk);}
  if(response.headers?.['content-length']&&Number(response.headers['content-length'])!==size)throw new Error('Release metadata truncated.');
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}
function assetURL(asset,tag,name){
  const expected=`https://github.com/${REPOSITORY}/releases/download/${encodeURIComponent(tag)}/${encodeURIComponent(name)}`;
  if(!asset||asset.name!==name||asset.browser_download_url!==expected)throw new Error('Release asset is not in the official repository.');
  approvedURL(expected,'asset');return expected;
}
function createTestingUpdateCoordinator({app,manifest,distribution,publishStatus=()=>{},prepareQuit,authorizeQuit=()=>{},revokeQuit=()=>{},onInstallationFailure=()=>{},installedBundle,transport=httpsTransport,verifyCandidate=validateTestingCandidate,revalidateCandidate=revalidateTestingCandidate,installHelper,processIdentity,hostVersion,timers=globalThis,random=Math.random,enabled}){
  installedBundle||=path.resolve(app.getPath('exe'),'../../..');
  let status={state:'Current',installed:manifest.application_version,available:null,channel:'unsigned-testing',manual_updates:true,can_download:false,can_restart:false,developer_id_verified:false,message:'Using the installed testing version.'};
  let active=false,stopped=false,timer=null,checking=null,downloading=null,installing=null,pending=null,offered=null;
  let receiptWrites=Promise.resolve();
  function set(state,fields={}){
    status={...status,...fields,state,can_download:state==='Available'&&Boolean(offered),can_restart:state==='Ready'&&Boolean(pending)};publishStatus({...status});
    const snapshot={format:'rieke-desktop-testing-update-status',version:1,installed:status.installed,available:status.available,state,checked_at:status.checked_at||null};
    receiptWrites=receiptWrites.catch(()=>{}).then(async()=>{
      const cache=await ensurePrivateCache(app.getPath('userData'));
      const temporary=path.join(cache,`status-${crypto.randomUUID()}.tmp`);
      await fs.writeFile(temporary,JSON.stringify(snapshot)+'\n',{mode:0o600,flag:'wx'});
      await fs.rename(temporary,path.join(cache,'status.json'));
    }).catch(()=>{});
    return {...status};
  }
  function deferred(message){return set(pending?'Ready':offered?'Available':'Deferred',{message,check_error:message});}
  async function forgetHint(){try{const cache=await ensurePrivateCache(app.getPath('userData'));await fs.rm(path.join(cache,'prepared.json'),{force:true});}catch{}}
  async function persistPrepared(cache,candidate,descriptor){
    const hint={format:'rieke-desktop-testing-prepared-hint',version:1,installed_version:manifest.application_version,
      available_version:candidate.version,archive_relative_path:path.relative(cache,candidate.downloadedFile).split(path.sep).join('/'),
      bundle_relative_path:path.relative(cache,candidate.bundle_path).split(path.sep).join('/'),
      archive_sha256:descriptor.archive.sha256,bundle_sha256:candidate.bundle_sha256,runtime_manifest_sha256:descriptor.runtime_manifest_sha256};
    await hintPath(cache,hint.archive_relative_path,'download',descriptor.archive.filename);
    await hintPath(cache,hint.bundle_relative_path,'candidate','Rieke OS.app');
    await atomicHint(cache,hint);
  }
  async function resumePrepared(selected){
    const cache=await ensurePrivateCache(app.getPath('userData')),file=path.join(cache,'prepared.json');
    let candidate=null;
    try{
      const handle=await fs.open(file,constants.O_RDONLY|constants.O_NOFOLLOW);
      let hint;
      try{const stat=await handle.stat();if(!stat.isFile()||stat.uid!==process.getuid()||(stat.mode&0o077)||stat.size>65536)throw new Error('Invalid prepared hint ownership.');hint=JSON.parse(await handle.readFile('utf8'));}finally{await handle.close();}
      const descriptor=selected.descriptor;
      if(hint.format!=='rieke-desktop-testing-prepared-hint'||hint.version!==1||hint.installed_version!==manifest.application_version||hint.available_version!==descriptor.application_version||hint.archive_sha256!==descriptor.archive.sha256||hint.runtime_manifest_sha256!==descriptor.runtime_manifest_sha256||!/^[a-f0-9]{64}$/.test(hint.bundle_sha256||''))throw new Error('Prepared hint differs from fresh official metadata.');
      const downloadedFile=await hintPath(cache,hint.archive_relative_path,'download',descriptor.archive.filename);
      const bundle=await hintPath(cache,hint.bundle_relative_path,'candidate','Rieke OS.app');
      candidate={version:descriptor.application_version,downloadedFile,bundle_path:bundle,bundle_sha256:hint.bundle_sha256,
        archive_sha256:descriptor.archive.sha256,runtime_manifest_sha256:descriptor.runtime_manifest_sha256,validated:true,descriptor,candidate_directory:path.dirname(bundle)};
      set('Validating',{message:'Rechecking the previously downloaded testing update against current GitHub metadata.'});
      await verifyArchive(downloadedFile,descriptor);
      const checked=await revalidateCandidate({candidate,descriptor,manifest,hostVersion});
      if(stopped)throw new Error('Updater stopped.');
      pending={...candidate,source_dirty:checked?.source_dirty};
      set('Ready',{source_dirty:pending.source_dirty,trust:'official-repository-https-checksums',developer_id_verified:false,message:'Previously downloaded unsigned testing update verified again. Restart to update when ready.'});
      await cleanupObsolete(cache,[path.dirname(downloadedFile),path.dirname(bundle)]).catch(()=>{});
      return true;
    }catch{if(!stopped)await forgetHint();return false;}
  }
  function schedule(){
    if(stopped||!active)return;
    timer=timers.setTimeout(async()=>{await check();schedule();},Math.round(3600000*(0.9+random()*0.2)));timer?.unref?.();
  }
  async function check(){
    if(!active||stopped||pending||downloading||installing)return {...status};
    if(checking)return checking;
    checking=(async()=>{
      set('Checking',{checked_at:new Date().toISOString(),check_error:null,message:'Checking the official GitHub testing releases.'});
      try{
        const releases=await jsonAt(transport,API,'api');
        if(!Array.isArray(releases)||releases.length>100)throw new Error('Invalid testing release list.');
        const relevant=releases.filter(release=>{
          if(release?.draft||typeof release.tag_name!=='string')return false;
          const match=/^(?:v|desktop-test-v)(\d+\.\d+\.\d+)$/.exec(release.tag_name);
          try{return match&&compareVersions(match[1],manifest.application_version)>0;}catch{return false;}
        }).sort((a,b)=>compareVersions(b.tag_name.replace(/^(?:v|desktop-test-v)/,''),a.tag_name.replace(/^(?:v|desktop-test-v)/,'')));
        let candidate=null,rejections=0;
        for(const release of relevant.slice(0,20)){
          const assets=release.assets;
          if(!Array.isArray(assets))continue;
          const descriptors=assets.filter(asset=>asset?.name==='desktop-release.json');
          if(descriptors.length!==1)continue;
          try{
            const descriptor=validateDescriptor(await jsonAt(transport,assetURL(descriptors[0],release.tag_name,'desktop-release.json')),manifest,hostVersion);
            if(release.tag_name!==`v${descriptor.application_version}`&&release.tag_name!==`desktop-test-v${descriptor.application_version}`)throw new Error('Release tag differs from app version.');
            const archives=assets.filter(asset=>asset?.name===descriptor.archive.filename);
            if(archives.length!==1||archives[0].size!==descriptor.archive.size)throw new Error('Archive metadata differs from descriptor.');
            candidate={descriptor,url:assetURL(archives[0],release.tag_name,descriptor.archive.filename),release_url:`https://github.com/${REPOSITORY}/releases/tag/${encodeURIComponent(release.tag_name)}`};break;
          }catch{rejections++;}
        }
        if(stopped)return {...status};
        if(candidate){
          offered=candidate;set('Available',{available:candidate.descriptor.application_version,release_url:candidate.release_url,source_dirty:null,message:`Rieke OS ${candidate.descriptor.application_version} testing update is available. Download when ready.`,check_error:null});
          if(!await resumePrepared(candidate)&&!stopped)set('Available',{message:'Testing update available. Download when ready; any missing or changed cached update will be replaced.'});
        }
        else if(rejections)deferred('Published testing update metadata was rejected. The installed app remains usable.');
        else{offered=null;set('Current',{available:null,message:'The installed testing version is current.',check_error:null});}
      }catch{deferred('Testing update check unavailable. The installed app remains usable.');}
      return {...status};
    })().finally(()=>{checking=null;});return checking;
  }
  async function start(){
    if(active||stopped)return {...status};
    if(enabled===false||!app.isPackaged||process.platform!=='darwin'||process.arch!=='arm64'||distribution?.format!=='rieke-desktop-distribution'||distribution.version!==1||distribution.channel!=='unsigned-testing'||distribution.repository!==REPOSITORY)return set('Deferred',{message:'This distribution does not enable GitHub testing updates.'});
    try{
      hostVersion||=(await runFile('/usr/bin/sw_vers',['-productVersion'])).stdout.trim();
      const cache=await ensurePrivateCache(app.getPath('userData'));
      // Disk status is a display hint, never authority to install or restore.
      try{const hint=JSON.parse(await fs.readFile(path.join(cache,'status.json'),'utf8'));if(hint.format==='rieke-desktop-testing-update-status'&&hint.installed===manifest.application_version)status.available=hint.available;}catch{}
    }catch{return set('Deferred',{message:'The testing update cache is unavailable.'});}
    active=true;await check();schedule();return {...status};
  }
  async function download(){
    if(!active||stopped)return {...status};
    if(downloading)return downloading;
    if(installing||pending)return {...status};
    if(checking)await checking;
    if(pending)return {...status};
    if(!offered)return {...status};
    const selected=offered;
    downloading=(async()=>{
      let directory=null,candidate=null;
      try{
        set('Downloading',{progress:0,check_error:null,message:'Downloading the selected unsigned testing update.'});
        const cache=await ensurePrivateCache(app.getPath('userData'));
        directory=await fs.mkdtemp(path.join(cache,'download-'));
        const file=path.join(directory,selected.descriptor.archive.filename);
        const response=await responseFor(transport,selected.url,'asset');
        if(response.headers?.['content-length']&&Number(response.headers['content-length'])!==selected.descriptor.archive.size){response.body.destroy?.();throw new Error('Archive length differs.');}
        const output=await fs.open(file,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);
        let size=0,lastPercent=-1,lastPublished=0;
        try{
          for await(const chunk of response.body){
            size+=chunk.length;if(stopped||size>selected.descriptor.archive.size){response.body.destroy?.();throw new Error('Archive download interrupted or oversized.');}
            await output.writeFile(chunk);
            const percent=Math.min(100,Math.floor(100*size/selected.descriptor.archive.size)),now=Date.now();
            if(percent!==lastPercent||now-lastPublished>=200){set('Downloading',{progress:percent});lastPercent=percent;lastPublished=now;}
          }
          await output.sync();
        }finally{await output.close();}
        await verifyArchive(file,selected.descriptor);
        set('Validating',{progress:100,message:'Checking the testing app checksums and data compatibility.'});
        candidate=await verifyCandidate({downloadedFile:file,descriptor:selected.descriptor,manifest,cacheDirectory:cache,installedBundle,hostVersion});
        if(stopped)throw new Error('Updater stopped.');
        await persistPrepared(cache,candidate,selected.descriptor);
        pending={...candidate,descriptor:selected.descriptor};
        set('Ready',{available:candidate.version,source_dirty:candidate.source_dirty,trust:'official-repository-https-checksums',developer_id_verified:false,message:'Unsigned testing update verified. Restart to update when your work is saved.'});
        await cleanupObsolete(cache,[directory,candidate.candidate_directory||path.dirname(candidate.bundle_path)]).catch(()=>{});
      }catch{
        if(candidate?.candidate_directory)await fs.rm(candidate.candidate_directory,{recursive:true,force:true});
        if(directory)await fs.rm(directory,{recursive:true,force:true});
        pending=null;await forgetHint();deferred('Testing update download or validation failed. You can retry the download.');
      }
      return {...status};
    })().finally(()=>{downloading=null;});return downloading;
  }
  async function verifyPrepared(){
    await ensurePrivateCache(app.getPath('userData'));
    await verifyArchive(pending.downloadedFile,pending.descriptor);
    await revalidateCandidate({candidate:pending,descriptor:pending.descriptor,manifest,hostVersion});
  }
  async function installPrepared(){
    if(installing)return installing;
    if(downloading)await downloading;
    if(!active||stopped||!pending||status.state!=='Ready')return{ready:false,reason:'No verified testing update is prepared.'};
    installing=(async()=>{
      let drained=false;
      try{
        await verifyPrepared();set('Draining',{message:'Saving drafts and closing scientific services before updating.'});
        const result=await prepareQuit();
        if(result?.ready!==true){set('Ready',{message:'Testing update remains pending until drafts, writers and services close.'});return{ready:false,reason:result?.reason||status.message};}
        drained=true;await verifyPrepared();if(stopped)throw new Error('Updater stopped during drain.');
        const helper=(!processIdentity||!installHelper)?require('./testing-install.cjs'):{};
        const identity=await (processIdentity||helper.processCreationIdentity)(process.pid,app.getPath('exe'));
        const cache=await ensurePrivateCache(app.getPath('userData'));
        const receiptPath=path.join(cache,`install-${crypto.randomUUID()}.json`);
        const receipt={format:'rieke-unsigned-testing-update',version:1,channel:'unsigned-testing',identifier:'org.riekeos.desktop',operation:'update',install_path:installedBundle,current_executable:typeof identity==='object'?identity.executable:app.getPath('exe'),current_pid:process.pid,current_created_at:typeof identity==='object'?identity.created_at:identity,current_version:manifest.application_version,current_manifest_sha256:await hashFile(path.join(installedBundle,'Contents/Resources/runtime/runtime-manifest.json')),target_version:pending.version,runtime_manifest_sha256:pending.runtime_manifest_sha256,archive_path:pending.downloadedFile,archive_sha256:pending.archive_sha256,bundle_path:pending.bundle_path,bundle_sha256:pending.bundle_sha256,validated:true};
        // Version is separately named because receipt.version identifies schema.
        await fs.writeFile(receiptPath,JSON.stringify(receipt)+'\n',{mode:0o600,flag:'wx'});
        set('Installing',{message:'Handing the verified unsigned testing app to the owned installer.'});
        const handoff=await (installHelper||helper.launchTestingInstall)({receiptPath,currentExecutable:receipt.current_executable,currentPid:process.pid});
        if(handoff?.ready===false)throw new Error('Testing installer did not acknowledge readiness.');
        authorizeQuit();app.quit?.();return{ready:true,installing:true};
      }catch{
        revokeQuit();pending=null;await forgetHint();deferred(drained?'Testing update changed or installation failed. Restart the installed app from recovery.':'The prepared testing update changed or is unavailable. Retry the download; the installed app remains usable.');
        if(drained)onInstallationFailure();return{ready:false,reason:status.message};
      }
    })().finally(()=>{installing=null;});return installing;
  }
  function stop(){stopped=true;active=false;if(timer)timers.clearTimeout(timer);}
  return{getStatus:()=>({...status}),start,check,download,installPrepared,stop,flushReceipts:()=>receiptWrites};
}
module.exports={createTestingUpdateCoordinator,httpsTransport};
