'use strict';
const {app, BrowserWindow, ipcMain, dialog, session, shell, Menu, powerMonitor} = require('electron');
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
const {StartupSession,viewNamespace}=require('./startup/startup-session.cjs');
let startupSession,startupOpening,startupError;const scopedDraftStores=new Map();
function scopedDraftStore(window,projectId){
  const origin=new URL(window.webContents.getURL()).origin;
  if(projectId==='launcher'&&origin===supervisor.origin)return {store:draftStore};
  const record=supervisor.registry?.services?.find(record=>record.bound&&record.project_uuid===projectId&&`http://127.0.0.1:${record.port}`===origin);
  if(!record)throw Error('Saved view does not belong to this project window');
  const key=viewNamespace(projectId,record.project_path,app.getVersion()+':view-v1');
  if(!scopedDraftStores.has(key))scopedDraftStores.set(key,new DraftStore(path.join(app.getPath('userData'),'scoped-views',key)));
  return {store:scopedDraftStores.get(key),record};
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
let draftStore, viewUnavailable = false;
let lifecycleStatus = {state: 'Starting', title: 'Starting Disco', message: 'Opening your workspace.'};
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
  for (const window of windows) if (!window.isDestroyed()) window.webContents.send('desktop:status-changed', value);
}
function status() { return previewStatus(lifecycleStatus.state === 'Running' ? (coordinator?.getStatus() || {state: 'Current', installed_version: app.getVersion()}) : lifecycleStatus); }
function recovery(message, detail = '') {
  lifecycleStatus = {state: 'Recovery', channel:distribution.channel, title: 'Disco recovery', message, detail}; broadcast(lifecycleStatus);
  if (scientificWindows.size) viewUnavailable = true;
  // The recovery page has no scientific draft listener. Keep the last good
  // persisted draft; never request a snapshot from the page that replaced it.
  for (const window of windows) {
    scientificWindows.delete(window);
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
      prepareDrafts: timeout => verificationRecovery ? verificationRecovery.then(result=>result.drafts) : viewUnavailable
        ? Promise.resolve({ready:false,reason:'The scientific page is unavailable. The last saved view is retained; its latest changes could not be confirmed.'})
        : draftBarrier.prepare(scientificWindows, {timeout}),
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

function createWindow() {
  const window = new BrowserWindow({width: 1440, height: 960, minWidth: 960, minHeight: 650,
    icon:iconPath(appIcon), title: preview?.label || 'Disco', backgroundColor: '#f4f5f3', show: false,
    webPreferences: {preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true,
      sandbox: true, nodeIntegration: false, nodeIntegrationInWorker: false,
      webSecurity: true, allowRunningInsecureContent: false, webviewTag: false, spellcheck: false,
      partition: 'rieke-desktop'}});
  windows.add(window);
  if (preview) window.webContents.on('page-title-updated', event => { event.preventDefault(); window.setTitle(preview.label); });
  window.once('ready-to-show', () => window.show());
  window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.on('will-navigate', (event, url) => {
    if (isOwnedURL(url, null, [recoveryPage])) return;
    event.preventDefault();
    if (supervisor?.ready) supervisor.authorizeProjectURL(url).then(allowed => {
      if (allowed && !window.isDestroyed()) window.loadURL(url);
    }).catch(() => recovery('A project service failed ownership verification.'));
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
  window.webContents.on('render-process-gone', () => { window.draftUnavailable = scientificWindows.has(window); recovery('The scientific window stopped. The last saved view is retained. Quit remains available; retry startup to recover the project.'); });
  window.on('close', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
  window.on('closed', () => { windows.delete(window); scientificWindows.delete(window); });
  window.loadFile(recoveryPage); return window;
}
function configureSession() {
  const ownedSession = session.fromPartition('rieke-desktop');
  ownedSession.setPermissionRequestHandler((contents, permission, callback, details) =>
    callback(!integrityFailed && allowClipboardWrite(contents, permission, details, scientificWindows, supervisor?.origins)));
  ownedSession.setPermissionCheckHandler((contents, permission, requestingOrigin, details) =>
    !integrityFailed && allowClipboardWrite(contents, permission, details, scientificWindows, supervisor?.origins, requestingOrigin));
  ownedSession.webRequest.onBeforeRequest((details, callback) => {
    const owned = [...windows].some(win => !win.isDestroyed() && win.webContents.id === details.webContentsId);
    const localAsset = details.url.startsWith('file:') && (() => {
      try { return require('node:url').fileURLToPath(details.url).startsWith(__dirname + path.sep); } catch { return false; }
    })();
    callback({cancel: (integrityFailed && !localAsset) || !owned || (!localAsset && !isOwnedURL(details.url, supervisor?.origins))});
  });
  ownedSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const headers = {...details.requestHeaders};
    for (const key of Object.keys(headers)) if (['x-rieke-desktop-capability', 'x-rieke-desktop-session'].includes(key.toLowerCase())) delete headers[key];
    if (supervisor && isOwnedURL(details.url, supervisor.origins) && [...windows].some(win => !win.isDestroyed() && win.webContents.id === details.webContentsId))
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
    if (![...windows].some(win => win.webContents === contents) || !isOwnedURL(item.getURL(), supervisor?.origins)) { event.preventDefault(); return; }
    const filename = path.basename(item.getFilename()).replace(/[\x00-\x1f]/g, '_');
    item.setSaveDialogOptions({title: 'Save export', defaultPath: filename});
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
    await window.loadURL(origin);return {restored:true};
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
    } else origin = await supervisor.start();
    if (integrityFailed || quitting) return;
    if (!coordinator && !preview) {
      const createUpdateCoordinator = distribution.channel === 'unsigned-testing'
        ? require('./updates/testing-updater.cjs').createTestingUpdateCoordinator
        : require('./updates/updater.cjs').createUpdateCoordinator;
      coordinator = createUpdateCoordinator({app, publishStatus: broadcast, prepareQuit,
        authorizeQuit: () => { quitAuthorized = true; }, revokeQuit: () => { quitAuthorized = false; },
        onInstallationFailure: () => { scientificWindows.clear(); recovery('Native update installation failed. Restart the installed backend or restore the verified previous app.'); },
        manifest: supervisor.manifest, distribution});
      coordinator.start().catch(() => broadcast({state:'Deferred',channel:distribution.channel,message:'Update check unavailable. The installed app remains usable.'}));
    }
    // Resolve the remembered project before the first application document.
    // The existing authenticated open/authorization/cleanup path retains ownership.
    // No intermediate chooser renderer, draft read, React mount or IPC round trip.
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
      if(!restored)await window.loadURL(origin);
      window.draftUnavailable = false; scientificWindows.add(window);
    }
    lifecycleStatus = {state: 'Running'};
    viewUnavailable = false;
    broadcast(supervisor.recoveredQuit?.drafts_saved === false
      ? {...status(),message:'The previous quit could not confirm the latest view. The last saved view is retained; accepted operations were reconciled before reopening.'}
      : status());
  } catch (error) { recovery('The packaged scientific backend could not start. Projects have not been opened.', error.message); }
  finally { startupInProgress = false; }
}
function registerIPC() {
  const handle = (channel, action) => ipcMain.handle(channel, async (event, payload) => {
    const window = validateSender(event, windows, supervisor?.origins, [recoveryPage]);
    if ((quitting || integrityFailed) && !['desktop:quit', 'desktop:status', 'desktop:drafts-ack', 'desktop:save-draft'].includes(channel))
      throw new Error('Disco is closing; new work is paused.');
    return action(payload, window);
  });
  const noPayload = (channel, action) => handle(channel, (payload, window) => {
    if (payload !== undefined) throw new TypeError('This desktop operation accepts no payload');
    return action(window);
  });
  handle('desktop:app-icon', variant=>{const result=applyAppIcon(app,windows,variant);appIcon=variant;return result;});
  noPayload('desktop:undo-text', window=>window.webContents.undo());

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
    const {store,record}=scopedDraftStore(window,payload?.projectId);
    const result=await store.save(payload);
    if(record)await startupSession.remember(record.project_uuid,record.project_path,payload.value?.value?.route?.page);
    return result;
  });
  handle('desktop:load-draft', async (projectId,window) => {
    return scopedDraftStore(window,projectId).store.load(projectId);
  });
  handle('desktop:reset-draft', (projectId,window) => scopedDraftStore(window,projectId).store.reset(projectId));
  noPayload('desktop:choose-project-folder', async window => {
    const result = await dialog.showOpenDialog(window, {properties: ['openDirectory', 'createDirectory'], title: 'Choose project folder'});
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
    app.setAboutPanelOptions({applicationName:preview ? 'DISCO Preview' : 'Disco',applicationVersion:app.getVersion(),copyright:preview ? `Source ${preview.source_commit}` : 'Data Inspection, Selection, Comparison Operations · A Rieke Lab OS'});
    supervisor = new ServiceSupervisor({resourcesPath: app.isPackaged ? process.resourcesPath : path.join(__dirname, 'build'),
      userData: app.getPath('userData'), appVersion: app.getVersion(), onFailure: recovery});
    // Backend ownership/readiness can progress while the native window and its
    // presentation preferences initialize. Store rejection until UI can show it.
    if(!bootstrap)backendStartup=supervisor.start().then(origin=>({origin}),error=>({error}));
    appIcon=await savedAppIcon();applyAppIcon(app,windows,appIcon);
    draftStore = new DraftStore(app.getPath('userData'));
    startupSession=new StartupSession(app.getPath('userData'),app.getVersion()+':view-v1');
    await startupSession.load();
    if(startupSession.value?.mode==='resume')lifecycleStatus={state:'Starting',title:'Restoring your workspace',message:'Reopening your saved '+startupSession.value.view+' view. Checking the project before loading scientific data.'};
    configureSession(); registerIPC(); createWindow();
    powerMonitor.on('shutdown', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
    Menu.setApplicationMenu(Menu.buildFromTemplate([{label: 'Disco', submenu: [{role: 'about'}, {type: 'separator'},
      {label: 'Check for Updates', enabled:!preview, click: () => coordinator?.check()},
      {id:'verify-application',label:'Verify Application Files…', enabled:app.isPackaged&&!bootstrap, click:()=>void verifyApplicationFiles()},
      {label:'Cancel Application Verification',click:()=>void cancelApplicationVerification()},
      {type: 'separator'}, {label: 'Quit Disco', accelerator: 'CommandOrControl+Q', click: () => orderlyQuit()}]},
    {label: 'Edit', submenu: [{label: 'Undo', accelerator: 'CommandOrControl+Z', click: (_item, window) => window?.webContents.send('desktop:undo')}, {role: 'redo'}, {type: 'separator'}, {role: 'cut'}, {role: 'copy'}, {role: 'paste'}, {role: 'selectAll'}]},

    {label: 'Window', submenu: [{label:'Resume Last Workspace at Startup',type:'checkbox',checked:startupSession.value?.mode!=='chooser',click:item=>{(item.checked?startupSession.resume():startupSession.choose()).catch(()=>broadcast({...status(),message:'Startup preference could not be saved.'}));}},{role: 'minimize'}, {role: 'zoom'}]}]));
    if (bootstrap) { lifecycleStatus = {state: 'Bootstrap', channel:distribution.channel, title: 'Install Disco', message: 'Install this complete app in your Applications folder and open it.', detail: distribution.channel === 'unsigned-testing' ? 'Unsigned testing release. Install a copy downloaded from the official Disco GitHub release. macOS may require a one-time Open Anyway approval in Privacy & Security. Existing projects stay in their selected folders.' : 'The downloaded app and installed copy must pass Developer ID signature verification. Existing projects stay in their selected folders.'}; broadcast(lifecycleStatus); }
    else await startScientificUI();
  }).catch(error => { console.error('Desktop startup failed:', error.name); app.exit(1); });
}
