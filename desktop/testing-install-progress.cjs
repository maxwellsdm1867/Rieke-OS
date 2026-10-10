'use strict';
// This observer grants no installation/quit authority. The installer owns every
// record and decision; the view can close without changing the operation.
const physical=require('./physical-fs.cjs');
const fs=physical.promises,path=require('node:path'),{timingSafeEqual}=require('node:crypto'),{spawn}=require('node:child_process');
const UI=require('./testing-install-progress-ui.cjs');
const FORMAT='rieke-unsigned-testing-progress',MAX_RECORD_BYTES=16384;
const PHASE_LABELS=Object.freeze({
 'prepare-helper':'Preparing the update…','validate-prepared':'Checking the prepared update…',
 'wait-parent-exit':'Waiting for Disco to close…','validate-after-exit':'Checking the update after Disco closes…',
 'validate-installed':'Checking the installed app…','verify-source':'Checking the new app…',
 'verify-current':'Checking the installed app…','copy-bundle':'Copying the new app…',
 'verify-staging':'Verifying the copied app…','activate-bundle':'Replacing Disco…',
 'replace-bundle':'Installing the new app…','save-rollback-receipt':'Saving update recovery information…',
 'request-launch':'Opening Disco…','restore-previous':'Restoring the previous app…'
});
function reject(message){const error=new Error(message);error.code='PROGRESS_UNAVAILABLE';return error;}
function sameSecret(left,right){return typeof left==='string'&&/^[a-f0-9]{64}$/.test(left)&&timingSafeEqual(Buffer.from(left),Buffer.from(right));}
function binding({progressPath,operationId,capability}){
 if(typeof progressPath!=='string'||!path.isAbsolute(progressPath)||path.normalize(progressPath)!==progressPath||
  !/^(?:install|restore)-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(operationId||'')||
  path.basename(progressPath)!==operationId+'.json.progress.json'||
  path.basename(path.dirname(progressPath))!=='unsigned-testing'||path.basename(path.dirname(path.dirname(progressPath)))!=='updates'||
  !/^[a-f0-9]{64}$/.test(capability||''))throw reject('The update progress operation is not a valid private binding.');
 return {progressPath,operationId,capability};
}
async function readProgressRecord(options,{now=Date.now(),staleMs=120000}={}){
 const {progressPath,operationId,capability}=binding(options),cache=path.dirname(progressPath);
 for(const directory of [cache,path.dirname(cache),path.dirname(path.dirname(cache))]){
  const info=await fs.lstat(directory);
  if(!info.isDirectory()||info.isSymbolicLink()||info.uid!==process.getuid()||(directory===cache&&(info.mode&0o077)))throw reject('The update progress directory is not private and owned.');
 }
 if(await fs.realpath(cache)!==cache)throw reject('The update progress directory contains a redirected path.');
 const handle=await fs.open(progressPath,physical.constants.O_RDONLY|physical.constants.O_NOFOLLOW);
 try{
  const stat=await handle.stat();
  if(!stat.isFile()||stat.uid!==process.getuid()||(stat.mode&0o777)!==0o600||stat.nlink>1||stat.size<1||stat.size>MAX_RECORD_BYTES)throw reject('The update progress record is not a bounded private file.');
  const data=Buffer.alloc(MAX_RECORD_BYTES+1);let used=0;
  while(used<data.length){const {bytesRead}=await handle.read(data,used,data.length-used,used);if(!bytesRead)break;used+=bytesRead;}
  if(used!==stat.size||used>MAX_RECORD_BYTES)throw reject('The update progress record changed size while reading.');
  let record;try{record=JSON.parse(data.subarray(0,used).toString('utf8'));}catch{throw reject('The update progress record is malformed.');}
  const updated=Date.parse(record.updated_at);
  if(record.format!==FORMAT||record.version!==1||record.operation_id!==operationId||!sameSecret(record.capability,capability)||
   !Number.isSafeInteger(record.helper_pid)||record.helper_pid<=0||!Number.isFinite(updated)||
   !['Running','Installed','Restored','Deferred'].includes(record.state)||typeof record.phase!=='string'||!/^[a-z][a-z0-9-]{0,63}$/.test(record.phase)||
   (record.progress!==undefined&&record.progress!==null&&(typeof record.progress!=='number'||!Number.isFinite(record.progress)||record.progress<0||record.progress>100))||
   (record.message!==undefined&&(typeof record.message!=='string'||record.message.length>512)))throw reject('The update progress record does not match this operation.');
  if(updated>now+5000||now-updated>staleMs)throw reject('The updater has stopped reporting fresh progress.');
  return {state:record.state,phase:record.phase,progress:record.progress??null,helperPid:record.helper_pid,updatedAt:updated};
 }finally{await handle.close();}
}
function displayFrame(record,timing){
 const terminal={Installed:['Update installed','Opening Disco…'],Restored:['Previous app restored','Opening Disco…'],Deferred:['The update could not finish','Reopen Disco to view the update result.']};
 const text=terminal[record.state]||[PHASE_LABELS[record.phase]||'Updating Disco…','Please leave Disco closed while the update finishes.'];
 return {format:'disco-progress-view',version:1,state:record.state,label:text[0],detail:text[1],progress:record.state==='Running'?record.progress:null,timing};
}
function launchProgressReporter({progressPath,operationId,capability,onError=()=>{},spawnReporter=spawn,timers=globalThis,now=Date.now,platform=process.platform,pollMs=250,staleMs=120000,maxLifetimeMs=20*60*1000,successDisplayMs=2000,failureDisplayMs=20000}={}){
 let child=null,timer=null,finished=false,closing=false,reading=null,last=null,lastFrame=null,lastError=null,resolveClosed;
 const closed=new Promise(resolve=>{resolveClosed=resolve;}),started=now();
 const options={progressPath,operationId,capability},timing={successMs:successDisplayMs,failureMs:failureDisplayMs,staleMs};
 function reportError(){if(lastError)return;lastError={code:'PROGRESS_UNAVAILABLE',message:'The native update progress window is unavailable.'};try{onError({...lastError});}catch{}}
 function stopTimer(){if(timer!==null){timers.clearTimeout(timer);timer=null;}}
 function endInput(){try{child?.stdin?.end();}catch{}}
 function finish(reason){if(finished)return;finished=true;stopTimer();resolveClosed({reason,...(lastError?{error:lastError}:{})});}
 function send(frame){if(!child?.stdin||child.stdin.destroyed)return;try{child.stdin.write(JSON.stringify(frame)+'\n',error=>{if(error&&!finished&&!closing)unavailable();});}catch{if(!finished&&!closing)unavailable();}}
 function unavailable(){if(finished)return;reportError();closing=true;stopTimer();if(child){send({format:'disco-progress-view',version:1,state:'Deferred',label:'Update progress is unavailable',detail:'Please wait for Disco to reopen.',progress:null,timing});endInput();}else finish('unavailable');}
 function show(record){
  if(last&&(record.helperPid!==last.helperPid||record.updatedAt<last.updatedAt))throw reject('The update progress identity changed.');
  last=record;const frame=displayFrame(record,timing),key=JSON.stringify(frame);
  // A repeated valid heartbeat is still forwarded so a long native command
  // remains visibly alive; this never fabricates a percentage.
  if(key!==lastFrame||record.state==='Running'){send(frame);lastFrame=key;}
  if(record.state!=='Running'){closing=true;stopTimer();endInput();}
 }
 async function read(){if(reading)return reading;reading=readProgressRecord(options,{now:now(),staleMs}).finally(()=>{reading=null;});return reading;}
 async function tick(){
  if(finished||closing)return;
  try{if(now()-started>maxLifetimeMs)throw reject('The progress observer exceeded its lifetime.');show(await read());}
  catch{unavailable();return;}
  if(!closing&&!finished){timer=timers.setTimeout(()=>{void tick();},pollMs);timer.unref?.();}
 }
 async function close(){
  if(finished||closing)return;
  closing=true;stopTimer();
  if(!child){finish('closed');return;}
  // One last bounded read prevents a terminal record being lost when the
  // installer exits between polling ticks. Never wait for window dismissal.
  let deadline;
  try{const finalRead=async()=>{if(reading)await reading.catch(()=>{});return readProgressRecord(options,{now:now(),staleMs});};const record=await Promise.race([finalRead(),new Promise((_resolve,rejectTimeout)=>{deadline=timers.setTimeout(()=>rejectTimeout(reject('Progress close timeout.')),1000);})]);show(record);}
  catch{reportError();}
  finally{if(deadline!==undefined)timers.clearTimeout(deadline);endInput();}
 }
 void (async()=>{
  try{
   binding(options);if(platform!=='darwin')throw reject('Native progress is available only on macOS.');
   const initial=await read();if(finished||closing)return;
   child=spawnReporter('/usr/bin/osascript',['-l','JavaScript','-e',UI],{detached:true,stdio:['pipe','ignore','pipe'],env:{PATH:'/usr/bin:/bin',LANG:process.env.LANG||'en_US.UTF-8'}});
   child.once('error',()=>{unavailable();finish('unavailable');});child.once('exit',code=>{if(code!==0&&!lastError)reportError();finish(code===0?'closed':'unavailable');});
   child.stdin.on('error',()=>{if(!closing&&!finished)unavailable();});child.stderr?.on('data',()=>{});
   child.unref?.();child.stdin.unref?.();child.stderr?.unref?.();
   show(initial);if(!closing)timer=timers.setTimeout(()=>{void tick();},pollMs);
   timer?.unref?.();
  }catch{unavailable();}
 })();
 return {closed,close,get pid(){return child?.pid??null;},get error(){return lastError;}};
}
module.exports={FORMAT,MAX_RECORD_BYTES,PHASE_LABELS,readProgressRecord,displayFrame,launchProgressReporter};
