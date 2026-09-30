'use strict';
// Qualification harness only: observe an owned helper without signaling it.
const fs=require('node:fs/promises'),path=require('node:path');
const {promisify}=require('node:util'),run=promisify(require('node:child_process').execFile);
async function readHelperResult(file){
 let stat;
 try{stat=await fs.lstat(file);}catch(error){if(error.code==='ENOENT')return null;throw error;}
 if(!stat.isFile()||stat.isSymbolicLink()||stat.uid!==process.getuid()||stat.size>65536)throw new Error('Helper result is not a bounded owned regular file');
 const value=JSON.parse(await fs.readFile(file,'utf8'));
 if(!value||Array.isArray(value)||typeof value!=='object'||!['Installed','Restored','Deferred'].includes(value.state))throw new Error('Helper result has an invalid outcome schema');
 return value;
}
async function inspectOwnedHelper(pid,{wrapper,configFile}){
 if(!Number.isSafeInteger(pid)||pid<=0)throw new Error('Owned helper PID is invalid');
 for(const file of[wrapper,configFile]){
  const stat=await fs.lstat(file);
  if(!path.isAbsolute(file)||!stat.isFile()||stat.isSymbolicLink()||stat.uid!==process.getuid())throw new Error('Helper observation requires owned regular wrapper and config files');
 }
 let stdout;
 try{({stdout}=await run('/bin/ps',['-ww','-p',String(pid),'-o','stat=,command=']));}
 catch(error){if(error.code===1&&!error.stdout?.trim())return{alive:false,owned:false,status:'absent'};throw error;}
 const match=/^\s*(\S+)\s+(.+?)\s*$/.exec(stdout);
 if(!match)throw new Error('Owned helper process observation is malformed');
 const contains=file=>new RegExp('(?:^|\\s)'+file.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?:\\s|$)').test(match[2]);
 return {alive:!match[1].includes('Z'),owned:contains(wrapper)&&contains(configFile),status:match[1]};
}
async function waitForHelperResult({resultPath,helperPid,wrapper,configFile,phase,timeoutMs=15*60*1000,pollMs=500,heartbeatMs=60000,longWaitMs=300000,
 readResult=readHelperResult,inspectHelper=inspectOwnedHelper,now=Date.now,delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),onHeartbeat=()=>{},onObservation=()=>{},onDiagnostics=()=>{}}){
 for(const[name,value]of Object.entries({timeoutMs,pollMs,heartbeatMs,longWaitMs}))if(!Number.isFinite(value)||value<=0)throw new TypeError(`${name} must be a finite positive duration`);
 if(timeoutMs>15*60*1000)throw new RangeError('Helper result deadline cannot exceed fifteen minutes');
 const started=now();let heartbeatAt=started,previous,diagnosed=false;
 for(;;){
  const result=await readResult(resultPath);if(result)return{result,elapsed_ms:now()-started};
  const processState=await inspectHelper(helperPid,{wrapper,configFile}),elapsed=now()-started;
  const observation={phase,elapsed_ms:elapsed,...processState},identity=JSON.stringify(processState);
  if(identity!==previous){await onObservation(observation);previous=identity;}
  if(!processState.alive||!processState.owned){
   // The helper can exit immediately after atomically publishing its result.
   const finalResult=await readResult(resultPath);if(finalResult)return{result:finalResult,elapsed_ms:now()-started};
   const error=new Error(processState.status.includes('Z')?'Owned native helper is a zombie without a final result':!processState.alive?'Owned native helper exited without a final result':'Native helper PID was reused or no longer belongs to the owned wrapper');
   error.observation=observation;throw error;
  }
  if(elapsed>=timeoutMs){const finalResult=await readResult(resultPath);if(finalResult)return{result:finalResult,elapsed_ms:now()-started};await onDiagnostics({...observation,reason:'timeout'});const error=new Error('Owned native helper remained alive but exceeded the bounded result deadline');error.observation=observation;throw error;}
  if(!diagnosed&&elapsed>=longWaitMs){await onDiagnostics({...observation,reason:'long-wait'});diagnosed=true;}
  if(now()-heartbeatAt>=heartbeatMs){await onHeartbeat(observation);await onObservation(observation);heartbeatAt=now();}
  await delay(Math.min(pollMs,timeoutMs-elapsed));
 }
}
async function captureHelperDiagnostics({helperPid,wrapper,configFile,directory,phase,reason,runCommand=run}){
 const observation=await inspectOwnedHelper(helperPid,{wrapper,configFile});
 const result={phase,reason,captured_at:new Date().toISOString(),process:observation,category:'unclassified',errors:[]};
 if(!observation.alive||!observation.owned)return{...result,category:'helper-no-longer-owned'};
 const destination=path.join(directory,`${phase}-helper-${reason}`),sampleFile=destination+'.sample.txt';
 const bounded=value=>String(value||'').slice(0,65536);
 try{
  const ps=await runCommand('/bin/ps',['-ww','-p',String(helperPid),'-o','pid=,stat=,%cpu=,etime=,command='],{timeout:5000,maxBuffer:128*1024});
  result.ps=bounded(ps.stdout);
 }catch(error){result.errors.push({operation:'ps',code:error.code,message:bounded(error.message)});}
 try{
  // Only sample the exact still-owned helper; never a reused PID/user app.
  const current=await inspectOwnedHelper(helperPid,{wrapper,configFile});
  if(current.alive&&current.owned){
   await runCommand('/usr/bin/sample',[String(helperPid),'1','1','-file',sampleFile],{timeout:10000,maxBuffer:128*1024});
   const handle=await fs.open(sampleFile,'r');let text;
   try{result.sample_truncated=(await handle.stat()).size>65536;const bytes=Buffer.alloc(65536);const read=await handle.read(bytes,0,bytes.length,0);text=bytes.subarray(0,read.bytesRead).toString('utf8');}finally{await handle.close();}
   await fs.writeFile(sampleFile,text,{mode:0o600});await fs.chmod(sampleFile,0o600);result.sample_path=sampleFile;result.category='sample-captured-unclassified';
  }
 }catch(error){result.errors.push({operation:'sample',code:error.code,message:bounded(error.message)});}
 try{
  const quote=value=>JSON.stringify(value);
  const predicate=`process == "tccd" AND eventMessage CONTAINS[c] "org.riekeos.desktop" AND (eventMessage CONTAINS[c] ${quote(directory)} OR eventMessage CONTAINS[c] ${quote('pid='+helperPid)} OR eventMessage CONTAINS[c] ${quote('pid: '+helperPid)})`;
  const log=await runCommand('/usr/bin/log',['show','--last','5m','--style','compact','--predicate',predicate],{timeout:10000,maxBuffer:128*1024});
  // A numeric substring in the OS predicate may match another PID. Keep only
  // fixture path or exact PID evidence, excluding the real user's app logs.
  const pid=new RegExp('\\bpid(?:=|: ?)' +helperPid+'\\b','i');
  result.tcc_log=bounded(log.stdout.split('\n').filter(line=>line.includes(directory)||pid.test(line)).join('\n'));
  if(result.tcc_log)result.category='fixture-tcc-evidence';
 }catch(error){result.errors.push({operation:'log-show',code:error.code,message:bounded(error.message)});}
 await fs.writeFile(destination+'.json',JSON.stringify(result,null,2)+'\n',{mode:0o600});
 return result;
}
module.exports={waitForHelperResult,readHelperResult,inspectOwnedHelper,captureHelperDiagnostics};
