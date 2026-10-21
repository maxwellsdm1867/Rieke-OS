import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const execute=promisify(execFile);

export async function readFrontmost(helper){
 if(typeof helper!=='string'||!helper.startsWith('/'))throw Error('Absolute read-only foreground helper required');
 const {stdout}=await execute(helper,[],{timeout:2000,maxBuffer:4096});
 const value=JSON.parse(stdout);
 if(!Number.isSafeInteger(value.pid)||value.pid<2||typeof value.active!=='boolean')throw Error('Malformed foreground identity');
 return value;
}
export function requireOwnedForeground(dom,native,ownerPid){
 if(dom?.visibility!=='visible'||dom?.focus!==true)throw Error('Environment admission failed: page is not visible and DOM-focused');
 if(!Number.isSafeInteger(ownerPid)||ownerPid<2||native?.pid!==ownerPid||native?.active!==true)throw Error('Environment admission failed: owned browser is not the frontmost macOS application');
 return {dom,native,owner_pid:ownerPid,focus_emulation:'Playwright default; OS PID independently checked'};
}
export async function acquireForeground(page,ownerPid,helper,read=readFrontmost,timeoutMs=5000){
 const started=Date.now();let timer;
 const admission=(async()=>{
  await page.bringToFront();
  await page.waitForFunction(()=>document.visibilityState==='visible'&&document.hasFocus(),null,{timeout:timeoutMs,polling:50});
  const dom=await page.evaluate(()=>({visibility:document.visibilityState,focus:document.hasFocus()}));
  const native=await read(helper);
  return {...requireOwnedForeground(dom,native,ownerPid),setup_elapsed_ms:Date.now()-started};
 })();
 try{return await Promise.race([admission,new Promise((_resolve,reject)=>{timer=setTimeout(()=>reject(Error('Environment admission timed out before intent')),timeoutMs);})]);}
 finally{clearTimeout(timer);}
}
export async function verifyForeground(page,ownerPid,helper,read=readFrontmost){
 const dom=await page.evaluate(()=>({visibility:document.visibilityState,focus:document.hasFocus()}));
 return requireOwnedForeground(dom,await read(helper),ownerPid);
}
export function requireObservedFocus(diagnostic){
 const observed=[...(diagnostic?.frames??[]),...(diagnostic?.readiness??[])];
 if(!observed.length||observed.some(row=>row.visibility!=='visible'||row.focus!==true))throw Error('Environment admission failed: visibility/DOM focus changed during observation');
}
