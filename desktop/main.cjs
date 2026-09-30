'use strict';
const {app, BrowserWindow, ipcMain, dialog, session, shell, Menu, powerMonitor} = require('electron');
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {ServiceSupervisor, matchesHealth} = require('./supervisor.cjs');
const {validateSender, approvedReleaseURL, isOwnedURL} = require('./security.cjs');
const {enclosingApp, installCompleteBundle} = require('./bootstrap.cjs');
const {DraftBarrier} = require('./draft-barrier.cjs');
const {DraftStore} = require('./draft-store.cjs');
const {distributionPolicy} = require('./distribution.cjs');
const distribution = distributionPolicy(require('./distribution.json'));
app.enableSandbox();
app.setName('Rieke OS');
const windows = new Set();
const scientificWindows = new Set();
const recoveryPage = path.join(__dirname, 'recovery.html');
const sourceApp = enclosingApp(process.execPath);
const destination = path.join(os.homedir(), 'Applications', 'Rieke OS.app');
const bootstrap = app.isPackaged && process.platform === 'darwin' && sourceApp !== destination;
const installedUserData = app.getPath('userData');
if (bootstrap) {
  // A downloaded installer must be able to explain why a running installed app
  // blocks replacement instead of silently forwarding its launch to that app.
  const installerState = path.join(app.getPath('userData'), 'installer');
  require('node:fs').mkdirSync(installerState, {recursive:true,mode:0o700});
  app.setPath('userData', installerState);
}
let supervisor, coordinator, quitAuthorized = false, quitInProgress = false, startupInProgress = false;
let draftStore;
let lifecycleStatus = {state: 'Starting', title: 'Starting Rieke OS', message: 'Verifying the complete app and its private runtime.'};
const draftBarrier = new DraftBarrier();
function broadcast(value) {
  for (const window of windows) if (!window.isDestroyed()) window.webContents.send('desktop:status-changed', value);
}
function status() { return lifecycleStatus.state === 'Running' ? (coordinator?.getStatus() || {state: 'Current', installed_version: app.getVersion()}) : lifecycleStatus; }
function recovery(message, detail = '') {
  lifecycleStatus = {state: 'Recovery', channel:distribution.channel, title: 'Rieke OS recovery', message, detail}; broadcast(lifecycleStatus);
  for (const window of windows) if (!window.isDestroyed()) window.loadFile(recoveryPage).catch(() => {});
}
async function acknowledgeDrafts() {
  return draftBarrier.prepare(scientificWindows);
}
async function prepareQuit() {
  const drafts = await acknowledgeDrafts(); if (!drafts.ready) return drafts;
  return supervisor ? supervisor.drain() : {ready: true};
}
async function orderlyQuit() {
  if (quitInProgress) return {ready: false, reason: 'Quit preparation is already in progress'};
  quitInProgress = true;
  try {
    if (distribution.channel !== 'unsigned-testing' && coordinator?.getStatus().state === 'Ready') {
      const result = await coordinator.installPrepared();
      if (result.installing) return result;
      if (!result.ready) { broadcast({...status(), message: result.reason}); return result; }
    }
    const result = await prepareQuit();
    if (!result.ready) { broadcast({...status(), message: result.reason}); return result; }
    quitAuthorized = true; coordinator?.stop(); app.quit(); return result;
  } finally { quitInProgress = false; }
}
function createWindow() {
  const window = new BrowserWindow({width: 1440, height: 960, minWidth: 960, minHeight: 650,
    title: 'Rieke OS', backgroundColor: '#f4f5f3', show: false,
    webPreferences: {preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true,
      sandbox: true, nodeIntegration: false, nodeIntegrationInWorker: false,
      webSecurity: true, allowRunningInsecureContent: false, webviewTag: false, spellcheck: false,
      partition: 'rieke-desktop'}});
  windows.add(window);
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
  window.webContents.on('render-process-gone', () => { window.draftUnavailable = scientificWindows.has(window); recovery('The scientific window stopped. Restore the window to acknowledge drafts before shutdown.'); });
  window.on('close', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
  window.on('closed', () => { windows.delete(window); scientificWindows.delete(window); });
  window.loadFile(recoveryPage); return window;
}
function configureSession() {
  const ownedSession = session.fromPartition('rieke-desktop');
  ownedSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  ownedSession.setPermissionCheckHandler(() => false);
  ownedSession.webRequest.onBeforeRequest((details, callback) => {
    const owned = [...windows].some(win => !win.isDestroyed() && win.webContents.id === details.webContentsId);
    const localAsset = details.url.startsWith('file:') && (() => {
      try { return require('node:url').fileURLToPath(details.url).startsWith(__dirname + path.sep); } catch { return false; }
    })();
    callback({cancel: !owned || (!localAsset && !isOwnedURL(details.url, supervisor?.origins))});
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
async function startScientificUI() {
  if (startupInProgress) return;
  startupInProgress = true;
  try {
    let origin;
    if (supervisor.child && !supervisor.exited) {
      const health = await supervisor.api('/api/desktop/health');
      if (!matchesHealth(health, supervisor.expectedHealth())) throw new Error('Existing backend is not ready for recovery');
      origin = supervisor.origin; supervisor.ready = true; supervisor.origins.add(origin);
    } else origin = await supervisor.start();
    if (!coordinator) {
      const createUpdateCoordinator = distribution.channel === 'unsigned-testing'
        ? require('./testing-updater.cjs').createTestingUpdateCoordinator
        : require('./updater.cjs').createUpdateCoordinator;
      coordinator = createUpdateCoordinator({app, publishStatus: broadcast, prepareQuit,
        authorizeQuit: () => { quitAuthorized = true; }, revokeQuit: () => { quitAuthorized = false; },
        onInstallationFailure: () => { scientificWindows.clear(); recovery('Native update installation failed. Restart the installed backend or restore the verified previous app.'); },
        manifest: supervisor.manifest, distribution});
      coordinator.start().catch(() => broadcast({state:'Deferred',channel:distribution.channel,message:'Update check unavailable. The installed app remains usable.'}));
    }
    lifecycleStatus = {state: 'Running'};
    for (const window of windows) {
      await window.loadURL(origin); window.draftUnavailable = false; scientificWindows.add(window);
    }
    broadcast(status());
  } catch (error) { recovery('The packaged scientific backend could not start. Projects have not been opened.', error.message); }
  finally { startupInProgress = false; }
}
function registerIPC() {
  const handle = (channel, action) => ipcMain.handle(channel, async (event, payload) => {
    const window = validateSender(event, windows, supervisor?.origins, [recoveryPage]); return action(payload, window);
  });
  const noPayload = (channel, action) => handle(channel, (payload, window) => {
    if (payload !== undefined) throw new TypeError('This desktop operation accepts no payload');
    return action(window);
  });
  noPayload('desktop:status', () => status());
  noPayload('desktop:check-updates', () => coordinator ? coordinator.check() : status());
  noPayload('desktop:download-update', () => {
    if (!coordinator?.download) throw new Error('Update download is unavailable for this installation.');
    return coordinator.download();
  });
  noPayload('desktop:restart-to-update', () => {
    if (!coordinator) throw new Error('No prepared update is available.');
    return coordinator.installPrepared();
  });
  noPayload('desktop:quit', () => orderlyQuit());
  noPayload('desktop:retry-startup', () => { if (bootstrap) throw new Error('Install the complete app before starting projects'); return startScientificUI(); });
  handle('desktop:restore-previous', async payload => {
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
  handle('desktop:save-draft', async payload => {
    return draftStore.save(payload);
  });
  handle('desktop:load-draft', async projectId => {
    return draftStore.load(projectId);
  });
  handle('desktop:reset-draft', projectId => draftStore.reset(projectId));
  noPayload('desktop:choose-project-folder', async window => {
    const result = await dialog.showOpenDialog(window, {properties: ['openDirectory', 'createDirectory'], title: 'Choose project folder'});
    return result.canceled ? null : result.filePaths[0];
  });
  handle('desktop:open-release-notes', async url => {
    if (!approvedReleaseURL(url)) throw new TypeError('Only official HTTPS release notes may be opened');
    await shell.openExternal(url); return {opened: true};
  });
  noPayload('desktop:install-and-open', async () => {
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
    draftStore = new DraftStore(app.getPath('userData'));
    supervisor = new ServiceSupervisor({resourcesPath: app.isPackaged ? process.resourcesPath : path.join(__dirname, 'build'),
      userData: app.getPath('userData'), appVersion: app.getVersion(), onFailure: recovery});
    configureSession(); registerIPC(); createWindow();
    powerMonitor.on('shutdown', event => { if (!quitAuthorized) { event.preventDefault(); void orderlyQuit(); } });
    Menu.setApplicationMenu(Menu.buildFromTemplate([{label: 'Rieke OS', submenu: [{role: 'about'}, {type: 'separator'},
      {label: 'Check for Updates', click: () => coordinator?.check()}, {type: 'separator'}, {label: 'Quit Rieke OS', accelerator: 'CommandOrControl+Q', click: () => orderlyQuit()}]},
    {label: 'Edit', submenu: [{role: 'undo'}, {role: 'redo'}, {type: 'separator'}, {role: 'cut'}, {role: 'copy'}, {role: 'paste'}, {role: 'selectAll'}]},
    {label: 'Window', submenu: [{role: 'minimize'}, {role: 'zoom'}]}]));
    if (bootstrap) { lifecycleStatus = {state: 'Bootstrap', channel:distribution.channel, title: 'Install Rieke OS', message: 'Install this complete app in your Applications folder and open it.', detail: distribution.channel === 'unsigned-testing' ? 'Unsigned testing release. Install a copy downloaded from the official Rieke OS GitHub release. macOS may require a one-time Open Anyway approval in Privacy & Security. Existing projects stay in their selected folders.' : 'The downloaded app and installed copy must pass Developer ID signature verification. Existing projects stay in their selected folders.'}; broadcast(lifecycleStatus); }
    else await startScientificUI();
  }).catch(error => { console.error('Desktop startup failed:', error.name); app.exit(1); });
}
