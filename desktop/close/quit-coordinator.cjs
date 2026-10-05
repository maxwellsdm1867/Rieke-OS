'use strict';
// Explicit exit has a finite deadline. Replacement continues to require every
// clean receipt through the separate prepareQuit path.
function bounded(action, milliseconds, reason) {
  let timer;
  return Promise.race([Promise.resolve().then(action), new Promise(resolve => {
    timer = setTimeout(() => resolve({ready:false, reason, timedOut:true}), Math.max(1, milliseconds));
  })]).finally(() => clearTimeout(timer));
}
class QuitCoordinator {
  constructor({prepareDrafts, cleanup, exit, publish = () => {}, deadline = 35000, draftDeadline = 5000}) {
    Object.assign(this, {prepareDrafts, cleanup, exit, publish, deadline, draftDeadline});
    this.pending = null;
  }
  quit() {
    if (this.pending) return this.pending;
    this.pending = this.run();
    return this.pending;
  }
  async run() {
    const until = Date.now() + this.deadline, remaining = () => Math.max(1, until - Date.now());
    const warnings = [];
    this.publish({state:'Closing', title:'Closing Disco', message:'Finishing accepted changes and the latest available view.'});
    let drafts, backend;
    try {
      drafts = await bounded(() => this.prepareDrafts(Math.min(this.draftDeadline, remaining())),
        Math.min(this.draftDeadline, remaining()), 'The renderer did not confirm the latest view or accepted changes. The last saved view is retained.');
      if (!drafts.ready) warnings.push(drafts.reason);
    } catch (error) { warnings.push(error.message); }
    try {
      backend = await bounded(() => this.cleanup({timeout:remaining(), drafts}), remaining(),
        'Service cleanup exceeded the quit deadline. Its existing operation records are retained for reconciliation on relaunch.');
      if (!backend.ready) warnings.push(backend.reason);
    } catch (error) { warnings.push(error.message); }
    const result = {ready:true, clean:backend?.ready === true && drafts?.ready === true, services_closed:backend?.ready === true, drafts_saved:drafts?.ready === true, warnings};
    if (warnings.length) this.publish({state:'Closing', title:'Closing with recovery pending', message:warnings.join(' ')});
    this.exit(result);
    return result;
  }
}
module.exports = {QuitCoordinator, bounded};
