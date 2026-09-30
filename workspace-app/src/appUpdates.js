const releaseRoot='https://github.com/maxwellsdm1867/Rieke-OS/releases';
export function releaseLink(value){
  if(typeof value!=='string')return null;
  try{const url=new URL(value);return url.origin==='https://github.com'&&(url.pathname==='/maxwellsdm1867/Rieke-OS/releases'||url.pathname.startsWith('/maxwellsdm1867/Rieke-OS/releases/tag/'))&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
export function updateNotice(status){
  const version=typeof status?.available==='string'?status.available:status?.available?.version;
  return (status?.state==='update_available'||['Available','Downloading','Validating','Ready','Draining','Installing'].includes(status?.state))&&version?{version,message:`Rieke OS ${version} is available`,url:releaseLink(status.release_url)||releaseRoot}:null;
}

// A failed refresh does not erase a release we already discovered. A successful
// response (including a withdrawn release) replaces the previous status.
export function mergeUpdateCheck(previous,result){
  if(result?.state!=='error')return result;
  if(!updateNotice(previous))return {...previous,...result};
  return {...previous,...result,state:previous.state,available:previous.available,
    release_url:previous.release_url,release_notes:previous.release_notes,
    checked_at:previous.checked_at,check_error:result.message};
}

export function updateLabel(status,busy=false){
  if(busy&&!status)return 'Checking for updates…';
  if(updateNotice(status))return 'Update available';
  return ({up_to_date:'Up to date',unavailable:'No release published',error:'Update check unavailable'})[status?.state]||'App updates';
}

export function watchAppUpdates(check,{interval=15*60*1000,setTimer=setInterval,clearTimer=clearInterval,documentObject=globalThis.document,now=Date.now}={}){
  let lastCheck=0;
  const run=()=>{lastCheck=now();check();};
  const visible=()=>{if(documentObject?.visibilityState==='visible'&&now()-lastCheck>=interval)run();};
  run();
  const timer=setTimer(()=>{if(!documentObject||documentObject.visibilityState==='visible')run();},interval);
  documentObject?.addEventListener('visibilitychange',visible);
  return()=>{clearTimer(timer);documentObject?.removeEventListener('visibilitychange',visible);};
}
