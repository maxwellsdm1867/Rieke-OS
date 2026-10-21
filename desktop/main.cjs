'use strict';
const {app, BrowserWindow, WebContentsView, ipcMain, dialog, session, shell, Menu, powerMonitor} = require('electron');
let preview;
try { preview = require('./local-preview.cjs').localPreview({app}); }
catch (error) { dialog.showErrorBox('Open DISCO Preview', error.message); app.exit(1); throw error; }
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {ServiceSupervisor, matchesHealth} = require('./supervisor.cjs');
const {validateSender, approvedReleaseURL, isOwnedURL, allowClipboardWrite} = require('./security.cjs');
const {enclosingApp, installCompleteBundle} = require('./bootstrap.cjs');
const {DraftBarrier} = require('./close/draft-barrier.cjs');
const {DraftStore} = require('./drafts/draft-store.cjs');
const {StartupSession,viewNamespace,VIEW_COMPATIBILITY,compatibleViews}=require('./startup/startup-session.cjs');
let startupSession,startupOpening,startupError;const scopedDraftStores=new Map();
async function scopedDraftStore(window,projectId){
  const origin=new URL(window.webContents.getURL()).origin;
  if(projectId==='launcher'&&origin===supervisor.origin)return {store:draftStore};
  const record=supervisor.registry?.services?.find(record=>record.bound&&record.project_uuid===projectId&&`http://127.0.0.1:${record.port}`===origin);
  if(!record)throw Error('Saved view does not belong to this project window');
  const key=viewNamespace(projectId,record.project_path,VIEW_COMPATIBILITY);
  if(!scopedDraftStores.has(key))scopedDraftStores.set(key,(async()=>{
    const views=path.join(app.getPath('userData'),'scoped-views');
    let selected=path.join(views,key);
    for(const compatibility of compatibleViews(VIEW_COMPATIBILITY)){
      const directory=path.join(views,viewNamespace(projectId,record.project_path,compatibility));
      try{
        await require('node:fs/promises').lstat(path.join(directory,'drafts',`${projectId}.json`));
        selected=directory;break;
      }catch(error){if(error.code!=='ENOENT'){selected=directory;break;}}
    }
    // Reuse the exact legacy scope, retaining unreadable-state recovery and
    // original bytes. Never fall through an existing but corrupt saved view.
    return new DraftStore(selected);
  })());
  return {store:await scopedDraftStores.get(key),record};
}
const {iconPath,applyAppIcon,savedAppIcon}=require('./app-icon.cjs');
let appIcon='disco';
const {QuitCoordinator} = require('./close/quit-coordinator.cjs');

const {distributionPolicy} = require('./distribution.cjs');
const distribution = distributionPolicy(require('./distribution.json'));
app.enableSandbox();
require('./branding.cjs').configureBranding(app);
const windows = new Set();
const scientificWindows = new Set();
const projectViews = new Map();
const rendererOwners = () => new Set([...windows,...scientificWindows]);
const {ProjectViews,bindingKey}=require('./project-views.cjs');
const recoveryPage = path.join(__dirname, 'recovery.html');
const sourceApp = enclosingApp(process.execPath);
const destination = path.join(os.homedir(), 'Applications', 'Disco.app');
const bootstrap = app.isPackaged && process.platform === 'darwin' && sourceApp !== destination;
const installedUserData = app.getPath('userData');
if (bootstrap) {
  // A downloaded installer must be able to explain why a running installed app
  // blocks replacement instead of silently forwarding its launch to that app.
  const installerState = path.join(app.getPath('userData'), 'installer');
  require('node:fs').mkdirSync(installerState, {recursive:true,mode:0o700});
  app.setPath('userData', installerState);
}
let supervisor, backendStartup, coordinator, quitAuthorized = false, startupInProgress = false, quitting;
let draftStore, viewUnavailable = false, retiredDraftsUnconfirmed = false, navigationGeneration = 0;
let lifecycleStatus = {state: 'Starting', title: 'Starting DISCO', message: 'Opening your workspace.'};
let applicationVerification, verificationController, verificationRecovery, verificationRecoveryResult;
let integrityFailed=false;
async function verifyApplicationFiles() {
  if (applicationVerification || integrityFailed || quitting || bootstrap) return;
  verificationController=new AbortController();
  const signal=verificationController.signal;
  const menuItem=Menu.getApplicationMenu()?.getMenuItemById('verify-application');
  if(menuItem)menuItem.enabled=false;
  applicationVerification=(async()=>{
    let checked=0,last=0;
    try {
      broadcast({...status(),message:'Verifying application files… Use Cancel Application Verification or Quit to stop.'});
      await require('./integrity/verify-application.cjs').verifyApplication({bundle:sourceApp,signed:distribution.channel==='signed',signal,
        progress:()=>{checked++;if(Date.now()-last>250){last=Date.now();broadcast({...status(),message:`Verifying application files… ${checked} entries checked.`});}}});
      if(signal.aborted||quitting)return;
      void dialog.showMessageBox({type:'info',title:'Application verification complete',message:'Application files match the installed inventory and app seal.',
        detail:distribution.channel==='signed'?'Developer ID signature verification also passed. This does not verify project data.':'This unsigned testing build does not establish publisher identity. This does not verify project data.'}).catch(()=>{});
    } catch(error) {
      if(signal.aborted||quitting)return;
      verificationRecovery=require('./integrity/verification-recovery.cjs').recoverVerificationFailure({
        blockNewWork:()=>{integrityFailed=true;coordinator?.stop();if(startupSession)startupSession.cancelled=true;broadcast({state:'IntegrityRecovery',title:'Application verification failed',message:'New work is blocked. Finishing accepted operations and saving the last available view.'});},
        pause:async()=>{if(supervisor?.bound)await supervisor.api('/api/desktop/pause-all',{method:'POST',timeout:5000});},
        saveDrafts:()=>draftBarrier.prepare(scientificWindows,{timeout:5000}),
        closeServices:drafts=>supervisor?supervisor.quit({drafts,startup:startupOpening}):{ready:true},
        showRecovery:result=>{verificationRecoveryResult=result;
          recovery(result.services.ready?'Application verification failed. Owned services have closed.':'Application verification failed. Service closure is unconfirmed; recovery is required.',require('./integrity/verify-application.cjs').repairGuidance(sourceApp));
          lifecycleStatus={...lifecycleStatus,state:'IntegrityRecovery'};broadcast(lifecycleStatus);}
      });
      await verificationRecovery;
    } finally {
      if(menuItem)menuItem.enabled=!integrityFailed&&!quitting;
    }
  })().finally(()=>{applicationVerification=null;verificationController=null;});
  return applicationVerification;
}
async function cancelApplicationVerification() {
  verificationController?.abort();
  await applicationVerification;
  if(!quitting&&!integrityFailed)broadcast({...status(),message:'Application verification cancelled. No application files were changed.'});
}

const draftBarrier = new DraftBarrier();
function previewStatus(value) {
  return preview ? {...value, local_preview:true, channel:'unsigned-testing', installed:preview.application_version,
    source_commit:preview.source_commit, can_download:false, can_restart:false,
    message:value.message || `${preview.label}. Updates, installation and restore are disabled.`} : value;
}
function broadcast(value) {
  value = previewStatus(value);
  for (const window of rendererOwners()) if (!window.isDestroyed()) window.webContents.send('desktop:status-changed', value);
}
function status() { return previewStatus(lifecycleStatus.state === 'Running' ? (coordinator?.getStatus() || {state: 'Current', installed_version: app.getVersion()}) : lifecycleStatus); }
function publishUpdateStatus(value){if(lifecycleStatus.state==='Running')broadcast(value);}
function recovery(message, detail = '') {
  lifecycleStatus = {state: 'Recovery', channel:distribution.channel, title: 'DISCO recovery', message, detail}; broadcast(lifecycleStatus);
  // Recovery hides documents but cannot discard a healthy unsaved draft.
  // IPC still permits persistence; all new scientific/user actions are fenced.
  navigationGeneration++;
  for(const views of projectViews.values())views.cancelActivations();
  // The recovery page has no scientific draft listener. Keep the last good
  // persisted draft; never request a snapshot from the page that replaced it.
  for (const window of windows) {
    if(scientificWindows.has(window)){window.draftUnavailable=true;viewUnavailable=true;}
    if (!window.isDestroyed()) window.loadFile(recoveryPage).catch(() => {});
  }

}
async function acknowledgeDrafts() {
  return draftBarrier.prepare(scientificWindows);
}
async function prepareQuit() {
  const drafts = await acknowledgeDrafts();
  if (!drafts.ready) { broadcast({...status(), message:drafts.reason}); return drafts; }
  const result = supervisor ? await supervisor.drain() : {ready: true};
  if (!result.ready) broadcast({...status(), message:result.reason});
  return result;
}
function orderlyQuit() {
  verificationController?.abort();
  if (!quitting) {
    coordinator?.stop();
    if(startupSession)startupSession.cancelled=true;
    quitting = new QuitCoordinator({
      prepareDrafts: async timeout => {
        const result=await draftBarrier.prepare(scientificWindows,{timeout});
        return viewUnavailable?{ready:false,reason:[result.reason,'The scientific page is unavailable. The last saved view of the stopped page remains unconfirmed.'].filter(Boolean).join(' ')}:result;
      },
      cleanup: async options => {
        await cancelApplicationVerification();
        return require('./integrity/verification-recovery.cjs').cleanupAfterVerificationRecovery(verificationRecoveryResult,
          () => supervisor ? supervisor.quit({...options,startup:startupOpening}) : {ready:true});
      },
      publish: value => { lifecycleStatus = value; broadcast(value); },
      exit: () => { quitAuthorized = true; app.quit(); }
    });
  }
  return quitting.quit();
}

// Draft persistence outlives the backend: a crash clears supervisor.origins, but a
// retained document still at the exact origin authenticated when it registered may
// persist its view and acknowledge drafts. No other channel gains this origin.
const DRAFT_CHANNELS=['desktop:drafts-ack','desktop:save-draft'];
function draftOrigins(event){
  const origins=new Set(supervisor?.origins||[]);
  const owner=[...scientificWindows].find(item=>item.binding&&!item.isDestroyed()&&item.webContents===event?.sender);
  if(owner)origins.add(owner.binding.origin);
  return origins;
}
// One project = one draft writer. The writer for a project's saved-view scope is
// the most recently registered owner for that project. A newer owner is admitted
// to write only after the previous owner's final checkpoint completes or is
// declared unconfirmed; afterwards the previous owner's saves are refused and it
// is disposed. No two documents can ever interleave writes to one saved view.
const draftWriters=new Map();
const draftScope=binding=>binding.project_uuid==='launcher'?'launcher':JSON.stringify([binding.project_uuid,binding.project_path]);
function claimDraftWriter(owner){
  if(!owner.binding)return;
  const scope=draftScope(owner.binding),previous=draftWriters.get(scope);
  const entry={owner,previous:previous?.owner,settled:false};
  entry.ready=(async()=>{
    if(!entry.previous)return;
    await previous.ready;
    if(entry.previous.isDestroyed()||entry.previous.draftUnavailable)return;
    entry.checkpointing=true;
    try{const result=await draftBarrier.prepare([entry.previous],{purpose:'project-checkpoint',timeout:5000});if(!result.ready)retiredDraftsUnconfirmed=true;}
    catch{retiredDraftsUnconfirmed=true;}
    finally{entry.checkpointing=false;}
  })().finally(()=>{
    entry.settled=true;
    const stale=entry.previous;
    if(stale&&!stale.isDestroyed()&&stale.retired===undefined)projectViews.get(stale.parentWindow)?.dispose(stale);
  });
  draftWriters.set(scope,entry);
}
function releaseDraftWriter(owner){
  if(!owner.binding)return;
  const scope=draftScope(owner.binding);
  if(draftWriters.get(scope)?.owner===owner)draftWriters.delete(scope);
}
// Resolves when this owner may write; rejects for a superseded owner.
async function admitDraftWriter(owner){
  if(!owner.binding)return;
  const entry=draftWriters.get(draftScope(owner.binding));
  if(entry?.owner===owner){await entry.ready;if(draftWriters.get(draftScope(owner.binding))===entry)return;}
  else if(entry?.checkpointing&&entry.previous===owner)return; // Only the superseded owner's final checkpoint.
  throw Error('Another document now owns this project\'s saved view.');
}
function retainedOwners(){return [...projectViews.values()].flatMap(views=>[...views.owners.values()].map(owner=>({views,owner})));}
// After a failed backend, checkpoint retained documents while their old bindings
// still authenticate; a replacement root invalidates every one of those bindings.
async function checkpointRetainedOwners(){
  const owners=retainedOwners().map(item=>item.owner);
  if(!owners.length)return;
  const result=await draftBarrier.prepare(owners,{purpose:'project-checkpoint',timeout:5000});
  if(!result.ready)retiredDraftsUnconfirmed=true;
}
// Dispose owners whose backend is gone only after a successful replacement start.
function disposeStaleOwners(){
  for(const {views,owner} of retainedOwners())if(!ownerCurrent(owner))views.dispose(owner);
}
function ownerCurrent(owner){
  if(!owner.binding)return true;
  if(owner.binding.project_uuid==='launcher')return owner.binding.origin===supervisor?.origin;
  return supervisor?.registry?.services?.some(record=>record.bound&&['project_uuid','project_path','session_id','pid','created_at'].every(key=>record[key]===owner.binding[key])&&`http://127.0.0.1:${record.port}`===owner.binding.origin)===true;
}
function secureContents(window) {
  if (preview) window.webContents.on('page-title-updated', event => { event.preventDefault(); (window.parentWindow||window).setTitle(preview.label); });
  else if(window.parentWindow)window.webContents.on('page-title-updated',(_event,title)=>{if(window.active)window.parentWindow.setTitle(title);});
  window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.on('will-navigate', (event, url) => {
    if (isOwnedURL(url, null, [recoveryPage])) return;
    event.preventDefault();
    if (supervisor?.ready) activateProject(window.parentWindow||window,url).catch(error => broadcast({...status(),message:`The project could not open: ${error.message}`}));
  });
  window.webContents.on('will-redirect', (event, url) => {
    if (!isOwnedURL(url, supervisor?.origins, [recoveryPage])) event.preventDefault();
  });
  // Owned benchmark telemetry only. Observe native first paint before any CDP
  // client attaches; never use this marker as readiness or mutation authority.
  if(process.env.DISCO_STARTUP_DIAGNOSTIC==='1')window.webContents.on('did-finish-load',()=>{
    if(!isOwnedURL(window.webContents.getURL(),supervisor?.origins))return;
    void window.webContents.executeJavaScript(`new Promise(resolve=>{
      const until=performance.now()+15000;
      function frame(){
        const current=document.querySelector('.project-rail-item[aria-current="page"]');
        const launcher=document.querySelector('.project-launcher');
        const node=current||launcher;
        if(node&&node.getBoundingClientRect().width>0&&!node.disabled){
          requestAnimationFrame(()=>resolve({kind:current?'project':'launcher',wall_ms:performance.timeOrigin+performance.now()}));
        }else if(performance.now()<until)requestAnimationFrame(frame);else resolve(null);
      }
      requestAnimationFrame(frame);
    })`).then(value=>{
      if(value)process.stdout.write('DISCO_SHELL_PAINTED='+JSON.stringify({pid:process.pid,...value})+'\n');
    }).catch(()=>{});
  });
  window.webContents.on('render-process-gone', () => {
    if(window.parentWindow){
      if(!scientificWindows.has(window))return;
      window.draftUnavailable=true;viewUnavailable=true;
      const views=projectViews.get(window.parentWindow),wasActive=views?.active===window;
      views?.suspend(window);
      const notice=()=>broadcast({...status(),message:'A project renderer stopped. Other projects are retained. Quit and reopen DISCO to recover its last saved view.'});
      if(wasActive)activateProject(window.parentWindow,supervisor.origin).then(notice,error=>recovery('The project renderer stopped. Healthy views are retained.',error.message));
      else notice();
      return;
    }
    recovery('The window stopped. Healthy project views are retained. Quit remains available.');
  });
}
function viewsFor(window){
  if(!projectViews.has(window))projectViews.set(window,new ProjectViews({window,
    createView:()=>new WebContentsView({webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,sandbox:true,nodeIntegration:false,nodeIntegrationInWorker:false,webSecurity:true,allowRunningInsecureContent:false,webviewTag:false,spellcheck:false,partition:'rieke-desktop'}}),
    prepare:owners=>draftBarrier.prepare(owners,{purpose:'project-checkpoint'}),
    onRegister:owner=>{scientificWindows.add(owner);secureContents(owner);claimDraftWriter(owner);},
    onDispose:owner=>{scientificWindows.delete(owner);releaseDraftWriter(owner);},
    onActivate:async owner=>{
      if(owner.binding.project_uuid!=='launcher')try{await startupSession.remember(owner.binding.project_uuid,owner.binding.project_path,'workspace');}catch{broadcast({...status(),message:'The project opened, but its startup preference could not be saved.'});}
      if(!preview){const title=owner.webContents.getTitle();if(title)window.setTitle(title);}
    },
    admit:()=>supervisor?.ready&&!quitting&&!integrityFailed&&lifecycleStatus.state!=='Recovery'&&!window.isDestroyed(),limit:3,
  }));
  return projectViews.get(window);
}
async function activateProject(window,url){
  const generation=navigationGeneration;
  if(quitting||integrityFailed||lifecycleStatus.state==='Recovery')throw Error('DISCO is closing; new work is paused.');
  if(typeof url!=='string'||!await supervisor.authorizeProjectURL(url))throw Error('Project service failed ownership verification.');
  if(generation!==navigationGeneration||quitting||integrityFailed||lifecycleStatus.state==='Recovery')throw Error('Project activation was cancelled.');
  // Legacy host adapters retain their existing navigation contract.
  if(!WebContentsView){await window.loadURL(url);return {activated:true};}
  const origin=new URL(url).origin;
  const record=origin===supervisor.origin?{project_uuid:'launcher',project_path:'',session_id:supervisor.sessionId,pid:supervisor.child?.pid,created_at:null}:supervisor.registry.services.find(item=>`http://127.0.0.1:${item.port}`===origin);
  if(!record)throw Error('Project binding is unavailable.');
  return viewsFor(window).activate({...record,origin},url);
}
async function activateRetainedProject(caller,value){
  const identity=projectIdentity(value),window=caller.parentWindow||caller,views=projectViews.get(window);
  const generation=navigationGeneration,callerUse=caller.used,callerFrame=caller.webContents.mainFrame;
  const assertCaller=()=>{
    if(generation!==navigationGeneration||quitting||integrityFailed||lifecycleStatus.state==='Recovery'||!supervisor?.ready)throw Error('Project activation was cancelled.');
    if(!views||projectViews.get(window)!==views||views.active!==caller||caller.active!==true||caller.used!==callerUse||caller.closing||caller.draftUnavailable||caller.isDestroyed())throw Error('The requesting project is no longer active.');
    if(caller.webContents.mainFrame!==callerFrame||!scientificWindows.has(caller)||!ownerCurrent(caller))throw Error('The requesting project binding changed.');
    validateSender({sender:caller.webContents,senderFrame:callerFrame},rendererOwners(),supervisor.origins,[recoveryPage]);
  };
  if(!WebContentsView){
    if(generation!==navigationGeneration||quitting||integrityFailed||lifecycleStatus.state==='Recovery'||!supervisor?.ready)throw Error('Project activation was cancelled.');
    if(caller.parentWindow||!windows.has(caller)||!scientificWindows.has(caller)||caller.isDestroyed()||caller.draftUnavailable||caller.active===false||!ownerCurrent(caller))throw Error('The requesting project is no longer active.');
    validateSender({sender:caller.webContents,senderFrame:callerFrame},rendererOwners(),supervisor.origins,[recoveryPage]);
    return {activated:false};
  }
  assertCaller();
  const matches=views.find(identity);
  if(!matches.length)return {activated:false};
  if(matches.length!==1)throw Error('The retained project binding is ambiguous.');
  const target=matches[0],expected=bindingKey(target.binding),origin=target.binding.origin;
  return views.activateRetained(target,async()=>{
    assertCaller();
    if(bindingKey(target.binding)!==expected||!ownerCurrent(target))throw Error('The retained project backend binding changed.');
    // Authorization may discover a different child on a reused port. Never
    // resolve that URL into a new view; prove this exact retained owner again.
    if(!await supervisor.authorizeProjectURL(origin))throw Error('Project service failed ownership verification.');
    assertCaller();
    if(bindingKey(target.binding)!==expected||!ownerCurrent(target))throw Error('The retained project backend binding changed.');
  });
}
function projectIdentity(value){
  if(!value||Object.keys(value).sort().join(',')!=='path,projectUuid'||typeof value.path!=='string'||!path.isAbsolute(value.path)||path.normalize(value.path)!==value.path||typeof value.projectUuid!=='string')throw TypeError('Invalid project identity');
  require('./security.cjs').validateProjectId(value.projectUuid);return value;
}
function createWindow() {
  const window = new BrowserWindow({width: 1440, height: 960, minWidth: 960, minHeight: 650,
    icon:iconPath(appIcon), title: preview?.label || 'DISCO', backgroundColor: '#f4f5f3', show: false,
    webPreferences: {preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true,
      sandbox: true, nodeIntegration: false, nodeIntegrationInWorker: false,
      webSecurity: true, allowRunningInsecureContent: false, webviewTag: false, spellcheck: false,
      partition: 'rieke-desktop'}});
  windows.add(window);
  secureContents(window);
  window.once('ready-to-show', () => window.show());
  window.on('resize',()=>projectViews.get(window)?.resize());
  window.on('close', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
  window.on('closed', () => { projectViews.get(window)?.clear();projectViews.delete(window);windows.delete(window);scientificWindows.delete(window); });
  window.loadFile(recoveryPage); return window;
}
function configureSession() {
  const ownedSession = session.fromPartition('rieke-desktop');
  ownedSession.setPermissionRequestHandler((contents, permission, callback, details) =>
    callback(!integrityFailed && allowClipboardWrite(contents, permission, details, scientificWindows, supervisor?.origins)));
  ownedSession.setPermissionCheckHandler((contents, permission, requestingOrigin, details) =>
    !integrityFailed && allowClipboardWrite(contents, permission, details, scientificWindows, supervisor?.origins, requestingOrigin));
  ownedSession.webRequest.onBeforeRequest((details, callback) => {
    const owned = [...rendererOwners()].some(win => !win.isDestroyed() && ownerCurrent(win) && win.webContents.id === details.webContentsId && (!win.binding || new URL(details.url).origin===win.binding.origin));
    const localAsset = details.url.startsWith('file:') && (() => {
      try { return require('node:url').fileURLToPath(details.url).startsWith(__dirname + path.sep); } catch { return false; }
    })();
    callback({cancel: (integrityFailed && !localAsset) || (lifecycleStatus.state==='Recovery'&&!['GET','HEAD','OPTIONS'].includes(details.method||'GET')&&!localAsset) || !owned || (!localAsset && !isOwnedURL(details.url, supervisor?.origins))});
  });
  ownedSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const headers = {...details.requestHeaders};
    for (const key of Object.keys(headers)) if (['x-rieke-desktop-capability', 'x-rieke-desktop-session'].includes(key.toLowerCase())) delete headers[key];
    if (supervisor && isOwnedURL(details.url, supervisor.origins) && [...rendererOwners()].some(win => !win.isDestroyed() && ownerCurrent(win) && win.webContents.id === details.webContentsId && (!win.binding || new URL(details.url).origin===win.binding.origin)))
      headers['X-Rieke-Desktop-Session'] = supervisor.rendererCapability;
    callback({requestHeaders: headers});
  });
  ownedSession.webRequest.onHeadersReceived((details, callback) => {
    const headers = {...details.responseHeaders};
    if (isOwnedURL(details.url, supervisor?.origins)) {
      headers['Content-Security-Policy'] = ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"];
      headers['X-Content-Type-Options'] = ['nosniff'];
    }
    callback({responseHeaders: headers});
  });
  ownedSession.on('will-download', (event, item, contents) => {
    if (![...rendererOwners()].some(win => win.webContents === contents && (!win.binding || new URL(item.getURL()).origin===win.binding.origin)) || !isOwnedURL(item.getURL(), supervisor?.origins)) { event.preventDefault(); return; }
    const filename = path.basename(item.getFilename()).replace(/[\x00-\x1f]/g, '_');
    item.setSaveDialogOptions({title: 'Save export', defaultPath: path.join(app.getPath('downloads'), filename)});
  });
}
function restoreStartupWindow(window){
    const expected=startupSession.target;startupSession.target=null;
    if(startupSession.cancelled)return {restored:false};
    startupOpening=(async()=>{
    const opened=await supervisor.api('/api/desktop/resume-project',{method:'POST',body:{directory:expected.projectPath,project_uuid:expected.projectId},timeout:90000});
    const url=opened.url;
    if(!await supervisor.authorizeProjectURL(url))throw Error('Restored project failed ownership verification');
    const origin=new URL(url).origin,record=supervisor.registry.services.find(record=>`http://127.0.0.1:${record.port}`===origin);
    const mismatch=record?.project_uuid!==expected.projectId||record?.project_path!==expected.projectPath;
    if(startupSession.cancelled||mismatch||quitting){
      if(!record)throw Error('Restored project ownership is unavailable; Quit to recover');
      const response=await fetch(origin+'/api/project/close',{method:'POST',headers:{'X-Rieke-Desktop-Capability':supervisor.capability,'X-Workspace-Request':'1','Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(35000)});
      const value=await response.json();if(!response.ok||value.state!=='closed')throw Error('Restoration cancelled but project cleanup requires recovery. Quit before continuing.');
      const deadline=Date.now()+10000;
      while((await supervisor.api('/api/desktop/health')).services.some(item=>item.pid===record.pid&&item.created_at===record.created_at)){
        if(Date.now()>deadline)throw Error('Cancelled project has not exited. Quit to recover.');await new Promise(resolve=>setTimeout(resolve,100));
      }
      supervisor.origins.delete(origin);
      if(mismatch)throw Error('The saved project identity changed. Choose its current folder.');
      return {restored:false,closed:true};
    }
    await activateProject(window,origin);return {restored:true};
    })().finally(()=>{startupOpening=null;});
    return startupOpening;
}
async function startScientificUI() {
  if (startupInProgress || quitting || integrityFailed) return;
  startupInProgress = true;
  try {
    let origin;
    if (backendStartup) {
      const started=await backendStartup;backendStartup=null;
      if(started.error)throw started.error;
      if(supervisor.exited||!supervisor.ready)throw Error('The backend stopped before the workspace window was ready.');
      origin=started.origin;
    } else if (supervisor.child && !supervisor.exited) {
      const health = await supervisor.api('/api/desktop/health');
      if (!matchesHealth(health, supervisor.expectedHealth())) throw new Error('Existing backend is not ready for recovery');
      origin = supervisor.origin; supervisor.ready = true; supervisor.origins.add(origin);
    } else {
      await checkpointRetainedOwners();
      if (integrityFailed || quitting) return;
      origin = await supervisor.start();
    }
    if (integrityFailed || quitting) return;
    disposeStaleOwners();
    if (!coordinator && !preview) {
      const createUpdateCoordinator = distribution.channel === 'unsigned-testing'
        ? require('./updates/testing-updater.cjs').createTestingUpdateCoordinator
        : require('./updates/updater.cjs').createUpdateCoordinator;
      coordinator = createUpdateCoordinator({app, publishStatus: publishUpdateStatus, prepareQuit,
        authorizeQuit: () => { quitAuthorized = true; }, revokeQuit: () => { quitAuthorized = false; },
        onInstallationFailure: () => { recovery('Native update installation failed. Restart the installed backend or restore the verified previous app.'); },
        manifest: supervisor.manifest, distribution});
      coordinator.start().catch(() => publishUpdateStatus({state:'Deferred',channel:distribution.channel,message:'Update check unavailable. The installed app remains usable.'}));
    }
    // Resolve the remembered project before the first application document.
    // The existing authenticated open/authorization/cleanup path retains ownership.
    // No intermediate chooser renderer, draft read, React mount or IPC round trip.
    lifecycleStatus={state:'Starting',title:'Opening DISCO',message:'Restoring your workspace.'};
    const target=startupSession.claim();
    for (const window of windows) {
      let restored=false;
      if(target&&!startupSession.cancelled){
        try{restored=(await restoreStartupWindow(window)).restored;}
        catch(error){
          // A failed ownership check can leave a child requiring recovery. Only
          // a root that confirms no retained child allows the ordinary chooser.
          const health=await supervisor.api('/api/desktop/health');
          if(health.services?.length)throw error;
          startupError=error.message;
        }
      }
      if(quitting||integrityFailed)return;
      if(!restored)await activateProject(window,origin);
      window.draftUnavailable = false;if(!WebContentsView)scientificWindows.add(window);
    }
    lifecycleStatus = {state: 'Running'};
    viewUnavailable = retiredDraftsUnconfirmed || [...scientificWindows].some(owner=>owner.draftUnavailable||owner.isDestroyed());
    broadcast(supervisor.recoveredQuit?.drafts_saved === false
      ? {...status(),message:'The previous quit could not confirm the latest view. The last saved view is retained; accepted operations were reconciled before reopening.'}
      : status());
  } catch (error) { recovery('The packaged scientific backend could not start. Projects have not been opened.', error.message); }
  finally { startupInProgress = false; }
}
function registerIPC() {
  const handle = (channel, action) => ipcMain.handle(channel, async (event, payload) => {
    const window = validateSender(event, rendererOwners(), DRAFT_CHANNELS.includes(channel) ? draftOrigins(event) : supervisor?.origins, [recoveryPage]);
    if(!ownerCurrent(window))throw Error('The project backend binding has changed.');
    if(window.active===false&&['desktop:choose-project-folder','desktop:prepare-project-close','desktop:confirm-project-closed','desktop:cancel-project-close'].includes(channel))throw Error('The project is not visible.');
    const recoveryHost=!window.parentWindow&&isOwnedURL(window.webContents?.getURL(),null,[recoveryPage]);
    if ((quitting || integrityFailed || lifecycleStatus.state==='Recovery') && !['desktop:quit', 'desktop:status', 'desktop:drafts-ack', 'desktop:save-draft', ...(!quitting&&!integrityFailed&&recoveryHost?['desktop:retry-startup','desktop:restore-previous']:[])].includes(channel))
      throw new Error('DISCO is closing; new work is paused.');
    return action(payload, window);
  });
  const noPayload = (channel, action) => handle(channel, (payload, window) => {
    if (payload !== undefined) throw new TypeError('This desktop operation accepts no payload');
    return action(window);
  });
  handle('desktop:app-icon', variant=>{const result=applyAppIcon(app,windows,variant);appIcon=variant;return result;});
  noPayload('desktop:undo-text', window=>{if(window.active===false)throw Error('The project is not visible.');return window.webContents.undo();});
  handle('desktop:activate-retained-project',(identity,owner)=>activateRetainedProject(owner,identity));
  handle('desktop:activate-project',(url,owner)=>{if(owner.active===false)throw Error('The project is not visible.');return activateProject(owner.parentWindow||owner,url);});
  noPayload('desktop:project-visibility',owner=>({visible:owner.active!==false}));
  handle('desktop:prepare-project-close',async(value)=>{
    const identity=projectIdentity(value);
    for(const views of projectViews.values())await views.prepareClose(identity);
    return {ready:true};
  });
  handle('desktop:cancel-project-close',value=>{const identity=projectIdentity(value);for(const views of projectViews.values())views.cancelClose(identity);return {cancelled:true};});
  handle('desktop:confirm-project-closed',async value=>{
    const identity=projectIdentity(value),health=await supervisor.api('/api/desktop/health');
    if(!matchesHealth(health,supervisor.expectedHealth())||!Array.isArray(health.services)||health.services.some(record=>record.project_uuid===identity.projectUuid&&record.project_path===identity.path))throw Error('Project closure is not confirmed.');
    for(const views of projectViews.values())for(const owner of views.find(identity)){
      if(!owner.closing)throw Error('Project view closure was not prepared.');
      if(owner.active)await activateProject(owner.parentWindow,supervisor.origin);
      views.dispose(owner);
    }
    return {closed:true};
  });

  noPayload('desktop:status', () => status());
  noPayload('desktop:startup-session', window => {
    if(new URL(window.webContents.getURL()).origin!==supervisor.origin)return null;
    if(startupError){const error=startupError;startupError=null;throw Error(error);}
    return startupSession.claim();
  });
  noPayload('desktop:choose-startup',()=>startupSession.choose());
  noPayload('desktop:cancel-startup',()=>{startupSession.cancelled=true;});
  noPayload('desktop:open-startup',window=>{
    if(new URL(window.webContents.getURL()).origin!==supervisor.origin||!startupSession.target||startupOpening)throw Error('No startup restoration is active');
    return restoreStartupWindow(window);
  });
  noPayload('desktop:check-updates', () => coordinator ? coordinator.check() : status());
  noPayload('desktop:download-update', () => {
    if (preview) throw new Error('Updates are disabled in DISCO Preview.');
    if (!coordinator?.download) throw new Error('Update download is unavailable for this installation.');
    return coordinator.download();
  });
  noPayload('desktop:restart-to-update', () => {
    if (preview) throw new Error('Updates are disabled in DISCO Preview.');
    if (!coordinator) throw new Error('No prepared update is available.');
    return coordinator.installPrepared();
  });
  noPayload('desktop:quit', () => orderlyQuit());
  noPayload('desktop:retry-startup', () => { if (bootstrap) throw new Error('Install the complete app before starting projects'); return startScientificUI(); });
  handle('desktop:restore-previous', async payload => {
    if (preview) throw new Error('Restore is disabled in DISCO Preview.');
    if (payload !== undefined || lifecycleStatus.state !== 'Recovery') throw new Error('Verified restoration is available only from recovery');
    const restorePriorBundle = distribution.channel === 'unsigned-testing'
      ? require('./testing-install.cjs').restoreTestingPriorBundle
      : require('./update-recovery.cjs').restorePriorBundle;
    const manifest = supervisor.manifest || await supervisor.loadManifest();
    return restorePriorBundle({app, prepareQuit, authorizeQuit: () => { quitAuthorized = true; }, manifest});
  });
  handle('desktop:drafts-ack', (payload, window) => {
    return draftBarrier.acknowledge(payload, window);
  });
  handle('desktop:save-draft', async (payload,window) => {
    await admitDraftWriter(window);
    const {store,record}=await scopedDraftStore(window,payload?.projectId);
    const result=await store.save(payload);
    // The startup preference is a separate convenience; its failure never turns
    // a persisted view into a failed draft save. remember() skips unchanged values.
    if(record&&window.active!==false)try{await startupSession.remember(record.project_uuid,record.project_path,payload.value?.value?.route?.page);}
    catch{broadcast({...status(),message:'The view was saved, but its startup preference could not be saved.'});}
    return result;
  });
  handle('desktop:load-draft', async (projectId,window) => {
    return (await scopedDraftStore(window,projectId)).store.load(projectId);
  });
  handle('desktop:reset-draft', async (projectId,window) => (await scopedDraftStore(window,projectId)).store.reset(projectId));
  noPayload('desktop:choose-project-folder', async window => {
    const result = await dialog.showOpenDialog(window.parentWindow||window, {properties: ['openDirectory', 'createDirectory'], title: 'Choose project folder'});
    return result.canceled ? null : result.filePaths[0];
  });
  handle('desktop:open-release-notes', async url => {
    if (!approvedReleaseURL(url)) throw new TypeError('Only official HTTPS release notes may be opened');
    await shell.openExternal(url); return {opened: true};
  });
  noPayload('desktop:install-and-open', async () => {
    if (preview) throw new Error('Installation is disabled in DISCO Preview.');
    if (!bootstrap || supervisor?.child) throw new Error('Install action is available only before backend startup');
    const result = await installCompleteBundle({source: sourceApp, destination, distribution});
    app.releaseSingleInstanceLock();
    await promisify(execFile)('/usr/bin/open', ['-n', '-a', result.destination,
      '--env', `HOME=${os.homedir()}`, '--args', `--user-data-dir=${installedUserData}`]);
    quitAuthorized = true; app.quit(); return {installed: true};
  });
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { const window = [...windows][0]; if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } });
  app.on('before-quit', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
  app.on('window-all-closed', () => { if (quitAuthorized) app.quit(); });
  app.whenReady().then(async () => {
    app.setAboutPanelOptions({applicationName:preview ? 'DISCO Preview' : 'DISCO',applicationVersion:app.getVersion(),copyright:preview ? `Source ${preview.source_commit}` : 'Data Inspection, Selection, Comparison Operations · A Rieke Lab OS'});
    supervisor = new ServiceSupervisor({resourcesPath: app.isPackaged ? process.resourcesPath : path.join(__dirname, 'build'),
      userData: app.getPath('userData'), appVersion: app.getVersion(), onFailure: recovery});
    // Backend ownership/readiness can progress while the native window and its
    // presentation preferences initialize. Store rejection until UI can show it.
    if(!bootstrap)backendStartup=supervisor.start().then(origin=>({origin}),error=>({error}));
    appIcon=await savedAppIcon();applyAppIcon(app,windows,appIcon);
    draftStore = new DraftStore(app.getPath('userData'));
    startupSession=new StartupSession(app.getPath('userData'),VIEW_COMPATIBILITY);
    await startupSession.load();
    if(startupSession.value?.mode==='resume')lifecycleStatus={state:'Starting',title:'Restoring your workspace',message:'Reopening your saved '+startupSession.value.view+' view. Checking the project before loading scientific data.'};
    configureSession(); registerIPC(); createWindow();
    powerMonitor.on('shutdown', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
    Menu.setApplicationMenu(Menu.buildFromTemplate([{label: 'DISCO', submenu: [{role: 'about'}, {type: 'separator'},
      {label: 'Check for Updates', enabled:!preview, click: () => coordinator?.check()},
      {id:'verify-application',label:'Verify Application Files…', enabled:app.isPackaged&&!bootstrap, click:()=>void verifyApplicationFiles()},
      {label:'Cancel Application Verification',click:()=>void cancelApplicationVerification()},
      {type: 'separator'}, {label: 'Quit DISCO', accelerator: 'CommandOrControl+Q', click: () => orderlyQuit()}]},
    {label: 'Edit', submenu: [{label: 'Undo', accelerator: 'CommandOrControl+Z', click: (_item, window) => (projectViews.get(window)?.active?.webContents||window?.webContents)?.send('desktop:undo')}, {role: 'redo'}, {type: 'separator'}, {role: 'cut'}, {role: 'copy'}, {role: 'paste'}, {role: 'selectAll'}]},

    {label: 'Window', submenu: [{label:'Resume Last Workspace at Startup',type:'checkbox',checked:startupSession.value?.mode!=='chooser',click:item=>{(item.checked?startupSession.resume():startupSession.choose()).catch(()=>broadcast({...status(),message:'Startup preference could not be saved.'}));}},{role: 'minimize'}, {role: 'zoom'}]}]));
    if (bootstrap) { lifecycleStatus = {state: 'Bootstrap', channel:distribution.channel, title: 'Install DISCO', message: 'Install this complete app in your Applications folder and open it.', detail: distribution.channel === 'unsigned-testing' ? 'Unsigned testing release. Install a copy downloaded from the official DISCO GitHub release. macOS may require a one-time Open Anyway approval in Privacy & Security. Existing projects stay in their selected folders.' : 'The downloaded app and installed copy must pass Developer ID signature verification. Existing projects stay in their selected folders.'}; broadcast(lifecycleStatus); }
    else await startScientificUI();
  }).catch(error => { console.error('Desktop startup failed:', error.name); app.exit(1); });
}
