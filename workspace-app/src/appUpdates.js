const releaseRoot='https://github.com/maxwellsdm1867/disco/releases';
export function releaseLink(value){
  if(typeof value!=='string')return null;
  try{const url=new URL(value);return url.origin==='https://github.com'&&['disco','Rieke-OS'].some(repo=>url.pathname===`/maxwellsdm1867/${repo}/releases`||url.pathname.startsWith(`/maxwellsdm1867/${repo}/releases/tag/`))&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
export function updateNotice(status){
  const version=typeof status?.available==='string'?status.available:status?.available?.version;
  return (status?.state==='update_available'||['Available','Downloading','Validating','Ready','Draining','Installing'].includes(status?.state))&&version?{version,message:`Disco ${version} is available`,url:releaseLink(status.release_url)||releaseRoot}:null;
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

// A host-only session cookie spans localhost ports during launcher/project
// navigation. It contains bounded display claims, never update authority or
// scientific state. Existing per-origin session storage remains the fallback.
const discoveryCookie='rieke_update_discovery';
const maxDiscoveryClaims=12;
function cookieClaims(documentObject){
 try{
  const encoded=documentObject?.cookie?.split(';').map(value=>value.trim()).find(value=>value.startsWith(`${discoveryCookie}=`))?.slice(discoveryCookie.length+1);
  const value=encoded?JSON.parse(decodeURIComponent(encoded)):[];
  return Array.isArray(value)?value.filter(key=>typeof key==='string'&&key.startsWith('rieke.update.discovered.')&&key.length<=200).slice(-maxDiscoveryClaims):[];
 }catch{return [];}
}
function rememberDiscoveryCookie(documentObject,claims,key){
 if(key.length>200)return;
 try{if(documentObject)documentObject.cookie=`${discoveryCookie}=${encodeURIComponent(JSON.stringify([...claims.filter(value=>value!==key),key].slice(-maxDiscoveryClaims)))}; Path=/; SameSite=Strict`;}catch{}
}
export function claimUpdateDiscovery(status,seen=new Set(),storage,documentObject=globalThis.document){
 const notice=updateNotice(status);if(!notice)return false;
 const key=`rieke.update.discovered.${status?.channel||'default'}.${notice.version}`;
 if(seen.has(key))return false;
 if(storage===undefined){try{storage=globalThis.sessionStorage;}catch{}}
 const claims=cookieClaims(documentObject);
 try{if(storage?.getItem(key)){seen.add(key);rememberDiscoveryCookie(documentObject,claims,key);return false;}}catch{}
 if(claims.includes(key)){seen.add(key);try{storage?.setItem(key,'1');}catch{}return false;}
 seen.add(key);try{storage?.setItem(key,'1');}catch{}
 rememberDiscoveryCookie(documentObject,claims,key);
 return true;
}
