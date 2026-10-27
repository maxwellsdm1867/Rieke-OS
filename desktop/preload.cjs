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
  activateRetainedProject:identity=>ipcRenderer.invoke('desktop:activate-retained-project',identity),
  activateProject:url=>ipcRenderer.invoke('desktop:activate-project',url),
  prepareProjectClose:identity=>ipcRenderer.invoke('desktop:prepare-project-close',identity),
  confirmProjectClosed:identity=>ipcRenderer.invoke('desktop:confirm-project-closed',identity),
  cancelProjectClose:identity=>ipcRenderer.invoke('desktop:cancel-project-close',identity),
  projectVisibility:()=>ipcRenderer.invoke('desktop:project-visibility'),
  onProjectVisibility:callback=>subscribe('desktop:project-visibility',callback),
  onProjectResume:callback=>subscribe('desktop:project-resume',callback),
  cancelStartup:()=>ipcRenderer.invoke('desktop:cancel-startup'),
  openStartup:()=>ipcRenderer.invoke('desktop:open-startup'),
  startupSession:()=>ipcRenderer.invoke('desktop:startup-session'),
  chooseStartup:()=>ipcRenderer.invoke('desktop:choose-startup'),
  applyAppIcon: variant=>ipcRenderer.invoke('desktop:app-icon',variant),
  onUndo: callback => subscribe('desktop:undo', callback),
  undoText: () => ipcRenderer.invoke('desktop:undo-text'),

  status: () => ipcRenderer.invoke('desktop:status'),
  checkForUpdates: () => ipcRenderer.invoke('desktop:check-updates'),
  downloadUpdate: () => ipcRenderer.invoke('desktop:download-update'),
  restartToUpdate: () => ipcRenderer.invoke('desktop:restart-to-update'),
  onStatus: callback => subscribe('desktop:status-changed', callback),
  onPrepareClose: callback => subscribe('desktop:prepare-close', callback),
  acknowledgeDrafts: (requestId, result) => ipcRenderer.invoke('desktop:drafts-ack', {requestId, ok: result?.ok === true, ...(typeof result?.reason === 'string' ? {reason:result.reason} : {})}),
  chooseProjectFolder: () => ipcRenderer.invoke('desktop:choose-project-folder'),
  saveDraft: payload => ipcRenderer.invoke('desktop:save-draft', payload),
  loadDraft: projectId => ipcRenderer.invoke('desktop:load-draft', projectId),
  resetDraft: projectId => ipcRenderer.invoke('desktop:reset-draft', projectId),
  openReleaseNotes: url => ipcRenderer.invoke('desktop:open-release-notes', url),
  installAndOpen: () => ipcRenderer.invoke('desktop:install-and-open'),
  newSession: () => ipcRenderer.invoke('desktop:new-session'),
  retryStartup: () => ipcRenderer.invoke('desktop:retry-startup'),
  restorePreviousVersion: () => ipcRenderer.invoke('desktop:restore-previous'),
  quit: () => ipcRenderer.invoke('desktop:quit')
}));
