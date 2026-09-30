'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const {validateDraft, validateProjectId} = require('./security.cjs');
const MAX_DRAFT_BYTES = 2 * 1024 * 1024;
function validStoredDraft(value, projectId) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    value.format === 'rieke-renderer-draft' && value.version === 1 && value.projectId === projectId &&
    value.value !== null && typeof value.value === 'object' && !Array.isArray(value.value);
}
class DraftStore {
  constructor(userData) { this.userData = userData; this.directory = path.join(userData, 'drafts'); this.pending = new Set(); }
  async location(projectId) {
    const id = validateProjectId(projectId);
    await fs.mkdir(this.directory, {recursive: true, mode: 0o700});
    const stat = await fs.lstat(this.directory);
    if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== process.getuid()) throw new Error('Draft state directory is redirected or not privately owned');
    return {id, filename: path.join(this.directory, `${id}.json`)};
  }
  recovery(id) { this.pending.add(id); return {format: 'rieke-draft-recovery', version: 1, projectId: id, reason: 'saved-draft-unreadable'}; }
  async load(projectId) {
    const id = validateProjectId(projectId);
    if (this.pending.has(id)) return this.recovery(id);
    let filename;
    try { ({filename} = await this.location(id)); }
    catch { return this.recovery(id); }
    try {
      const stat = await fs.lstat(filename);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size > MAX_DRAFT_BYTES || stat.uid !== process.getuid()) return this.recovery(id);
      const value = JSON.parse(await fs.readFile(filename, 'utf8'));
      return validStoredDraft(value, id) ? value : this.recovery(id);
    } catch (error) { return error.code === 'ENOENT' ? null : this.recovery(id); }
  }
  async save(payload) {
    const {projectId, serialized} = validateDraft(payload);
    if (!validStoredDraft(payload.value, projectId)) throw new TypeError('Invalid renderer draft identity or schema');
    await this.load(projectId);
    if (this.pending.has(projectId)) throw new Error('Saved view needs an explicit recovery decision before it can be replaced');
    const {filename} = await this.location(projectId);
    const temporary = `${filename}.${randomUUID()}.tmp`;
    try { await fs.writeFile(temporary, serialized, {mode: 0o600, flag: 'wx'}); await fs.rename(temporary, filename); }
    finally { await fs.rm(temporary, {force: true}); }
    return {saved: true};
  }
  async reset(projectId) {
    const id = validateProjectId(projectId);
    if (!this.pending.has(id)) throw new Error('No verified unreadable draft is pending recovery');
    const {filename} = await this.location(id);
    try { await fs.rename(filename, path.join(this.directory, `${id}.corrupt-${randomUUID()}.json`)); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    this.pending.delete(id); return {reset: true};
  }
}
module.exports = {DraftStore, validStoredDraft, MAX_DRAFT_BYTES};
