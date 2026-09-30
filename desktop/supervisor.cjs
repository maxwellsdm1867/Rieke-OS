'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const net = require('node:net');
const {spawn, execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {randomUUID, randomBytes, createHash} = require('node:crypto');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function inspectExecutable(pid) {
  try {
    const {stdout} = await promisify(execFile)('/bin/ps', ['-p', String(pid), '-o', 'comm=']);
    const executable = stdout.trim(); return executable ? await fs.realpath(executable) : null;
  } catch (error) { if (error.code === 1 || error.code === 'ENOENT') return null; throw error; }
}
async function atomicJSON(filename, value) {
  await fs.mkdir(path.dirname(filename), {recursive: true, mode: 0o700});
  const temporary = `${filename}.${randomUUID()}.tmp`;
  await fs.writeFile(temporary, JSON.stringify(value, null, 2), {mode: 0o600});
  await fs.rename(temporary, filename);
}
async function availablePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => server.once('error', reject).listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
function matchesHealth(health, expected) {
  return health?.ready === true && Object.entries(expected).every(([key, value]) =>
    JSON.stringify(health[key]) === JSON.stringify(value));
}
class ServiceSupervisor {
  constructor({resourcesPath, userData, appVersion, spawnProcess = spawn, request = fetch, inspectProcess = inspectExecutable, startupTimeout = 90000, drainTimeout = 30000, onFailure = () => {}}) {
    Object.assign(this, {resourcesPath, userData, appVersion, spawnProcess, request, inspectProcess, startupTimeout, drainTimeout, onFailure});
    this.capability = randomBytes(32).toString('hex'); this.sessionId = randomUUID();
    this.rendererCapability = createHash('sha256').update(this.capability + ':renderer').digest('hex');
    this.origins = new Set(); this.child = null; this.exited = true; this.ready = false;
    this.registryPath = path.join(userData, 'desktop-service.json');
  }
  async loadManifest() {
    const runtime = path.join(this.resourcesPath, 'runtime');
    const manifestPath = path.join(runtime, 'runtime-manifest.json');
    this.manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    if (this.manifest.format !== 'rieke-desktop-runtime' || this.manifest.version !== 1 ||
        this.manifest.platform !== process.platform || this.manifest.architecture !== process.arch ||
        this.manifest.application_version !== this.appVersion || !this.manifest.source_commit ||
        !Array.isArray(this.manifest.workspace_formats) || !Number.isInteger(this.manifest.database_compatibility))
      throw new Error('Packaged runtime identity or compatibility does not match this application');
    this.executable = await fs.realpath(path.join(runtime, 'python', 'bin', 'python3.11'));
    this.entry = await fs.realpath(path.join(runtime, 'application', 'python', 'workspace_desktop.py'));
    const root = await fs.realpath(runtime);
    if (![this.executable, this.entry].every(item => item.startsWith(root + path.sep))) throw new Error('Runtime entry escapes packaged resources');
    return this.manifest;
  }
  async start() {
    if (this.child && !this.exited) throw new Error('Previous backend is still running; replacement is deferred');
    await this.loadManifest();
    try {
      const previous = JSON.parse(await fs.readFile(this.registryPath, 'utf8'));
      if (!Number.isSafeInteger(previous.pid) || previous.pid <= 0 || !path.isAbsolute(previous.executable || '') || !previous.session_id)
        throw new Error('Previous service registry is malformed; resolve recovery before opening projects');
      const actualExecutable = await this.inspectProcess(previous.pid);
      if (actualExecutable === previous.executable) throw new Error('A prior matching service is still active; resolve recovery before opening projects');
      for (const record of previous.services || []) {
        if (await this.inspectProcess(record.pid) === previous.executable)
          throw new Error('A prior project service is still active; resolve recovery before opening projects');
      }
      // PID reuse is never treated as ownership and never authorizes termination.
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const port = await availablePort(); this.origin = `http://127.0.0.1:${port}`;
    const backendState = path.join(this.userData, 'backend');
    await fs.mkdir(backendState, {recursive: true, mode: 0o700});
    const env = {HOME: process.env.HOME, TMPDIR: process.env.TMPDIR, LANG: 'en_US.UTF-8',
      PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1', RIEKE_DESKTOP_CAPABILITY: this.capability,
      RIEKE_PARSER_CONFIG: path.join(backendState, 'parser', 'config.ini')};
    this.child = this.spawnProcess(this.executable, ['-B', this.entry, '--host', '127.0.0.1', '--port', String(port),
      '--resources', this.resourcesPath, '--user-state', backendState,
      '--manifest', path.join(this.resourcesPath, 'runtime', 'runtime-manifest.json'), '--session-id', this.sessionId],
    {cwd: backendState, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true});
    this.exited = false; this.exitCode = null; this.abnormalExit = false; this.stopping = false; this.bound = false;
    const expectedBound = {pid: this.child.pid, session_id: this.sessionId, port,
      application_version: this.appVersion, source_commit: this.manifest.source_commit};
    let finishBound;
    const binding = new Promise(resolve => { finishBound = resolve; });
    let stdoutPending = '';
    this.child.stdout?.on('data', chunk => {
      stdoutPending += chunk.toString('utf8');
      if (stdoutPending.length > 65536) { stdoutPending = ''; return; }
      let index;
      while ((index = stdoutPending.indexOf('\n')) >= 0) {
        const line = stdoutPending.slice(0, index); stdoutPending = stdoutPending.slice(index + 1);
        if (!line.startsWith('RIEKE_DESKTOP_BOUND=')) continue;
        try {
          const value = JSON.parse(line.slice('RIEKE_DESKTOP_BOUND='.length));
          if (Object.entries(expectedBound).every(([key, expected]) => value[key] === expected)) {
            this.bound = true; finishBound(true);
          }
        } catch {}
      }
    });
    this.child.once('error', () => { this.exited = true; this.exitCode = 'spawn'; finishBound(false); });
    this.child.once('exit', code => { this.exited = true; this.exitCode = code; this.abnormalExit = !this.stopping;
      finishBound(false); if (this.ready && !this.stopping) { this.origins.clear(); this.onFailure('The owned backend stopped unexpectedly. Scientific projects are closed until recovery.'); } });
    // Backend output may contain scientific paths or credentials. Do not persist or expose it.
    this.child.stdout?.resume(); this.child.stderr?.resume();
    this.registry = {pid: this.child.pid, executable: this.executable, entry: this.entry,
      session_id: this.sessionId, source_commit: this.manifest.source_commit, application_version: this.appVersion, port};
    await atomicJSON(this.registryPath, this.registry);
    const expected = this.expectedHealth(); const deadline = Date.now() + this.startupTimeout;
    let boundTimer;
    const bound = await Promise.race([binding, new Promise(resolve => { boundTimer = setTimeout(() => resolve(false), this.startupTimeout); })]);
    clearTimeout(boundTimer);
    if (!bound) throw new Error(this.exited ? `Packaged backend exited before owning its listener (${this.exitCode})` : 'Packaged backend listener deadline exceeded; no desktop capability was sent');
    while (Date.now() < deadline && !this.exited) {
      try {
        const health = await this.api('/api/desktop/health');
        if (!matchesHealth(health, expected)) throw new Error('Owned backend identity mismatch');
        this.origins.add(this.origin); this.ready = true; return this.origin;
      } catch (error) { this.lastStartupError = error.message; await delay(200); }
    }
    throw new Error(this.exited ? `Packaged backend exited before readiness (${this.exitCode})` : 'Packaged backend readiness deadline exceeded; backend retained for safe recovery');
  }
  expectedHealth() { return {pid: this.child.pid, session_id: this.sessionId,
    application_version: this.manifest.application_version, source_commit: this.manifest.source_commit,
    workspace_formats: this.manifest.workspace_formats, database_compatibility: this.manifest.database_compatibility}; }
  async api(route, {origin = this.origin, method = 'GET', timeout = 3000, body = {}} = {}) {
    if (!this.bound) throw new Error('Owned backend has not proved listener ownership');
    if (origin !== this.origin || !/^\/api\/desktop\/[a-z-]+$/.test(route)) throw new Error('Desktop controls target only the exact owned root service');
    const response = await this.request(`${origin}${route}`, {method,
      headers: {'X-Rieke-Desktop-Capability': this.capability, 'X-Workspace-Request': '1', 'Content-Type': 'application/json'},
      signal: AbortSignal.timeout(timeout), ...(method === 'POST' ? {body: JSON.stringify(body)} : {})});
    let value; try { value = await response.json(); } catch { throw new Error('Malformed desktop service response'); }
    if (!response.ok) throw new Error(value.error || (response.status === 409 ? 'Scientific writes are still active' : 'Desktop service request failed'));
    return value;
  }
  async authorizeProjectURL(value) {
    const url = new URL(value);
    if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.username || url.password) return false;
    const rootHealth = await this.api('/api/desktop/health');
    if (!matchesHealth(rootHealth, this.expectedHealth())) return false;
    if (url.origin === this.origin) return true;
    this.registry.services = rootHealth.services || [];
    await atomicJSON(this.registryPath, this.registry);
    const record = rootHealth.services?.find(item => item.port === Number(url.port));
    if (!record || record.bound !== true || record.session_id !== this.sessionId || !record.project_uuid || !record.project_path) { this.origins.delete(url.origin); return false; }
    // Root owns the child's private bind receipt and exact process creation time.
    // It performs the native process check before sending control capabilities;
    // main never sends its capability to a possibly reused child port.
    const authorization = await this.api('/api/desktop/authorize-project', {method: 'POST', body: {port: Number(url.port)}});
    if (!authorization.record || !Object.entries(record).every(([key, value]) => JSON.stringify(authorization.record[key]) === JSON.stringify(value))) return false;
    const childHealth = authorization.health;
    if (!matchesHealth(childHealth, {pid: record.pid, session_id: this.sessionId,
      application_version: this.appVersion, source_commit: this.manifest.source_commit,
      workspace_formats: this.manifest.workspace_formats, database_compatibility: this.manifest.database_compatibility,
      project_uuid: record.project_uuid, project_path: record.project_path})) return false;
    this.origins.add(url.origin); return true;
  }
  async drain() {
    if (this.abnormalExit) return {ready: false, reason: 'Backend exited without a drain acknowledgement; project service exit must be recovered before replacement'};
    if (!this.child || this.exited) { this.ready = false; await fs.rm(this.registryPath, {force: true}); return {ready: true}; }
    try {
      const result = await this.api('/api/desktop/drain', {method: 'POST', timeout: this.drainTimeout});
      if (result.ready !== true) throw new Error('Backend did not acknowledge drain');
      // Ack only starts the exit phase; process exit is independent required evidence.
      this.stopping = true;
      await this.api('/api/desktop/stop', {method: 'POST', timeout: 3000});
      const deadline = Date.now() + this.drainTimeout; this.ready = false;
      while (!this.exited && Date.now() < deadline) await delay(50);
      if (!this.exited) return {ready: false, reason: 'Backend has not acknowledged process exit; replacement is deferred'};
      this.origins.clear(); await fs.rm(this.registryPath, {force: true}); return {ready: true};
    } catch (error) {
      this.stopping = false;
      try { await this.api('/api/desktop/resume', {method: 'POST'}); } catch {}
      return {ready: false, reason: error.message};
    }
  }
}
module.exports = {ServiceSupervisor, matchesHealth, atomicJSON, availablePort, inspectExecutable};
