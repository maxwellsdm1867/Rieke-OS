'use strict';
const {randomUUID} = require('node:crypto');
class DraftBarrier {
  constructor({timeout = 10000, send = (window, value) => window.webContents.send('desktop:prepare-close', value)} = {}) {
    this.timeout = timeout; this.send = send; this.pending = new Map();
  }
  acknowledge(payload, window) {
    if (!payload || typeof payload.requestId !== 'string' || typeof payload.ok !== 'boolean' || Object.keys(payload).some(key => !['ok','requestId','reason'].includes(key)) || (payload.reason !== undefined && (typeof payload.reason !== 'string' || payload.reason.length > 1024))) throw new TypeError('Invalid draft acknowledgement');
    const pending = this.pending.get(payload.requestId);
    if (!pending || pending.window !== window) throw new Error('No matching draft request');
    pending.resolve({ok:payload.ok,reason:payload.reason}); return {acknowledged: true};
  }
  async prepare(windows, {timeout = this.timeout, purpose} = {}) {
    if(purpose!==undefined&&purpose!=='project-checkpoint')throw TypeError('Invalid draft preparation purpose');
    const unavailable = [...windows].some(window => window.isDestroyed() || window.draftUnavailable);
    const available = [...windows].filter(window => !window.isDestroyed() && !window.draftUnavailable);
    const results = await Promise.all(available.map(window => new Promise(resolve => {
      const requestId = randomUUID();
      const finish = value => { clearTimeout(timer); this.pending.delete(requestId); resolve(value); };
      const timer = setTimeout(() => finish({ok:false}), timeout);
      this.pending.set(requestId, {window, resolve: finish});
      try { this.send(window, {requestId,...(purpose?{purpose}:{})}); } catch { finish({ok:false}); }
    })));
    if(unavailable)results.push({ok:false,reason:'Renderer drafts have not been acknowledged. The last saved view is retained; its latest changes could not be confirmed.'});
    return results.every(result=>result.ok) ? {ready: true} : {ready: false, reason: results.filter(result=>!result.ok).map(result=>result.reason||'Latest view or accepted changes were not acknowledged. The last saved view is retained.').join(' ')};
  }
}
module.exports = {DraftBarrier};
