'use strict';
const {contextBridge, ipcRenderer} = require('electron');
function subscribe(channel, callback) {
  if (typeof callback !== 'function') throw new TypeError('Callback required');
  const listener = (_event, value) => callback(value);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}
contextBridge.exposeInMainWorld('riekeDesktop', Object.freeze({
  protocolVersion: 1,
  status: () => ipcRenderer.invoke('desktop:status'),
  checkForUpdates: () => ipcRenderer.invoke('desktop:check-updates'),
  downloadUpdate: () => ipcRenderer.invoke('desktop:download-update'),
  restartToUpdate: () => ipcRenderer.invoke('desktop:restart-to-update'),
  onStatus: callback => subscribe('desktop:status-changed', callback),
  onPrepareClose: callback => subscribe('desktop:prepare-close', callback),
  acknowledgeDrafts: (requestId, result) => ipcRenderer.invoke('desktop:drafts-ack', {requestId, ok: result?.ok === true}),
  chooseProjectFolder: () => ipcRenderer.invoke('desktop:choose-project-folder'),
  saveDraft: payload => ipcRenderer.invoke('desktop:save-draft', payload),
  loadDraft: projectId => ipcRenderer.invoke('desktop:load-draft', projectId),
  resetDraft: projectId => ipcRenderer.invoke('desktop:reset-draft', projectId),
  openReleaseNotes: url => ipcRenderer.invoke('desktop:open-release-notes', url),
  installAndOpen: () => ipcRenderer.invoke('desktop:install-and-open'),
  retryStartup: () => ipcRenderer.invoke('desktop:retry-startup'),
  restorePreviousVersion: () => ipcRenderer.invoke('desktop:restore-previous'),
  quit: () => ipcRenderer.invoke('desktop:quit')
}));
