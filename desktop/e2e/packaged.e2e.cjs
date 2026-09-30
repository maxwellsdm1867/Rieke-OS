'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {createHash, randomUUID} = require('node:crypto');
const {chromium} = require('playwright');
const {createFixture, launch, gracefulQuit, ownedControl, run} = require('./helpers.cjs');
const {verifyResources} = require('../updater-validation.cjs');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const output = path.resolve(__dirname, '../../docs/dev/desktop-ui-e2e');
let fixture, application, page, recoveredBrowser, deliberateCrash = false;
const receipt = {format: 'rieke-packaged-ui-e2e', version: 1, signed_qualification: false, checks: [], failures: [],
  method: 'Playwright Electron 1.63.0; exact packaged app clone; isolated HOME and standard --user-data-dir; sandbox enabled and CSP intact; native chooser return values stubbed only'};
receipt.run_id = randomUUID().slice(0, 8);
const projectName = 'Electron lifecycle fixture ' + receipt.run_id;
process.on('uncaughtException', error => {
  // Pinned Playwright throws this client assertion when Electron recovers the
  // same target after forcefullyCrashRenderer. The app is inspected through
  // its actual owned WebContents API during that fault, instead of its stale
  // Playwright Page session. Other unexpected exceptions still fail the run.
  if (deliberateCrash && error.message === 'Target crashed') {receipt.playwright_crash_session_warnings = (receipt.playwright_crash_session_warnings || 0) + 1; return;}
  throw error;
});
async function chooseTestProfile() {
  const dialog = page.getByRole('dialog', {name: 'Tag author', exact: true});
  const visible = await dialog.waitFor({state: 'visible', timeout: 3000}).then(() => true).catch(() => false);
  if (visible) {
    const existing = dialog.getByRole('button', {name: 'Electron E2E', exact: true});
    if (await existing.count()) await existing.first().click();
    else {await dialog.getByRole('textbox').fill('Electron E2E'); await dialog.getByRole('button', {name: 'Create profile', exact: true}).click();}
    await dialog.waitFor({state: 'hidden'});
  }
}
async function chooseNewProjectFolder(form, name) {
  const selected = form.locator('#new-project-directory');
  assert.equal(await selected.getAttribute('readonly'), '');
  await application.evaluate(({dialog}, directory) => {dialog.showOpenDialog = async () => ({canceled:false,filePaths:[directory]});}, fixture.projects);
  await form.getByRole('button', {name:'Browse: New project folder',exact:true}).click();
  const picker = page.getByRole('dialog', {name:'New project folder',exact:true});
  await picker.getByRole('checkbox', {name:'Create a new folder inside this location'}).check();
  await picker.getByRole('textbox', {name:'New folder name',exact:true}).fill(name);
  await picker.getByRole('button', {name:'Use new folder',exact:true}).click();
  await picker.waitFor({state:'hidden'});
  assert.equal(await selected.inputValue(), path.join(fixture.projects,name));
}
async function verifyHeaderIcon(selector, headerSelector, screenName) {
  const measurements = [];
  try {
    for (const width of [1440, 960]) {
      await application.evaluate(({BrowserWindow}, width) => BrowserWindow.getAllWindows()[0].setContentSize(width, 900), width);
      await page.waitForFunction(({selector, width}) => {
        const icon = document.querySelector(selector);
        return window.innerWidth === width && icon?.complete && icon.naturalWidth > 0;
      }, {selector, width}, {timeout: 15000});
      const geometry = await page.evaluate(({selector, headerSelector}) => {
        const icon = document.querySelector(selector), header = document.querySelector(headerSelector);
        const bounds = node => {const r = node.getBoundingClientRect(); return {left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width, height:r.height};};
        const others = [...header.children].filter(node => node !== icon && !node.classList.contains('spacer') && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden')
          .map(node => ({tag: node.tagName, className: node.className, rect: bounds(node)})).filter(node => node.rect.width > 0 && node.rect.height > 0);
        return {viewport: window.innerWidth, source: new URL(icon.currentSrc).pathname, naturalWidth:icon.naturalWidth, naturalHeight:icon.naturalHeight,
          icon:bounds(icon), header:bounds(header), others};
      }, {selector, headerSelector});
      await page.screenshot({path: path.join(output, `${screenName}-${width}.png`)});
      assert.equal(geometry.source, '/rieke-os-icon.png'); assert.ok(geometry.naturalWidth > 0);
      const expectedSize = selector === '.onboarding-app-icon' ? 48 : 32;
      assert.equal(geometry.icon.width, expectedSize); assert.equal(geometry.icon.height, expectedSize);
      assert.ok(geometry.icon.left >= geometry.header.left && geometry.icon.right <= geometry.header.right + 1 && geometry.icon.right <= width + 1,
        'App icon must remain inside its header and viewport: ' + JSON.stringify(geometry));
      assert.ok(geometry.icon.left > (geometry.header.left + geometry.header.right) / 2, 'App icon must be on the right');
      for (const sibling of geometry.others) {
        const r = sibling.rect, icon = geometry.icon;
        assert.ok(!(r.left < icon.right - 1 && r.right > icon.left + 1 && r.top < icon.bottom - 1 && r.bottom > icon.top + 1),
          'App icon overlaps an adjacent header control: ' + JSON.stringify({width, sibling, icon}));
      }
      measurements.push({viewport: width, naturalWidth: geometry.naturalWidth, icon: geometry.icon, header: geometry.header});
    }
  } finally {await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setContentSize(1440, 900));}
  return {actual_packaged_icon_loaded: true, header_right: true, no_icon_overlap: true, native_window_widths: measurements};
}
async function writeReceipt() { await fs.mkdir(output, {recursive: true}); await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n'); }
async function check(name, fn) {
  const start = Date.now();
  try { const evidence = await fn(); receipt.checks.push({name, passed: true, elapsed_ms: Date.now() - start, ...(evidence ? {evidence} : {})}); console.log('PASS ' + name); }
  catch (error) { receipt.failures.push({name, message: error.message}); console.error('FAIL ' + name + ': ' + error.message); await writeReceipt(); throw error; }
  await writeReceipt();
}
async function start(heading = 'Your projects') {
  const launched = await launch(fixture); ({application, page} = launched);
  page.on('pageerror', error => receipt.failures.push({name: 'renderer-pageerror', message: error.message}));
  await page.getByRole('heading', {name: heading, exact: true}).waitFor({timeout: 90000});
  return launched.actual;
}
async function main() {
  fixture = await createFixture(); console.log('Isolated fixture: ' + fixture.root);
  const runtime = path.join(fixture.bundle, 'Contents/Resources/runtime');
  const bytes = await fs.readFile(path.join(runtime, 'runtime-manifest.json')); const manifest = JSON.parse(bytes);
  receipt.manifest_sha256 = createHash('sha256').update(bytes).digest('hex'); receipt.application_version = manifest.application_version;
  receipt.app_asar_sha256 = createHash('sha256').update(await fs.readFile(path.join(fixture.bundle, 'Contents/Resources/app.asar'))).digest('hex');
  receipt.app_icon_sha256 = createHash('sha256').update(await fs.readFile(path.join(runtime, 'frontend/rieke-os-icon.png'))).digest('hex');
  assert.equal(receipt.app_icon_sha256, '614f7bcd44ced5ff8cf76f648e7a4e23ec45bee3236ea5ad17f59e3a1e173483', 'Packaged renderer must use the existing app icon');
  await check('cold packaged launcher and state isolation', async () => {const actual = await start(); assert.equal(actual.packaged, true); assert.equal(actual.electronVersion, '44.5.0'); return {isolated_user_state: true, packaged: true, electron_version: actual.electronVersion};});
  await check('launcher actual app icon loads at upper right at normal and narrow native widths',
    () => verifyHeaderIcon('.onboarding-app-icon', '.project-onboarding>header', 'launcher-icon'));
  await check('renderer isolation, sandbox and CSP', async () => {
    const settings = await application.evaluate(({BrowserWindow}) => {
      const prefs = BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();
      return {contextIsolation: prefs.contextIsolation, sandbox: prefs.sandbox, nodeIntegration: prefs.nodeIntegration, webSecurity: prefs.webSecurity};
    });
    assert.deepEqual(settings, {contextIsolation: true, sandbox: true, nodeIntegration: false, webSecurity: true});
    assert.deepEqual(await page.evaluate(() => ({require: typeof require, process: typeof process, rawIpc: typeof window.riekeDesktop.ipcRenderer})), {require: 'undefined', process: 'undefined', rawIpc: 'undefined'});
    const inlineRan = await page.evaluate(() => { const script = document.createElement('script'); script.textContent = 'window.__inline_e2e=true'; document.body.append(script); return window.__inline_e2e === true; });
    assert.equal(inlineRan, false); return settings;
  });
  await check('testing updates preserve explicit download, restart and bootstrap boundaries', async () => {
    const status = await page.evaluate(() => window.riekeDesktop.status());
    if(status.channel==='unsigned-testing') {
      assert.equal(status.manual_updates,true);
      assert.ok(!['Downloading','Validating','Ready','Draining','Installing'].includes(status.state), 'Background checks must never download or install');
      const result=await page.evaluate(()=>window.riekeDesktop.restartToUpdate());assert.equal(result.ready,false);
    } else assert.equal(status.state, 'Deferred');
    const message = await page.evaluate(async () => { try { await window.riekeDesktop.installAndOpen(); return ''; } catch (error) { return error.message; } });
    assert.match(message, /before backend startup/);
  });
  await check('malformed draft IPC and external release URLs reject', async () => {
    const results = await page.evaluate(async () => {
      const actions = [() => window.riekeDesktop.saveDraft({projectId: '../../escape', value: {}}),
        () => window.riekeDesktop.saveDraft({projectId: 'launcher', value: {}, path: '/outside'}),
        () => window.riekeDesktop.loadDraft('../../escape'), () => window.riekeDesktop.openReleaseNotes('https://evil.example/'),
        () => window.riekeDesktop.acknowledgeDrafts('foreign-request', {ok: true})];
      return Promise.all(actions.map(async action => {try {await action(); return false;} catch {return true;}}));
    }); assert.deepEqual(results, [true, true, true, true, true]);
  });
  await check('renderer cannot drain, stop or source-update services', async () => {
    const statuses = await page.evaluate(async () => Promise.all(['/api/desktop/drain', '/api/desktop/stop', '/api/desktop/authorize-project'].map(async url =>
      (await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Workspace-Request': '1'}, body: '{}'})).status)));
    assert.deepEqual(statuses, [403, 403, 403]);
    const sourceStatuses = await page.evaluate(async () => Promise.all(['/api/app/updates', '/api/app/updates/check', '/api/app/updates/stage', '/api/app/updates/download']
      .map(async url => (await fetch(url)).status)));
    assert.deepEqual(sourceStatuses, [409, 409, 409, 409]);
  });
  await check('scientific project creation cannot write into packaged resources or redirected parents', async () => {
    const direct = path.join(fixture.bundle, 'Contents/Resources/forbidden-project');
    const alias = path.join(fixture.root, 'resource-parent-alias-' + receipt.run_id);
    await fs.symlink(path.join(fixture.bundle, 'Contents/Resources'), alias);
    for (const directory of [direct, path.join(alias, 'forbidden-project'),
      path.join(fixture.bundle, 'forbidden-project'), path.join(fixture.bundle, 'Contents/MacOS/forbidden-project')]) {
      const result = await page.evaluate(async project_directory => {
        const response = await fetch('/api/projects', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Workspace-Request': '1'}, body: JSON.stringify({name: 'Must not be created', project_directory})});
        return {status: response.status, value: await response.json()};
      }, directory);
      assert.equal(result.status, 400); assert.ok(result.value.error);
      await assert.rejects(fs.stat(directory), {code: 'ENOENT'});
    }
  });
  await check('foreign navigation, popups and cross-origin requests blocked', async () => {
    let visits = 0; const server = http.createServer((_request, response) => {visits++; response.end('foreign');});
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const target = `http://127.0.0.1:${server.address().port}/`;
    const previous = page.url();
    try {
      await page.evaluate(url => {window.open(url); window.location.assign(url);}, target); await delay(600);
      assert.equal(page.url(), previous); assert.equal(application.windows().length, 1); assert.equal(visits, 0);
      const blocked = await page.evaluate(async url => {try {await fetch(url); return false;} catch {return true;}}, target); assert.equal(blocked, true);
      await page.evaluate(url => {const frame = document.createElement('iframe'); frame.src = url; document.body.append(frame);}, target); await delay(100); assert.equal(visits, 0);
      await page.evaluate(() => document.querySelectorAll('iframe').forEach(frame => frame.remove()));
      // Chromium reports the deliberately denied navigation to CDP before
      // Electron cancels it. Reset this test-created pending-navigation state.
      await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].webContents.reload());
      await page.getByRole('heading', {name: 'Your projects', exact: true}).waitFor({timeout: 15000});
    } finally { await new Promise(resolve => server.close(resolve)); }
  });
  await check('foreign renderer IPC cannot access desktop controls', async () => {
    const preload = path.join(fixture.root, 'foreign-preload.cjs');
    await fs.writeFile(preload, "const {contextBridge,ipcRenderer}=require('electron');contextBridge.exposeInMainWorld('foreignProbe',{request:()=>ipcRenderer.invoke('desktop:status').then(()=>({accepted:true}),e=>({accepted:false,message:e.message}))});");
    const result = await application.evaluate(async ({BrowserWindow}, preload) => {
      const foreign = new BrowserWindow({show: false, webPreferences: {sandbox: true, contextIsolation: true, nodeIntegration: false, preload}});
      try {await foreign.loadURL('data:text/html,<p>Foreign test renderer</p>'); return await foreign.webContents.executeJavaScript('window.foreignProbe.request()');}
      finally {foreign.destroy();}
    }, preload);
    assert.equal(result.accepted, false); assert.match(result.message, /Unauthorized desktop frame/);
  });
  await check('native project-folder chooser uses typed result', async () => {
    await fs.mkdir(fixture.projects, {recursive: true});
    await application.evaluate(({dialog}, directory) => {dialog.showOpenDialog = async () => ({canceled: false, filePaths: [directory]});}, fixture.projects);
    assert.equal(await page.evaluate(() => window.riekeDesktop.chooseProjectFolder()), fixture.projects);
    await application.evaluate(({dialog}) => {dialog.showOpenDialog = async () => ({canceled: true, filePaths: []});});
    assert.equal(await page.evaluate(() => window.riekeDesktop.chooseProjectFolder()), null);
  });
  await check('duplicate launch preserves one owner and existing backend', async () => {
    const before = await ownedControl(fixture, 'health');
    const child = spawn(fixture.executable, [`--user-data-dir=${fixture.userData}`], {env: {...process.env, HOME: fixture.home, TMPDIR: fixture.root}, stdio: 'ignore'});
    const code = await Promise.race([new Promise(resolve => child.once('exit', resolve)), delay(10000).then(() => {throw new Error('Duplicate app did not exit');})]);
    assert.equal(code, 0); assert.equal((await ownedControl(fixture, 'health')).pid, before.pid); assert.equal(application.windows().length, 1);
  });
  await check('corrupted saved view is visible, blocks overwrite and supports preserved quit or explicit reset', async () => {
    await gracefulQuit(application, page); application = null; page = null;
    const filename = path.join(fixture.userData, 'drafts', 'launcher.json');
    const valid = JSON.parse(await fs.readFile(filename, 'utf8'));
    const corrupted = '{intentional unreadable saved-view fixture'; await fs.writeFile(filename, corrupted);
    await start('Saved view needs recovery');
    assert.ok((await page.getByRole('alert').innerText()).includes('saved view'));
    await delay(3300); assert.equal(await fs.readFile(filename, 'utf8'), corrupted);
    assert.equal(await page.evaluate(async value => {try {await window.riekeDesktop.saveDraft({projectId: 'launcher', value}); return false;} catch {return true;}}, valid), true);
    assert.equal((await page.evaluate(() => window.riekeDesktop.quit())).ready, false);
    await page.screenshot({path: path.join(output, 'corrupted-view-recovery.png')});
    const exited = new Promise(resolve => application.process().once('exit', resolve));
    await page.getByRole('button', {name: 'Keep saved view and quit', exact: true}).click();
    assert.equal(await exited, 0); application = null; page = null;
    assert.equal(await fs.readFile(filename, 'utf8'), corrupted);
    await start('Saved view needs recovery');
    await page.getByRole('button', {name: 'Start with a new view', exact: true}).click();
    await page.getByRole('heading', {name: 'Your projects', exact: true}).waitFor();
    const backups = (await fs.readdir(path.dirname(filename))).filter(name => name.startsWith('launcher.corrupt-'));
    assert.ok((await Promise.all(backups.map(name => fs.readFile(path.join(path.dirname(filename), name), 'utf8')))).includes(corrupted));
    assert.equal(await page.evaluate(async () => {try {await window.riekeDesktop.resetDraft('launcher'); return false;} catch {return true;}}), true);
    return {visible_recovery: true, corrupt_bytes_preserved: true, ordinary_quit_deferred: true, preserved_quit_acknowledged: true, explicit_reset_preserved_backup: true};
  });
  await check('create and open project through actual React interface', async () => {
    await page.getByRole('button', {name: /Start a brand new project/}).click();
    const form = page.locator('.onboarding-create-form');
    await form.getByRole('textbox').nth(0).fill(projectName);
    const folderBeforeCancel=await form.locator('#new-project-directory').inputValue();
    await application.evaluate(({dialog})=>{dialog.showOpenDialog=async()=>({canceled:true,filePaths:[]});});
    await form.getByRole('button',{name:'Browse: New project folder',exact:true}).click();
    await form.getByRole('button',{name:'Browse: New project folder',exact:true}).waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('.folder-path-control button')?.disabled);
    assert.equal(await form.locator('#new-project-directory').inputValue(),folderBeforeCancel);
    assert.equal(await page.getByRole('dialog',{name:'New project folder',exact:true}).count(),0);
    assert.equal(await fs.stat(path.join(fixture.projects,receipt.run_id)).then(()=>true,()=>false),false);
    assert.equal(await form.getByRole('button',{name:'Create & open',exact:true}).isDisabled(),true);
    await chooseNewProjectFolder(form, receipt.run_id);
    await page.getByRole('button', {name: 'Create & open', exact: true}).click();
    await page.getByRole('button', {name: 'Project overview', exact: true}).waitFor({timeout: 90000});
    assert.match(await page.title(), /Electron lifecycle fixture/);
    const project = await page.evaluate(() => fetch('/api/projects').then(response => response.json()));
    receipt.test_project_uuid = project.current_project_uuid; assert.ok(project.current_project_uuid);
    await chooseTestProfile();
    await page.screenshot({path: path.join(output, 'project.png')});
  });
  await check('workspace actual app icon loads at upper right without overlap at normal and narrow native widths',
    () => verifyHeaderIcon('.header-app-icon', '.app-header', 'workspace-icon'));
  await check('rapid warm project navigation persists the current view before document replacement', async () => {
    const secondName = projectName + ' second';
    await page.locator('.sidebar').getByRole('button', {name: /Start a brand new project/}).click();
    const form = page.locator('.onboarding-create-form'); await form.getByRole('textbox').nth(0).fill(secondName);
    await chooseNewProjectFolder(form, receipt.run_id + '-second');
    await page.getByRole('button', {name: 'Create & open', exact: true}).click();
    await page.waitForFunction(expected => document.title.startsWith(expected), secondName, {timeout: 90000}); await chooseTestProfile();
    receipt.second_project_uuid = (await page.evaluate(() => fetch('/api/projects').then(response => response.json()))).current_project_uuid;
    assert.ok(receipt.second_project_uuid);
    await page.getByRole('navigation', {name: 'Research projects'}).getByRole('button', {name: projectName, exact: true}).click();
    await page.waitForFunction(expected => document.title.startsWith(expected) && !document.title.includes(' second'), projectName, {timeout: 30000});
    const navigationStart = Date.now();
    await page.getByRole('button', {name: 'Activity & logs', exact: true}).click();
    await page.getByRole('navigation', {name: 'Research projects'}).getByRole('button', {name: secondName, exact: true}).click();
    await page.waitForFunction(expected => document.title.startsWith(expected), secondName, {timeout: 30000});
    const saved = JSON.parse(await fs.readFile(path.join(fixture.userData, 'drafts', receipt.test_project_uuid + '.json')));
    assert.equal(saved.value.route.page, 'activity');
    await page.getByRole('navigation', {name: 'Research projects'}).getByRole('button', {name: projectName, exact: true}).click();
    await page.waitForFunction(expected => document.title.startsWith(expected) && !document.title.includes(' second'), projectName, {timeout: 30000});
    await page.waitForFunction(() => [...document.querySelectorAll('.nav-item.active')].some(item => item.textContent.includes('Activity & logs')));
    return {warm_document_handoff: true, route_persisted: 'activity', elapsed_ms: Date.now() - navigationStart};
  });
  await check('missing saved view opens normally without corrupt-draft recovery', async () => {
    const missing = path.join(fixture.userData, 'drafts', receipt.second_project_uuid + '.json');
    await fs.unlink(missing);
    const secondName = projectName + ' second';
    await page.getByRole('navigation', {name: 'Research projects'}).getByRole('button', {name: secondName, exact: true}).click();
    await page.waitForFunction(expected => document.title.startsWith(expected), secondName, {timeout: 30000});
    await page.waitForFunction(() => [...document.querySelectorAll('.nav-item.active')].some(item => item.textContent.includes('Project overview')));
    assert.equal(await page.getByRole('heading', {name: 'Saved view needs recovery', exact: true}).count(), 0);
    await page.getByRole('navigation', {name: 'Research projects'}).getByRole('button', {name: projectName, exact: true}).click();
    await page.waitForFunction(expected => document.title.startsWith(expected) && !document.title.includes(' second'), projectName, {timeout: 30000});
    return {missing_draft_treated_as_new_view: true};
  });
  if (process.env.RIEKE_E2E_H5) await check('actual active import defers close without stopping any writer', async () => {
    const copied = path.join(fixture.root, 'scientific-fixture.h5'); await fs.copyFile(process.env.RIEKE_E2E_H5, copied);
    const job = await page.evaluate(async source_path => {
      const response = await fetch('/api/imports', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Workspace-Request': '1'}, body: JSON.stringify({source_path})});
      const value = await response.json(); if (response.status !== 202) throw new Error(value.error || 'Import was not accepted'); return value;
    }, copied);
    const before = await ownedControl(fixture, 'health');
    let status;
    for (let index = 0; index < 80; index++) {
      status = await page.evaluate(async uuid => (await fetch('/api/jobs').then(response => response.json())).jobs.find(job => job.job_uuid === uuid), job.job_uuid);
      if (status && !['queued', 'waiting'].includes(status.status)) break;
      await delay(250);
    }
    assert.ok(status && !['complete', 'completed', 'failed', 'cancelled'].includes(status.status));
    const result = await page.evaluate(() => window.riekeDesktop.quit()); assert.equal(result.ready, false);
    assert.equal((await ownedControl(fixture, 'health')).pid, before.pid); assert.equal(page.isClosed(), false);
    await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].close());
    await delay(500);
    assert.equal(page.isClosed(), false); assert.equal((await ownedControl(fixture, 'health')).pid, before.pid);
    for (let index = 0; index < 240; index++) {
      status = await page.evaluate(async uuid => (await fetch('/api/jobs').then(response => response.json())).jobs.find(job => job.job_uuid === uuid), job.job_uuid);
      if (['complete', 'completed', 'failed', 'cancelled'].includes(status?.status)) break;
      await delay(500);
    }
    assert.ok(['complete', 'completed'].includes(status?.status), 'Import must finish successfully before test shutdown');
    // Completion is observed by the UI on its own polling cycle. Close its
    // automatic review explicitly after it appears, rather than sending Escape
    // before the dialog has been mounted.
    const review=page.getByRole('dialog',{name:'Review imported data',exact:true});
    if(await review.waitFor({state:'visible',timeout:10000}).then(()=>true,()=>false)) {
      await review.getByRole('button',{name:'Close import review',exact:true}).click();
      await review.waitFor({state:'hidden'});
    }
    await page.keyboard.press('Escape');
    return {real_import: true, bridge_quit_deferred: true, native_window_close_deferred: true, root_pid_preserved: true, completed: true};
  });
  if(process.env.RIEKE_E2E_H5) await check('real protocol inspection uses combined epoch and cell pages with registered metadata and a plotted response',async()=>{
    await page.keyboard.press('Escape');
    const overview=await page.evaluate(()=>fetch('/api/overview').then(response=>response.json()));
    const protocol=overview.protocols?.[0];assert.ok(protocol?.protocol_uuid,'Imported protocols must be available');
    let combined=null,inspectedProtocolUuid=null;const pending=[];
    const observe=response=>{
      const url=new URL(response.url());
      if(/^\/api\/protocols\/[^/]+\/epochs$/.test(url.pathname)&&url.searchParams.get('include_cells')==='true'&&response.status()===200)
        pending.push(response.json().then(value=>{combined=value;inspectedProtocolUuid=url.pathname.split('/')[3];}));
    };
    page.on('response',observe);
    try{
      await page.getByRole('button',{name:'Project overview',exact:true}).click();
      await page.locator('.ov-protocol-row:visible').first().click({timeout:90000});
      await page.getByRole('button',{name:'Open inspection',exact:true}).click();
      const tree=page.locator('.inspection-cell-tree');await tree.waitFor({state:'visible',timeout:90000});
      await tree.locator('.cell-tree-date>summary').first().click();
      await tree.locator('.cell-tree-cell>summary').first().click();
      await tree.getByRole('button',{name:/^Inspect .* epoch 1$/}).first().click();
      await page.getByRole('region',{name:'Recorded response viewer',exact:true}).waitFor({timeout:90000});
      await page.waitForFunction(()=>{const canvas=document.querySelector('.tv-base');return canvas?.width>0&&!document.querySelector('.tv-loading')&&!document.querySelector('.tv-error');},undefined,{timeout:90000});
      const details=page.getByRole('button',{name:'Details',exact:true});
      if(await details.getAttribute('aria-pressed')!=='true')await details.click();
      await page.getByRole('heading',{name:'Epoch details',exact:true}).waitFor();
      await page.getByRole('button',{name:'All fields',exact:true}).click();
      assert.ok(await page.locator('.metadata-panel-section').count()>0);
      const fields=await page.evaluate(()=>fetch('/api/metadata/fields').then(response=>response.json()));
      assert.ok(Array.isArray(fields.fields)&&fields.fields.length>0,'Registered metadata fields must match the bundled frontend');
      await Promise.all(pending);assert.ok(combined?.epochs?.length>0&&combined?.cells?.length>0,'Actual UI must receive combined epochs and cells');
      assert.ok(combined.query_revision);assert.ok(Number.isSafeInteger(combined.expected_binding_version));
      assert.ok(!await page.getByText('Predicate field catalog unavailable.',{exact:false}).count());
      return {real_epoch_inspection:true,trace_canvas_loaded:true,combined_epoch_count:combined.epochs.length,combined_cell_count:combined.cells.length,
        metadata_field_count:fields.fields.length,metadata_panel_visible:true,protocol_uuid:inspectedProtocolUuid};
    }finally{page.off('response',observe);}
  });
  await check('durable real renderer draft survives orderly close and cold restart', async () => {
    await page.getByRole('button', {name: 'Project files', exact: true}).click();
    await gracefulQuit(application, page); application = null; page = null;
    const saved = JSON.parse(await fs.readFile(path.join(fixture.userData, 'drafts', receipt.test_project_uuid + '.json')));
    assert.equal(saved.format, 'rieke-renderer-draft'); assert.equal(saved.value.route.page, 'files');
    await start(); await page.getByRole('button', {name: new RegExp('^Open ' + projectName + ',')}).click();
    await page.getByRole('button', {name: 'Project files', exact: true}).waitFor({timeout: 90000});
    await chooseTestProfile();
    await page.waitForFunction(() => [...document.querySelectorAll('.nav-item.active')].some(item => item.textContent.includes('Project files')), undefined, {timeout: 10000});
  });
  await check('project draft identity mismatch requires visible preserved recovery', async () => {
    await gracefulQuit(application, page); application = null; page = null;
    const filename = path.join(fixture.userData, 'drafts', receipt.test_project_uuid + '.json');
    const saved = JSON.parse(await fs.readFile(filename, 'utf8'));
    const corrupted = JSON.stringify({...saved, projectId: 'launcher'}); await fs.writeFile(filename, corrupted);
    await start(); await page.getByRole('button', {name: new RegExp('^Open ' + projectName + ',')}).click();
    await page.getByRole('heading', {name: 'Saved view needs recovery', exact: true}).waitFor({timeout: 90000});
    assert.equal((await page.evaluate(() => window.riekeDesktop.quit())).ready, false);
    assert.equal(await fs.readFile(filename, 'utf8'), corrupted);
    await page.getByRole('button', {name: 'Start with a new view', exact: true}).click();
    await page.getByRole('button', {name: 'Project overview', exact: true}).waitFor({timeout: 30000});
    await chooseTestProfile();
    const backups = (await fs.readdir(path.dirname(filename))).filter(name => name.startsWith(receipt.test_project_uuid + '.corrupt-'));
    assert.ok((await Promise.all(backups.map(name => fs.readFile(path.join(path.dirname(filename), name), 'utf8')))).includes(corrupted));
    return {project_identity_validated: true, mismatched_bytes_preserved: true, explicit_reset: true,
      preserved_sha256: createHash('sha256').update(corrupted).digest('hex')};
  });
  await check('renderer crash enters recovery, preserves backend and requires recovery before quit', async () => {
    const before = await ownedControl(fixture, 'health');
    deliberateCrash = true;
    receipt.crash_test_method = 'Actual renderer crash; original stale Playwright target replaced by fresh CDP connection to the same isolated app; real recovery UI, bridge and backend health assertions';
    await application.evaluate(({BrowserWindow}) => {const target = BrowserWindow.getAllWindows()[0]; setTimeout(() => target.webContents.forcefullyCrashRenderer(), 100);});
    await delay(300);
    // Attach a fresh software-test session to this isolated app's existing CDP
    // endpoint. Pinned Playwright cannot revive its original crashed Page.
    const port = Number((await fs.readFile(path.join(fixture.userData, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);
    recoveredBrowser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
    page = recoveredBrowser.contexts()[0].pages()[0];
    page.on('pageerror', error => receipt.failures.push({name: 'recovered-renderer-pageerror', message: error.message}));
    await page.getByRole('heading', {name: 'Rieke OS recovery', exact: true}).waitFor({timeout: 15000});
    assert.equal((await ownedControl(fixture, 'health')).pid, before.pid);
    const result = await page.evaluate(() => window.riekeDesktop.quit()); assert.equal(result.ready, false);
    await page.screenshot({path: path.join(output, 'renderer-recovery.png')});
    await page.getByRole('button', {name: 'Retry startup', exact: true}).click();
    await page.getByRole('heading', {name: 'Your projects', exact: true}).waitFor({timeout: 30000});
    assert.equal((await ownedControl(fixture, 'health')).pid, before.pid);
    deliberateCrash = false;
  });
  await check('final orderly quit and packaged resource immutability', async () => {
    await gracefulQuit(application, page); application = null; page = null;
    await assert.rejects(fs.stat(path.join(fixture.userData, 'desktop-service.json')), {code: 'ENOENT'});
    await verifyResources(runtime, manifest.resources);
    assert.equal(createHash('sha256').update(await fs.readFile(path.join(runtime, 'runtime-manifest.json'))).digest('hex'), receipt.manifest_sha256);
    assert.equal(receipt.failures.length, 0, 'Unexpected renderer errors: ' + receipt.failures.map(item => item.message).join('; '));
  });
  receipt.completed = true; await writeReceipt(); console.log('Packaged UI E2E completed');
}
main().catch(async error => {
  process.exitCode = 1; await writeReceipt();
  if (page) await page.screenshot({path: path.join(output, 'failure.png')}).catch(() => {});
  if (application && page) { try {await gracefulQuit(application, page);} catch {console.error('Isolated app retained because orderly closure was not acknowledged.');} }
  console.error(error.message);
});
