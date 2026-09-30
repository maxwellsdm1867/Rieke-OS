'use strict';
const fs = require('./physical-fs.cjs').promises;
const path = require('node:path');
const {compareVersions, signingIdentity, validateDownloadedCandidate} = require('./updater-validation.cjs');

function createUpdateCoordinator({app, manifest, publishStatus = () => {}, prepareQuit, authorizeQuit = () => {}, revokeQuit = () => {}, onInstallationFailure = () => {}, updater, verifyCandidate = validateDownloadedCandidate, verifyInstalled = signingIdentity, retainPrevious = options => require('./update-recovery.cjs').retainPriorBundle(options), receiptPath, timers = globalThis, random = Math.random, enabled, installedBundle}) {
  const cacheDirectory = path.join(app.getPath('userData'), 'updates');
  receiptPath ||= path.join(cacheDirectory, 'status.json');
  installedBundle ||= path.resolve(app.getPath('exe'), '../../..');
  let status = {state: 'Current', installed: manifest.application_version, available: null, message: 'Using the installed version.'};
  let pending = null, checking = null, installing = null, timer = null, stopped = false, active = false, validation = null;
  let receiptWrites = Promise.resolve();
  const listeners = [];
  async function verifyPendingArchive() {
    if (!pending?.archive_sha256) return;
    const crypto = require('node:crypto'), hasher = crypto.createHash('sha256');
    const handle = await fs.open(pending.downloadedFile, 'r');
    try {for await (const chunk of handle.createReadStream()) hasher.update(chunk);} finally {await handle.close();}
    if (hasher.digest('hex') !== pending.archive_sha256) throw new Error('Prepared archive changed');
  }
  function set(state, fields = {}) {
    status = {...status, ...fields, state};
    publishStatus({...status});
    const snapshot = {format: 'rieke-desktop-update-status', version: 1, installed: status.installed, available: status.available, state, validated: pending?.version || null, checked_at: status.checked_at || null};
    receiptWrites = receiptWrites.catch(() => {}).then(async () => {
      await fs.mkdir(path.dirname(receiptPath), {recursive: true, mode: 0o700});
      const temporary = receiptPath + '.tmp';
      await fs.writeFile(temporary, JSON.stringify(snapshot) + '\n', {mode: 0o600});
      await fs.rename(temporary, receiptPath);
    }).catch(() => {});
    return {...status};
  }
  function defer(message) { return set(pending ? 'Ready' : 'Deferred', {available: pending?.version || status.available, message, check_error: message}); }
  const on = (event, listener) => {updater.on(event, listener); listeners.push([event, listener]);};
  async function downloaded(event) {
    if (!active || stopped) return;
    set('Validating', {available: event.version, message: 'Verifying downloaded app identity and compatibility.'});
    // MacUpdater's native proxy now refers to this event's ZIP. A previous
    // candidate can no longer authorize that proxy if this ZIP is rejected.
    pending = null;
    try {
      const candidate = await verifyCandidate({downloadedFile: event.downloadedFile, version: event.version, manifest, cacheDirectory, installedBundle});
      await retainPrevious({app, manifest});
      if (!active || stopped) return;
      pending = candidate;
      set('Ready', {available: candidate.version, native_staging_verified: false, startup_health_verified: false, message: 'Update verified and prepared for an orderly quit. Native installation and startup health are checked separately.'});
    } catch {
      defer('The downloaded update was rejected. The installed app remains usable.');
    }
  }
  function schedule() {
    if (stopped || !active) return;
    timer = timers.setTimeout(async () => {await check(); schedule();}, Math.round(3600000 * (0.9 + random() * 0.2)));
    timer?.unref?.();
  }
  async function check() {
    if (!active || stopped) return {...status};
    if (pending) return {...status};
    if (checking) return checking;
    if (['Downloading', 'Validating', 'Draining', 'Installing'].includes(status.state)) return {...status};
    checking = (async () => {
      set('Checking', {checked_at: new Date().toISOString(), check_error: null, message: 'Checking for a published update.'});
      try {
        const result = await updater.checkForUpdates();
        // The pinned client resolves metadata before its automatic download.
        // Observe that separate promise so a failed checksum/network write
        // cannot escape as an unhandled rejection in the Electron main process.
        if (result?.downloadPromise) await result.downloadPromise;
      } catch { defer('Update check unavailable. The installed app remains usable.'); }
      return {...status};
    })().finally(() => {checking = null;});
    return checking;
  }
  async function start() {
    if (active || stopped) return {...status};
    // Receipts are display hints only: a previous Ready never authorizes install.
    try {
      const previous = JSON.parse(await fs.readFile(receiptPath, 'utf8'));
      if (previous.format === 'rieke-desktop-update-status' && previous.version === 1 && previous.installed === manifest.application_version && previous.validated) status.available = previous.available;
    } catch {}
    if (enabled === false || !app.isPackaged || process.platform !== 'darwin' || process.arch !== 'arm64') return set('Deferred', {message: 'Automatic updates require a qualified signed macOS Apple Silicon installation.'});
    try { await verifyInstalled(installedBundle); } catch { return set('Deferred', {message: 'Automatic updates are disabled for this unsigned development build.'}); }
    updater ||= require('electron-updater').autoUpdater;
    updater.autoInstallOnAppQuit = false;
    updater.autoDownload = true;
    updater.autoRunAppAfterInstall = false;
    updater.allowDowngrade = false;
    updater.allowPrerelease = false;
    updater.logger = null; // Never log cache/session URLs or local paths.
    updater.setFeedURL({provider: 'github', owner: 'maxwellsdm1867', repo: 'Rieke-OS', private: false});
    on('checking-for-update', () => set('Checking'));
    on('update-available', info => {
      try {
        if (compareVersions(info.version, manifest.application_version) <= 0) throw new Error('Older release');
        set('Available', {available: info.version, release_url: `https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/v${info.version}`, message: `Rieke OS ${info.version} is available.`});
      } catch { updater.autoDownload = false; defer('Published update metadata was rejected.'); }
    });
    on('download-progress', progress => set('Downloading', {progress: Math.max(0, Math.min(100, Number(progress.percent) || 0)), message: 'Downloading an update quietly.'}));
    on('update-not-available', () => set(pending ? 'Ready' : 'Current', {message: pending ? 'The verified pending update remains prepared.' : 'The installed version is current.'}));
    on('update-downloaded', event => { validation = downloaded(event); });
    on('error', () => {
      if (status.state === 'Installing') {
        revokeQuit();
        defer('Native installation failed. Restart the installed app from recovery.');
        onInstallationFailure();
      } else defer('Update preparation failed. The installed app remains usable.');
    });
    active = true;
    await check();
    schedule();
    return {...status};
  }
  async function installPrepared() {
    if (installing) return installing;
    if (validation) await validation;
    if (installing) return installing;
    if (!pending || status.state !== 'Ready') return {ready: false, reason: 'No verified update is prepared.'};
    installing = (async () => {
      set('Draining', {message: 'Saving drafts and waiting for all scientific services to close.'});
      if (pending.archive_sha256) {
        try { await verifyPendingArchive(); }
        catch { pending = null; defer('The prepared update changed or is missing. Installation is deferred.'); return {ready: false, reason: status.message}; }
      }
      let result;
      try { result = await prepareQuit(); } catch { result = {ready: false}; }
      if (result?.ready !== true) {
        set('Ready', {message: 'Update remains pending: a draft, writer or service has not acknowledged closure.'});
        return {ready: false, reason: result?.reason || status.message};
      }
      // Drain can take long enough for a cached ZIP to change. Check the exact
      // validated bytes again at the installation boundary. Services are already
      // closed here, so failed verification must offer backend recovery.
      try { await verifyPendingArchive(); }
      catch {
        pending = null; revokeQuit();
        defer('The prepared update changed during shutdown. Restart the installed app from recovery.');
        onInstallationFailure(); return {ready: false, reason: status.message};
      }
      set('Installing', {message: 'All owned services have closed; handing the verified app to the native installer.'});
      try { authorizeQuit(); updater.quitAndInstall(); return {ready: true, installing: true}; }
      catch { revokeQuit(); defer('Native installation failed. Use recovery to restart the installed app.'); onInstallationFailure(); return {ready: false, reason: status.message}; }
    })().finally(() => {installing = null;});
    return installing;
  }
  function stop() { stopped = true; active = false; if (timer) timers.clearTimeout(timer); for (const [event, listener] of listeners) updater.removeListener(event, listener); }
  return {getStatus: () => ({...status}), check, start, stop, installPrepared};
}
module.exports = {createUpdateCoordinator};
