'use strict';
const physicalFS=require('./physical-fs.cjs');
const fs=physicalFS.promises,path=require('node:path'),crypto=require('node:crypto');
const {constants}=physicalFS;
const {promisify}=require('node:util');
const runFile=promisify(require('node:child_process').execFile);
const {compareVersions,compatibleMacMinimum,verifyResources,ARCHIVE_CHECK}=require('./updater-validation.cjs');
const REPOSITORY='maxwellsdm1867/Rieke-OS';
function approvedURL(value,kind='asset',redirect=false){
  const url=new URL(value);
  if(url.protocol!=='https:'||url.username||url.password||url.hash||(url.port&&url.port!=='443'))throw new Error('Only public GitHub HTTPS downloads are accepted.');
  if(kind==='api'){
    if(url.hostname!=='api.github.com'||url.pathname!==`/repos/${REPOSITORY}/releases`)throw new Error('Unexpected release API.');
  }else if(url.hostname==='github.com'){
    if(!url.pathname.startsWith(`/${REPOSITORY}/releases/download/`)||url.search||decodeURIComponent(url.pathname).split('/').some(p=>p==='..'||p==='.')||/%2f|%5c/i.test(url.pathname))throw new Error('Unexpected release asset.');
  }else if(!redirect||!['release-assets.githubusercontent.com','objects.githubusercontent.com','github-releases.githubusercontent.com'].includes(url.hostname))throw new Error('Unexpected asset redirect.');
  return true;
}
function validateDescriptor(value,current,hostVersion){
  if(!value||value.format!=='rieke-desktop-test-release'||value.version!==1||value.channel!=='unsigned-testing'||value.repository!==REPOSITORY)throw new Error('Unexpected testing release provenance.');
  if(compareVersions(value.application_version,current.application_version)<=0)throw new Error('Testing update must be newer than the installed app.');
  if(value.platform!=='darwin'||value.architecture!=='arm64'||current.platform!==value.platform||current.architecture!==value.architecture)throw new Error('Unsupported testing platform.');
  if(value.mysql_version!==current.mysql_version||value.database_compatibility!==current.database_compatibility||!Array.isArray(value.workspace_formats)||!Array.isArray(current.workspace_formats)||!current.workspace_formats.every(f=>value.workspace_formats.includes(f)))throw new Error('Testing update requires a data migration.');
  compatibleMacMinimum(value.minimum_macos_version,hostVersion);
  const archive=value.archive;
  if(!archive||archive.filename!==`Rieke-OS-${value.application_version}-arm64.zip`||!Number.isSafeInteger(archive.size)||archive.size<=0||archive.size>2*1024**3||!/^[a-f0-9]{64}$/.test(archive.sha256||'')||!/^[A-Za-z0-9+/]{86}==$/.test(archive.sha512||'')||Buffer.from(archive.sha512,'base64').length!==64)throw new Error('Invalid testing archive metadata.');
  if(!/^[a-f0-9]{64}$/.test(value.asar_sha256||'')||!/^[a-f0-9]{64}$/.test(value.runtime_manifest_sha256||''))throw new Error('Incomplete testing app checksums.');
  return value;
}
async function hashFile(file,algorithm='sha256'){
  const handle=await fs.open(file,constants.O_RDONLY|constants.O_NOFOLLOW);
  try{
    const stat=await handle.stat();if(!stat.isFile())throw new Error('Expected a regular file.');
    const hash=crypto.createHash(algorithm);for await(const chunk of handle.createReadStream({autoClose:false}))hash.update(chunk);
    return hash.digest(algorithm==='sha512'?'base64':'hex');
  }finally{await handle.close();}
}
async function verifyArchive(file,descriptor){
  const info=await fs.lstat(file);
  if(!info.isFile()||info.isSymbolicLink()||info.uid!==process.getuid()||info.size!==descriptor.archive.size)throw new Error('Prepared archive size or ownership changed.');
  if(await hashFile(file)!==descriptor.archive.sha256||await hashFile(file,'sha512')!==descriptor.archive.sha512)throw new Error('Testing archive checksum failed.');
}
async function ensurePrivateCache(userData){
  await fs.mkdir(userData,{recursive:true,mode:0o700});
  let directory=userData;
  for(const part of ['', 'updates','unsigned-testing']){
    if(part)directory=path.join(directory,part);
    await fs.mkdir(directory,{recursive:true,mode:0o700});
    const stat=await fs.lstat(directory);
    if(!stat.isDirectory()||stat.isSymbolicLink()||stat.uid!==process.getuid())throw new Error('Update cache must be owned and contain no directory links.');
    if(part)await fs.chmod(directory,0o700);
  }
  return directory;
}
async function regularContained(bundle,relative){
  const file=path.join(bundle,relative),stat=await fs.lstat(file),resolved=await fs.realpath(file),root=await fs.realpath(bundle);
  if(!stat.isFile()||stat.isSymbolicLink()||!resolved.startsWith(root+path.sep))throw new Error('App control files must be regular contained files.');
  let parent=path.dirname(file);
  while(parent!==bundle){if((await fs.lstat(parent)).isSymbolicLink())throw new Error('App control directories cannot be links.');parent=path.dirname(parent);}
  return file;
}
async function inspectTestingBundle({bundle,descriptor,manifest,hostVersion,run=runFile,bundleDigest}){
  validateDescriptor(descriptor,manifest,hostVersion);
  const root=await fs.realpath(bundle);
  if((await fs.lstat(bundle)).isSymbolicLink())throw new Error('Candidate app cannot be a symlink.');
  async function links(directory){
    for(const entry of await fs.readdir(directory,{withFileTypes:true})){
      const file=path.join(directory,entry.name);
      if(entry.isSymbolicLink()){
        const target=await fs.readlink(file),physical=await fs.realpath(file);
        if(path.isAbsolute(target)||!physical.startsWith(root+path.sep))throw new Error('App has an escaping link.');
      }else if(entry.isDirectory())await links(file);
      else if(!entry.isFile())throw new Error('App has a special filesystem node.');
    }
  }
  await links(bundle);
  const plist=await regularContained(bundle,'Contents/Info.plist');
  const entry=await regularContained(bundle,'Contents/MacOS/Rieke OS');
  if(!((await fs.stat(entry)).mode&0o111))throw new Error('App entry is not executable.');
  const asar=await regularContained(bundle,'Contents/Resources/app.asar');
  const manifestPath=await regularContained(bundle,'Contents/Resources/runtime/runtime-manifest.json');
  if(await hashFile(asar)!==descriptor.asar_sha256||await hashFile(manifestPath)!==descriptor.runtime_manifest_sha256)throw new Error('Testing app identity checksums differ.');
  const candidate=JSON.parse(await fs.readFile(manifestPath,'utf8'));
  if(candidate.format!=='rieke-desktop-runtime'||candidate.version!==1||candidate.application_version!==descriptor.application_version||candidate.platform!==descriptor.platform||candidate.architecture!==descriptor.architecture||candidate.mysql_version!==descriptor.mysql_version||candidate.database_compatibility!==descriptor.database_compatibility||JSON.stringify(candidate.workspace_formats)!==JSON.stringify(descriptor.workspace_formats)||candidate.minimum_macos_version!==descriptor.minimum_macos_version||!/^[a-f0-9]{40}$/.test(candidate.source_commit||'')||!/^[a-f0-9]{40}$/.test(candidate.parser_commit||'')||typeof candidate.source_dirty!=='boolean'||!candidate.resources||typeof candidate.resources!=='object'||Array.isArray(candidate.resources)||!Object.keys(candidate.resources).length)throw new Error('Testing runtime differs from its descriptor.');
  for(const [key,expected] of [['CFBundleIdentifier','org.riekeos.desktop'],['CFBundleShortVersionString',descriptor.application_version],['LSMinimumSystemVersion',descriptor.minimum_macos_version]]){
    const result=await run('/usr/libexec/PlistBuddy',['-c',`Print :${key}`,plist]);
    if(result.stdout.trim()!==expected)throw new Error('App property list differs from testing metadata.');
  }
  const runtime=path.join(bundle,'Contents/Resources/runtime');
  for(const relative of ['python/bin/python3.11','mysql/bin/mysqld','application/python/workspace_desktop.py','frontend/index.html']){
    if(!candidate.resources[relative])throw new Error('Required private runtime entry is absent.');
    await regularContained(bundle,'Contents/Resources/runtime/'+relative);
  }
  for(const relative of ['python/bin/python3.11','mysql/bin/mysqld'])if(candidate.resources[relative].executable!==true)throw new Error('Private native runtime entry is not executable.');
  const releasePath=await regularContained(bundle,'Contents/Resources/runtime/application/rieke-release.json');
  const sourcePath=await regularContained(bundle,'Contents/Resources/runtime/application/python/workspace-source.json');
  const release=JSON.parse(await fs.readFile(releasePath,'utf8')),source=JSON.parse(await fs.readFile(sourcePath,'utf8'));
  if(release.version!==candidate.application_version||release.database_compatibility!==candidate.database_compatibility||JSON.stringify(release.workspace_formats)!==JSON.stringify(candidate.workspace_formats)||source.commit!==candidate.parser_commit||source.python!==candidate.python_version)throw new Error('Runtime compatibility differs from application declarations.');
  await verifyResources(runtime,candidate.resources);
  // Structural integrity accepts an ad-hoc testing seal; this is not a
  // Developer ID, notarization, or Gatekeeper authorization assertion.
  await run('/usr/bin/codesign',['--verify','--deep','--strict',bundle],{timeout:180000});
  bundleDigest||=require('./testing-install.cjs').bundleDigest;
  return {version:descriptor.application_version,bundle_path:bundle,bundle_sha256:await bundleDigest(bundle),runtime_manifest_sha256:descriptor.runtime_manifest_sha256,validated:true,source_dirty:candidate.source_dirty,trust:'official-repository-https-checksums',developer_id_verified:false,native_staging_verified:false,startup_health_verified:false};
}
async function validateTestingCandidate({downloadedFile,descriptor,manifest,cacheDirectory,installedBundle,hostVersion,run=runFile,bundleDigest}){
  await verifyArchive(downloadedFile,descriptor);
  const temporary=await fs.mkdtemp(path.join(cacheDirectory,'candidate-'));
  try{
    const python=path.join(installedBundle,'Contents/Resources/runtime/python/bin/python3.11');
    // Only the current trusted Python parses the ZIP. No candidate code executes.
    await run(python,['-I','-B','-c',ARCHIVE_CHECK,downloadedFile],{timeout:30000});
    await run('/usr/bin/ditto',['-x','-k',downloadedFile,temporary],{timeout:180000});
    const entries=await fs.readdir(temporary);
    if(entries.length!==1||entries[0]!=='Rieke OS.app')throw new Error('Testing archive must contain exactly Rieke OS.app.');
    const validated=await inspectTestingBundle({bundle:path.join(temporary,entries[0]),descriptor,manifest,hostVersion,run,bundleDigest});
    await verifyArchive(downloadedFile,descriptor);
    return {...validated,downloadedFile,archive_sha256:descriptor.archive.sha256,candidate_directory:temporary};
  }catch(error){await fs.rm(temporary,{recursive:true,force:true});throw error;}
}
async function revalidateTestingCandidate({candidate,descriptor,manifest,hostVersion,run=runFile,bundleDigest}){
  await verifyArchive(candidate.downloadedFile,descriptor);
  const result=await inspectTestingBundle({bundle:candidate.bundle_path,descriptor,manifest,hostVersion,run,bundleDigest});
  if(result.bundle_sha256!==candidate.bundle_sha256)throw new Error('Prepared app bundle changed.');
  return result;
}
module.exports={REPOSITORY,approvedURL,validateDescriptor,hashFile,verifyArchive,ensurePrivateCache,inspectTestingBundle,validateTestingCandidate,revalidateTestingCandidate};
