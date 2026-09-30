'use strict';
const {randomUUID} = require('node:crypto');
class DraftBarrier {
  constructor({timeout = 10000, send = (window, value) => window.webContents.send('desktop:prepare-close', value)} = {}) {
    this.timeout = timeout; this.send = send; this.pending = new Map();
  }
  acknowledge(payload, window) {
    if (!payload || typeof payload.requestId !== 'string' || typeof payload.ok !== 'boolean' || Object.keys(payload).sort().join(',') !== 'ok,requestId') throw new TypeError('Invalid draft acknowledgement');
    const pending = this.pending.get(payload.requestId);
    if (!pending || pending.window !== window) throw new Error('No matching draft request');
    pending.resolve(payload.ok); return {acknowledged: true};
  }
  async prepare(windows) {
    if ([...windows].some(window => window.isDestroyed() || window.draftUnavailable))
      return {ready: false, reason: 'Renderer drafts have not been acknowledged. Restore the scientific window before quitting.'};
    const results = await Promise.all([...windows].map(window => new Promise(resolve => {
      const requestId = randomUUID();
      const finish = ok => { clearTimeout(timer); this.pending.delete(requestId); resolve(ok); };
      const timer = setTimeout(() => finish(false), this.timeout);
      this.pending.set(requestId, {window, resolve: finish});
      try { this.send(window, {requestId}); } catch { finish(false); }
    })));
    return results.every(Boolean) ? {ready: true} : {ready: false, reason: 'Draft persistence was not acknowledged; quit and replacement are deferred'};
  }
}
module.exports = {DraftBarrier};
