'use strict';
// Actual renderer -> current Flask -> native MySQL, on the owned fixture only.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.DISCO_E2E_PLAYWRIGHT || 'playwright');

async function main() {
  const serverPath = process.argv[2];
  const server = JSON.parse(await fs.readFile(serverPath));
  const state = await fs.realpath(server.state);
  assert.match(path.basename(state), /^disco-workbench-replacement-e2e-/);
  assert.equal(path.dirname(serverPath), state);
  assert.equal(server.status, 'ready');
  const seed = JSON.parse(await fs.readFile(path.join(state, 'e2e-seed.json')));
  const oracles = await Promise.all([0, 1].map(async index => JSON.parse(await fs.readFile(path.join(state, `h5-${index}/oracle.json`)))));
  const origin = `http://127.0.0.1:${server.port}`;
  const runId = new Date().toISOString().replace(/[:.]/g, '-');
  const receipt = {format: 'disco-workbench-replacement-browser-e2e', passed: false, errors: [], requests: [],
    git_head: server.git_head, source_sha256: server.source_sha256,
    limits: ['Current-source browser/native service integration; not installed-app or packaged release evidence.']};
  const browser = await chromium.launch({headless: true, ...(process.env.DISCO_E2E_CHROME ? {executablePath: process.env.DISCO_E2E_CHROME} : {})});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.on('pageerror', error => receipt.errors.push(error.message));
  page.on('request', request => {if (/propose-to-protocol|replacement-accept|apply-to-protocol/.test(request.url())) receipt.requests.push({url:request.url(),method:request.method(),body:request.postDataJSON()});});
  async function api(route, body) {
    const response = await fetch(origin + '/api' + route, {method: body === undefined ? 'GET' : 'POST',
      headers: {'Content-Type': 'application/json', 'X-Workspace-Request': '1'},
      ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    const value = await response.json();
    assert.ok(response.ok, `${route}: ${response.status} ${JSON.stringify(value)}`);
    return value;
  }
  try {
    const predicate = {field: 'parameters/fixtureOrdinal', operator: 'gte', value: 60};
    await api('/search-presets', {name: 'Owned mixed protocol changes', predicate, splits: 'cell', pinned: true});
    await page.goto(origin);
    await page.getByRole('button', {name: 'Search predicate', exact: true}).first().click();
    await page.getByRole('button', {name: /Owned mixed protocol changes/}).first().click();
    await page.getByRole('button', {name: 'Export', exact: true}).click();
    await page.getByRole('button', {name: /^Update pinned protocol/}).click();
    await page.getByLabel('Target protocol', {exact: true}).selectOption(seed.protocol);
    await page.getByRole('button', {name: 'Review in Workbench', exact: true}).click();
    const review = page.getByRole('region', {name: 'Frozen protocol change review'});
    await review.waitFor();
    await page.getByRole('checkbox', {name: 'Approve removing 120 epochs from this pinned dataset.', exact: true}).waitFor();
    assert.equal((await api(`/protocols/${seed.protocol}/epochs?limit=200`)).epochs.length, 122);
    assert.equal(await page.getByRole('button', {name: 'Accept protocol changes', exact: true}).isEnabled(), false);
    await page.screenshot({path: path.join(state, 'mixed-review-before-approval.png'), fullPage: true});
    await page.getByRole('checkbox', {name: 'Approve removing 120 epochs from this pinned dataset.', exact: true}).check();
    await page.getByRole('button', {name: 'Accept protocol changes', exact: true}).click();
    await page.getByRole('status').filter({hasText: 'Protocol changes accepted'}).waitFor();
    assert.deepEqual((await api(`/protocols/${seed.protocol}/epochs?limit=200`)).epochs.map(row => row.epoch_uuid).sort(),
      oracles.flatMap(oracle => oracle.epochs.filter(row => row.ordinal >= 60).map(row => row.uuid)).sort());
    assert.equal((await api(`/epochs/${oracles[0].epochs.find(row => row.ordinal === 60).uuid}?protocol_uuid=${seed.protocol}`)).curation.included, false);
    await page.screenshot({path: path.join(state, 'mixed-review-accepted.png'), fullPage: true});
    await api('/search-presets', {name: 'Owned empty protocol changes',
      predicate: {field: 'parameters/fixtureOrdinal', operator: 'gt', value: 1000}, splits: 'cell', pinned: true});
    await page.getByRole('button', {name: 'Search predicate', exact: true}).first().click();
    await page.getByRole('button', {name: /Owned empty protocol changes/}).first().click();
    await page.getByRole('button', {name: 'Export', exact: true}).click();
    assert.equal(await page.getByRole('button', {name: /^Export directly/}).isEnabled(), false);
    await page.getByRole('button', {name: /^Update pinned protocol/}).click();
    await page.getByLabel('Target protocol', {exact: true}).selectOption(seed.protocol);
    await page.getByRole('button', {name: 'Review in Workbench', exact: true}).click();
    await page.getByRole('checkbox', {name: 'Approve removing 6 epochs from this pinned dataset.', exact: true}).waitFor();
    assert.equal((await api(`/protocols/${seed.protocol}/epochs?limit=200`)).epochs.length, 6);
    await page.screenshot({path: path.join(state, 'empty-review-before-approval.png'), fullPage: true});
    await page.getByRole('checkbox', {name: 'Approve removing 6 epochs from this pinned dataset.', exact: true}).check();
    await page.getByRole('button', {name: 'Accept protocol changes', exact: true}).click();
    await page.getByRole('status').filter({hasText: 'Protocol changes accepted'}).waitFor();
    assert.equal((await api(`/protocols/${seed.protocol}/epochs?limit=200`)).epochs.length, 0);
    await page.screenshot({path: path.join(state, 'empty-review-accepted.png'), fullPage: true});
    assert.equal(receipt.requests.filter(row => /propose-to-protocol/.test(row.url)).length, 2);
    assert.equal(receipt.requests.filter(row => /replacement-accept/.test(row.url)).length, 2);
    assert.equal(receipt.requests.filter(row => /apply-to-protocol/.test(row.url)).length, 0);
    assert.deepEqual(receipt.errors, []);
    receipt.passed = true;
  } catch (error) {
    receipt.failure = error.stack;
    receipt.visible_text = await page.locator('body').innerText();
    await page.screenshot({path: path.join(state, 'browser-failure.png'), fullPage: true});
    throw error;
  } finally {
    await browser.close();
    await fs.writeFile(path.join(state, `browser-receipt-${runId}.json`), JSON.stringify(receipt, null, 2));
    await fs.writeFile(path.join(state, 'browser-receipt.json'), JSON.stringify(receipt, null, 2));
  }
  console.log(JSON.stringify({passed: receipt.passed, requests: receipt.requests, state}));
}
main().catch(error => {console.error(error); process.exitCode = 1;});
