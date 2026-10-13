'use strict';
// Owned, forward-only first-open-after-upgrade diagnostic. No installed app,
// existing user HOME/project, cache deletion, or downgrade is accepted.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {createRequire} = require('node:module');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {captureNativeProcess, prepareInitialPresentation, closeOwned} = require('./retention-native-support.cjs');
const run = promisify(execFile);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const config = {};
for (let i = 2; i < process.argv.length; i += 2) {
  assert.ok(process.argv[i].startsWith('--') && process.argv[i + 1], 'Expected --key value');
  config[process.argv[i].slice(2)] = process.argv[i + 1];
}
for (const key of ['old-source-root', 'old-desktop-root', 'old-commit', 'new-source-root', 'new-desktop-root', 'new-commit', 'dependency-root', 'output']) {
  assert.ok(config[key], `Missing --${key}`);
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const hashFile = async file => sha(await fs.readFile(file));
const git = async (source, ...args) => (await run('git', ['-C', source, ...args])).stdout.trim();
async function validateStage(prefix) {
  const source = await fs.realpath(config[`${prefix}-source-root`]);
  const desktop = await fs.realpath(config[`${prefix}-desktop-root`]);
  assert.ok(!desktop.split(path.sep).some(part => part.endsWith('.app')), 'Installed application forbidden');
  assert.equal(await git(source, 'rev-parse', 'HEAD'), config[`${prefix}-commit`]);
  assert.equal(await git(source, 'status', '--porcelain'), '', 'Freeze exact clean source first');
  const runtime = path.join(desktop, 'build/runtime');
  const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'runtime-manifest.json')));
  assert.equal(manifest.source_commit, config[`${prefix}-commit`]);
  assert.equal(manifest.source_dirty, false);
  const files = (await git(source, 'ls-files', 'desktop')).split('\n');
  const desktopSource = {};
  for (const file of files) {
    const expected = await fs.readFile(path.join(source, file));
    const actual = await fs.readFile(path.join(desktop, path.relative('desktop', file)));
    assert.deepEqual(actual, expected, `Staged desktop differs: ${file}`);
    desktopSource[file] = sha(actual);
  }
  const ownerCode = {};
  for (const file of ['recording_workspace.py', 'workspace_service.py', 'disco/metadata/projection_cache.py',
    'disco/metadata/metadata_objects.py', 'disco/metadata/disk_index.py', 'disco/navigation/tree.py',
    'disco/navigation/predicates.py', 'disco/metadata/typed_index.py', 'disco/metadata/typed_lifecycle.py']) {
    const expected = await fs.readFile(path.join(source, 'python', file));
    assert.deepEqual(await fs.readFile(path.join(runtime, 'application/python', file)), expected, `Staged cache owner differs: ${file}`);
    ownerCode[file] = sha(expected);
  }
  return {source, desktop, runtime, commit: manifest.source_commit, desktop_source_sha256: desktopSource, cache_owner_sha256: ownerCode};
}
async function poll(operation, message, timeout = 120000) {
  const deadline = performance.now() + timeout;
  while (performance.now() < deadline) {
    const result = await operation();
    if (result) return result;
    await delay(100);
  }
  throw Error(message);
}
// Both an old BrowserWindow renderer and a new attached WebContentsView must
// match the actual Electron contents identity, visible bounds, and project label.
async function projectPage(application, project) {
  const bindings = new Map();
  return poll(async () => {
    const hosts = await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows().flatMap(window => [
      {kind: 'BrowserWindow', id: window.webContents.id, visible: window.isVisible(), bounds: window.getBounds()},
      ...window.contentView.children.map(view => ({kind: view.constructor.name, id: view.webContents?.id,
        visible: window.isVisible(), bounds: view.getBounds()})),
    ]));
    for (const page of application.context().pages()) {
      let id = bindings.get(page);
      if (!id) {
        const session = await application.context().newCDPSession(page);
        try {
          const {targetInfo} = await session.send('Target.getTargetInfo');
          id = await application.evaluate(({webContents}, targetId) => webContents.fromDevToolsTargetId(targetId)?.id, targetInfo.targetId);
          if (id) bindings.set(page, id);
        } finally { await session.detach(); }
      }
      const host = hosts.find(item => item.id === id && item.visible && item.bounds.width > 0 && item.bounds.height > 0);
      if (host && await page.evaluate(name => document.visibilityState === 'visible' && [...document.querySelectorAll('button[aria-current="page"]')]
        .some(el => el.getAttribute('aria-label') === `${name}, current project`), project.name).catch(() => false)) return {page, host};
    }
    return false;
  }, 'Owned scientific project renderer did not become visible', 45000);
}
async function snapshotCache(project) {
  const root = path.join(project, 'cache'), result = [];
  async function walk(folder) {
    for (const entry of await fs.readdir(folder, {withFileTypes: true}).catch(error => {
      if (error.code === 'ENOENT') return [];
      throw error;
    })) {
      if (entry.name.startsWith('.reader-') || entry.name.startsWith('.writer-')) continue;
      const file = path.join(folder, entry.name);
      assert.equal(entry.isSymbolicLink(), false, 'Owned derived cache must not contain links');
      if (entry.isDirectory()) await walk(file);
      else if (entry.isFile()) {
        const stat = await fs.stat(file);
        result.push({path: path.relative(root, file), bytes: stat.size, mtime_ms: stat.mtimeMs, sha256: await hashFile(file)});
      }
    }
  }
  await walk(root);
  return result.sort((a, b) => a.path.localeCompare(b.path));
}
(async () => {
  const old = await validateStage('old'), next = await validateStage('new');
  assert.notEqual(old.commit, next.commit, 'Upgrade requires distinct commits');
  const dependencies = createRequire(path.join(await fs.realpath(config['dependency-root']), 'package.json'));
  const {_electron} = dependencies('playwright'), executablePath = dependencies('electron');
  const output = path.resolve(config.output);
  await fs.mkdir(output, {recursive: false});
  const fixture = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'disco-retention-native-')));
  const home = path.join(fixture, 'home'), userData = path.join(home, 'state');
  await fs.mkdir(userData, {recursive: true});
  const env = {HOME: home, TMPDIR: fixture, XDG_CONFIG_HOME: userData, PATH: '/usr/bin:/bin:/usr/sbin:/sbin',
    LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8', PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1',
    RIEKE_PREFERENCES_DIR: path.join(home, '.rieke-os'), RIEKE_PROJECT_INDEX: path.join(userData, 'backend/preferences/project-index.json'),
    RIEKE_DESKTOP_USER_STATE: path.join(userData, 'backend'), RIEKE_MANAGED_PROJECTS_ROOT: path.join(home, 'projects'),
    RECORDING_WORKSPACE_ROOT: path.join(home, 'projects'), DISCO_STARTUP_DIAGNOSTIC: '1'};
  const receipt = {format: 'disco-owned-project-upgrade-v1', status: 'running', old, candidate: next, fixture,
    isolation: {home, userData, inherited_environment: false}, phases: [], requests: [], errors: [], observer_errors: [], cleanup: {},
    harness_sha256: await hashFile(__filename), limitations: [
      'One synthetic 63-epoch/two-cell owned project; no real-data scale claim.',
      'Fresh processes, unchanged owned HOME/project paths and existing caches; OS caches uncontrolled.',
      'Renderer HTTP observer attaches immediately after Playwright launch resolves; earlier bootstrap traffic may precede attachment.',
      'Main-process supervisor/authorization HTTP is outside the renderer ledger.',
      'First overview visibility can be a saved presentation; authoritative readiness is measured separately.',
    ]};
  receipt.harness_files = {};
  for (const file of ['desktop/e2e/project-upgrade.dev.cjs', 'desktop/e2e/retention-native-support.cjs', 'desktop/e2e/seed-retention-projects.py', 'desktop/e2e/seed-dual-response-fixture.py', 'tools/organization_e2e_fixture.py']) {
    receipt.harness_files[file] = await hashFile(path.join(__dirname, '../..', file));
  }
  const save = () => fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  const python = path.join(old.runtime, 'python/bin/python3.11');
  await run(python, ['-B', path.join(__dirname, 'seed-retention-projects.py'), path.join(old.runtime, 'application'), home, old.runtime], {env});
  const projects = JSON.parse(await fs.readFile(path.join(home, 'projects.json'))), project = projects[0];
  assert.ok((await fs.realpath(project.path)).startsWith(home + path.sep));
  receipt.project = project;
  const synthetic = path.join(home, 'synthetic');
  await run(python, ['-B', path.join(__dirname, 'seed-dual-response-fixture.py'), synthetic,
    path.join(old.runtime, 'python/lib/python3.11/site-packages/retinanalysis/utils/parse_data.py')], {env, timeout: 45000});
  const fixtureReceipt = JSON.parse(await fs.readFile(path.join(synthetic, 'dual-fixture-receipt.json')));
  const oracle = JSON.parse(await fs.readFile(path.join(synthetic, 'dual-oracle.json')));
  const input = path.join(synthetic, 'synthetic-dual.h5');
  assert.equal(fixtureReceipt.status, 'passed');
  assert.equal(await hashFile(input), fixtureReceipt.h5_sha256);
  receipt.synthetic = fixtureReceipt;
  async function importedMetadata() {
    const result = [];
    const root = path.join(project.path, 'imports');
    for (const entry of await fs.readdir(root, {withFileTypes: true})) {
      assert.equal(entry.isSymbolicLink(), false);
      if (!entry.isDirectory()) continue;
      for (const name of ['metadata.raw.json', 'metadata.catalog.json', 'epoch-index.json']) {
        const file = path.join(root, entry.name, name);
        if (await fs.stat(file).catch(error => { if (error.code === 'ENOENT') return null; throw error; })) {
          assert.equal((await fs.lstat(file)).isSymbolicLink(), false);
          result.push({path: file, sha256: await hashFile(file)});
        }
      }
    }
    assert.ok(result.some(row => row.path.endsWith('/metadata.raw.json')));
    return result.sort((a, b) => a.path.localeCompare(b.path));
  }
  let application, activePage, exited = true, canonical;
  const pending = [];
  async function api(endpoint) {
    return activePage.evaluate(async endpoint => {
      const response = await fetch(endpoint, {signal: AbortSignal.timeout(30000)});
      if (!response.ok) throw Error(`${endpoint}: ${response.status} ${await response.text()}`);
      return response.json();
    }, endpoint);
  }
  function observeContext(context, phase) {
    const rows = new WeakMap();
    const observedPages = new WeakSet();
    function pageErrors(page) {
      if (observedPages.has(page)) return;
      observedPages.add(page);
      page.on('pageerror', error => receipt.errors.push({phase: phase.name, at: performance.now(), error: String(error)}));
    }
    context.pages().forEach(pageErrors); context.on('page', pageErrors);
    context.on('request', request => {
      if (!new URL(request.url()).pathname.startsWith('/api/')) return;
      const row = {phase: phase.name, action: receipt.action, at: performance.now(), method: request.method(), url: request.url()};
      rows.set(request, row); receipt.requests.push(row);
    });
    context.on('response', response => {
      const row = rows.get(response.request());
      if (!row) return;
      row.response_at = performance.now(); row.status = response.status(); row.response_action = receipt.action;
      const pathname = new URL(response.url()).pathname;
      if (['/api/metadata/status', '/api/project/data-status', '/api/project/activate'].includes(pathname) || row.status >= 400) {
        pending.push((async () => {
          try {
            const body = await response.text();
            if ((response.headers()['content-type'] || '').includes('json')) row.body = JSON.parse(body);
            else row.body = body.slice(0, 500);
            if (row.status >= 400) {
              if (row.response_action === 'quit' && row.status === 503 && row.method === 'GET' && body === 'Desktop service is draining') row.classification = 'explicit-quit-draining';
              else row.classification = 'unexpected-http-response';
            }
          } catch (error) { receipt.observer_errors.push({phase: phase.name, url: row.url, error: String(error)}); }
        })());
      }
    });
    context.on('requestfinished', request => { const row = rows.get(request); if (row) { row.ended = performance.now(); row.elapsed_ms = row.ended - row.at; } });
    context.on('requestfailed', request => { const row = rows.get(request); if (row) { row.ended = performance.now(); row.elapsed_ms = row.ended - row.at; row.failure = request.failure()?.errorText; } });
  }
  async function science() {
    const overview = await api('/api/overview');
    assert.equal(overview.counts.epochs, 63); assert.equal(overview.counts.cells, 2); assert.equal(overview.protocols.length, 1);
    const protocol = overview.protocols[0].protocol_uuid;
    const page = await api(`/api/protocols/${protocol}/epochs?offset=0&limit=100&include_cells=true`);
    const epochs = page.epochs.map(row => row.epoch_uuid).sort();
    assert.deepEqual(epochs, oracle.epochs.map(row => row.uuid).sort());
    const cells = [...new Set(page.epochs.map(row => row.cell_uuid))].sort();
    assert.deepEqual(cells, [...new Set(oracle.epochs.map(row => row.cell_uuid))].sort());
    const value = {protocol_uuid: protocol, epochs, cells, counts: {epochs: 63, cells: 2},
      input_sha256: await hashFile(input), managed_sha256: await hashFile(receipt.managed_source), metadata: await importedMetadata()};
    assert.equal(value.input_sha256, fixtureReceipt.h5_sha256); assert.equal(value.managed_sha256, fixtureReceipt.h5_sha256);
    if (canonical) assert.deepEqual(value, canonical, 'Upgrade must preserve scientific membership and raw recordings');
    else canonical = value;
    return value;
  }
  async function quit(phase) {
    assert.ok(activePage.url().endsWith('#/overview'), 'Every measured process must finish on Project overview');
    await activePage.getByRole('region', {name: 'Project infographic', exact: true}).waitFor();
    receipt.action = 'quit'; phase.quit_started_at = performance.now(); await save();
    const exit = new Promise(resolve => application.process().once('exit', resolve));
    await activePage.evaluate(() => { void window.riekeDesktop.quit(); });
    let timer;
    try { assert.equal(await Promise.race([exit, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Ordinary owned Quit timed out')), 45000); })]), 0); }
    finally { clearTimeout(timer); }
    exited = true; phase.orderly_exit = true; phase.exit_at = performance.now();
    const owner = JSON.parse(await fs.readFile(path.join(project.path, 'database/native-owner.json')));
    assert.equal(owner.clean_shutdown, true);
    await Promise.all(pending); phase.cache_after_quit = await snapshotCache(project.path);
    phase.status = 'passed'; await save();
  }
  try {
    for (const [name, stage, populate] of [['old-populate', old, true], ['old-reopen', old, false], ['new-first-open', next, false], ['new-reopen', next, false]]) {
      const phase = {name, source_commit: stage.commit, status: 'running', cache_before: await snapshotCache(project.path)};
      receipt.phases.push(phase); receipt.action = 'launch'; await save();
      phase.launch_at = performance.now(); phase.started_at = new Date().toISOString();
      application = await _electron.launch({executablePath, args: [stage.desktop, `--user-data-dir=${userData}`], env,
        chromiumSandbox: true, bypassCSP: false, timeout: 45000});
      exited = false; phase.launch_resolved_at = performance.now();
      observeContext(application.context(), phase); phase.observer_attached_at = performance.now();
      captureNativeProcess(application, output, receipt, name);
      let markerBuffer = '';
      application.process().stdout?.on('data', bytes => {
        markerBuffer += bytes.toString();
        let end;
        while ((end = markerBuffer.indexOf('\n')) >= 0) {
          const line = markerBuffer.slice(0, end); markerBuffer = markerBuffer.slice(end + 1);
          if (line.startsWith('DISCO_SHELL_PAINTED=')) {
            try { (phase.shell_paint_markers ??= []).push({observed_at: performance.now(), value: JSON.parse(line.slice('DISCO_SHELL_PAINTED='.length))}); }
            catch (error) { receipt.observer_errors.push({phase: name, error: String(error)}); }
          }
        }
      });
      phase.runtime_identity = await application.evaluate(({app}) => ({home: process.env.HOME, userData: app.getPath('userData'),
        appPath: app.getAppPath(), packaged: app.isPackaged, pid: process.pid}));
      assert.equal(phase.runtime_identity.home, home); assert.equal(phase.runtime_identity.userData, userData);
      assert.equal(phase.runtime_identity.appPath, stage.desktop); assert.equal(phase.runtime_identity.packaged, false);
      if (populate) {
        const launcher = await poll(async () => {
          for (const page of application.context().pages()) if (await page.locator('.project-launcher').isVisible()) return page;
          return false;
        }, 'Owned launcher did not appear', 45000);
        receipt.action = 'open-project'; phase.open_click_at = performance.now();
        await launcher.getByRole('button', {name: `Open ${project.name}, ${project.path}`, exact: true}).click();
      }
      const bound = await projectPage(application, project); activePage = bound.page; phase.scientific_host = bound.host;
      activePage.setDefaultTimeout(20000); phase.project_shell_at = performance.now();
      receipt.action = 'first-overview';
      const usable = activePage.waitForFunction(() => {
        const node = document.querySelector('.infographic-overview');
        return !!node?.getClientRects().length && !node.closest('[inert]') && node.getAttribute('aria-busy') !== 'true';
      }, null, {timeout: 120000}).then(() => { phase.overview_usable_at = performance.now(); });
      const visible = activePage.getByRole('region', {name: 'Project infographic', exact: true}).waitFor({timeout: 120000})
        .then(() => { phase.overview_first_visible_at = performance.now(); });
      const dataReady = poll(async () => {
        const status = await api('/api/project/data-status');
        if (status.status === 'failed') throw Error(JSON.stringify(status));
        return status.status === 'ready';
      }, 'Project data did not become ready').then(() => { phase.project_data_ready_at = performance.now(); });
      await Promise.all([visible, usable, dataReady]); phase.metadata_ready = await api('/api/metadata/status');
      assert.equal(phase.metadata_ready.status, 'ready');
      await prepareInitialPresentation(activePage, receipt);
      if (populate) {
        receipt.action = 'import';
        await activePage.getByRole('button', {name: 'Data stores', exact: true}).click();
        await activePage.getByRole('button', {name: 'Import H5s', exact: true}).click();
        const chooser = activePage.waitForEvent('filechooser');
        await activePage.getByRole('button', {name: 'Browse H5 files', exact: true}).click();
        await (await chooser).setFiles(input);
        const job = await poll(async () => {
          const jobs = (await api('/api/jobs')).jobs; assert.ok(jobs.length <= 1);
          const job = jobs[0]; if (!job) return false;
          if (['failed', 'interrupted', 'duplicate', 'complete_with_warnings'].includes(job.status)) throw Error(`Import ${job.status}`);
          return job.status === 'complete' ? job : false;
        }, 'Owned import did not complete');
        assert.equal(job.source_sha256, fixtureReceipt.h5_sha256); assert.equal(job.recording_storage?.verified, true);
        receipt.managed_source = await fs.realpath(job.recording_storage.path);
        assert.ok(receipt.managed_source.startsWith(home + path.sep));
        const review = activePage.getByRole('dialog', {name: 'Review imported data', exact: true});
        await review.waitFor({timeout: 30000}); await review.getByRole('button', {name: 'Done reviewing', exact: true}).click();
        await activePage.getByRole('button', {name: 'Project overview', exact: true}).click();
        await activePage.getByRole('region', {name: 'Project infographic', exact: true}).waitFor();
      }
      receipt.action = 'verify-authoritative';
      phase.science = await science(); phase.metadata_after = await api('/api/metadata/status');
      phase.authoritative_verified_at = performance.now();
      phase.launch_to_shell_ms = phase.project_shell_at - phase.launch_at;
      phase.launch_to_overview_ms = phase.overview_first_visible_at - phase.launch_at;
      phase.launch_to_overview_usable_ms = phase.overview_usable_at - phase.launch_at;
      phase.launch_to_data_ready_ms = phase.project_data_ready_at - phase.launch_at;
      phase.cache_after_ready = await snapshotCache(project.path);
      await activePage.screenshot({path: path.join(output, `${name}.png`)});
      await quit(phase);
    }
    for (const stage of [old, next]) {
      assert.equal(await git(stage.source, 'rev-parse', 'HEAD'), stage.commit);
      assert.equal(await git(stage.source, 'status', '--porcelain'), '');
    }
    for (const [file, expected] of Object.entries(receipt.harness_files)) assert.equal(await hashFile(path.join(__dirname, '../..', file)), expected);
    assert.deepEqual(receipt.errors, []); assert.deepEqual(receipt.observer_errors, []);
    assert.deepEqual(receipt.requests.filter(row => row.classification === 'unexpected-http-response'), []);
    receipt.status = 'passed'; await save();
  } catch (error) {
    receipt.status = 'failed'; receipt.error = String(error);
    if (activePage) await activePage.screenshot({path: path.join(output, 'failure.png')}).catch(() => {});
    await save(); throw error;
  } finally {
    if (application && !exited) await closeOwned(application, userData, receipt);
    await save();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
