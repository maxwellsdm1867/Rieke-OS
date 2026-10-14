'use strict';
// Test harness only: normalize shared CI API rate limits without replacing any
// request, TLS validation, response, updater behavior, or packaged resource.
function takeReleaseFeedToken(environment) {
  const token=environment.GH_TOKEN;
  delete environment.GH_TOKEN;
  return token||null;
}
// Self-contained because Playwright serializes this into Electron's main process.
function installReleaseFeedAuth(_electron,{token}) {
  const https=_electron.https||process.getBuiltinModule('https');
  const key=Symbol.for('disco.smoke.release-feed-auth');
  if(https[key])throw new Error('Release-feed authentication already installed');
  if(typeof token!=='string'||!token||/[\r\n]/.test(token))throw new Error('Invalid CI release-feed credential');
  const endpoint='https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1';
  const original=https.get;let requests=0;
  https.get=function(url,options,callback){
    // Exact match: neither another API nor a redirect/asset host inherits auth.
    if(url!==endpoint)return Reflect.apply(original,this,arguments);
    requests++;
    if(typeof options==='function'){callback=options;options={};}
    return original.call(this,url,{...options,headers:{...options?.headers,Authorization:'Bearer '+token}},callback);
  };
  https[key]=()=>{https.get=original;delete https[key];token=null;return {authenticated_requests:requests,scope:endpoint};};
  return {scope:endpoint};
}
function restoreReleaseFeedAuth(_electron) {
  const https=_electron.https||process.getBuiltinModule('https');
  return https[Symbol.for('disco.smoke.release-feed-auth')]?.()||null;
}
module.exports={takeReleaseFeedToken,installReleaseFeedAuth,restoreReleaseFeedAuth};
