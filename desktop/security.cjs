'use strict';
const path = require('node:path');
const {fileURLToPath} = require('node:url');
const PROJECT_ID = /^(?:launcher|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;
function isOwnedURL(url, origin, localPages = []) {
  try {
    const parsed = new URL(url);
    if (parsed.username || parsed.password) return false;
    if (origin && (typeof origin === 'string' ? parsed.origin === origin : origin.has(parsed.origin)) && parsed.protocol === 'http:') return true;
    return parsed.protocol === 'file:' && localPages.includes(path.resolve(fileURLToPath(parsed)));
  } catch { return false; }
}
function validateSender(event, windows, origin, localPages) {
  const window = [...windows].find(win => !win.isDestroyed() && win.webContents === event.sender);
  if (!window || !event.senderFrame || event.senderFrame !== event.sender.mainFrame ||
      !isOwnedURL(event.senderFrame.url, origin, localPages)) throw new Error('Unauthorized desktop frame');
  return window;
}
function validateProjectId(value) {
  if (typeof value !== 'string' || !PROJECT_ID.test(value)) throw new TypeError('Invalid project identity');
  return value.toLowerCase();
}
function validateDraft(payload) {
  if (!payload || Object.keys(payload).sort().join(',') !== 'projectId,value') throw new TypeError('Invalid draft payload');
  const projectId = validateProjectId(payload.projectId);
  const serialized = JSON.stringify(payload.value);
  if (serialized === undefined || Buffer.byteLength(serialized) > 2 * 1024 * 1024) throw new TypeError('Draft exceeds size limit');
  return {projectId, serialized};
}
function approvedReleaseURL(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && url.hostname === 'github.com' &&
    !url.username && !url.password && /^\/maxwellsdm1867\/Rieke-OS\/releases(?:\/|$)/.test(url.pathname); } catch { return false; }
}
module.exports = {isOwnedURL, validateSender, validateDraft, validateProjectId, approvedReleaseURL};
