'use strict';
// Source-only exact allowlist and staged literal-require check. This does not
// invoke electron-builder or establish actual asar/native qualification.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {createRequire} = require('node:module');
const {pathToFileURL} = require('node:url');
const desktop = path.resolve(__dirname, '..');
const entries = ['close/draft-barrier.cjs', 'close/quit-coordinator.cjs',
  'drafts/draft-store.cjs', 'startup/startup-session.cjs'];
const rootPatterns = ['*.cjs', '*.html', '*.css'];
const rootFiles = ['recovery.js', 'icon.png', 'package.json', 'distribution.json', 'rieke-emblem.png'];
const expectedFiles = [...rootPatterns, ...rootFiles, ...entries];
const parser = import(pathToFileURL(path.resolve(desktop, '../workspace-app/architectureImports.mjs')).href);

function stage(t, mutate = () => {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'disco-close-package-')));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  // Only these currently reviewed root patterns are interpreted. No glob engine
  // approximation: assert their exact spelling/set before selecting root files.
  const config = JSON.parse(fs.readFileSync(path.join(desktop, 'package.json'))).build;
  const preview = {...require('../preview-builder.cjs'), files: [...require('../preview-builder.cjs').files]};
  const selected = fs.readdirSync(desktop).filter(name => rootFiles.includes(name) || /\.(cjs|html|css)$/.test(name));
  for (const name of [...selected, ...entries]) {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.copyFileSync(path.join(desktop, name), target);
  }
  const fixture = {root, config, preview};
  mutate(fixture);
  return fixture;
}

async function check({root, config, preview}) {
  for (const [label, build] of [['default', config], ['preview', preview]]) {
    assert.deepEqual([...build.files].sort(), [...expectedFiles].sort(), `${label}: exact reviewed app entries`);
    for (const entry of entries) assert.ok(fs.statSync(path.join(root, entry)).isFile(), `${label}: missing ${entry}`);
    for (const old of entries.map(entry => path.basename(entry))) assert.ok(!fs.existsSync(path.join(root, old)), `old entry ${old}`);
    for (const name of ['main', 'preload', 'sign-runtime', 'seal-testing']) assert.ok(fs.existsSync(path.join(root, name + '.cjs')));
    assert.equal(build.mac.sign, './sign-runtime.cjs');
    assert.equal(build.afterPack, './seal-testing.cjs');
  }
  const {dependencies} = await parser;
  const main = fs.readFileSync(path.join(root, 'main.cjs'), 'utf8');
  const mainDependencies = dependencies('main.cjs', main);
  for (const entry of entries) assert.ok(mainDependencies.includes('./' + entry), `main must require ${entry}`);
  // Check main and the four moved public entries only, without evaluating application
  // code. Existing unrelated helper CLI require.main guards are outside this
  // scoped parser policy; this is not a whole-desktop transitive closure audit.
  const pending = ['main.cjs', ...entries], seen = new Set();
  while (pending.length) {
    const relative = pending.pop();
    if (seen.has(relative)) continue;
    seen.add(relative);
    const filename = path.join(root, relative);
    const code = fs.readFileSync(filename, 'utf8');
    const imports = dependencies(relative, code);
    const stateDependencies = {
      'drafts/draft-store.cjs': ['node:fs/promises', 'node:path', 'node:crypto', '../security.cjs'],
      'startup/startup-session.cjs': ['node:fs/promises', 'node:path', 'node:crypto', '../supervisor.cjs', '../security.cjs'],
    };
    for (const specifier of imports) {
      if (!specifier.startsWith('.')) continue; // External packages retain package lock policy.
      const resolved = createRequire(filename).resolve(specifier);
      const target = path.relative(root, resolved);
      assert.ok(!target.startsWith('..') && !path.isAbsolute(target), `local require escaped stage: ${specifier}`);
      assert.ok(!target.split(path.sep).some(part => ['test', 'tests', 'e2e'].includes(part)), `production imports test: ${target}`);
      // Resolve direct installed targets; do not claim to parse their internals.
    }
    if (stateDependencies[relative]) assert.deepEqual([...imports].sort(), [...stateDependencies[relative]].sort(), `${relative}: reviewed direct dependencies`);
  }
  for (const entry of entries) assert.ok(seen.has(entry), `unreached entry ${entry}`);
  return seen;
}

test('default and preview declare all adopted nested entries; staged adopted desktop local requires resolve', async t => {
  const seen = await check(stage(t));
  assert.ok(seen.has('main.cjs'));
  assert.equal(seen.size, 5);
});

for (const entry of entries) test(`omitting ${entry} from either configuration fails`, async t => {
  for (const mode of ['config', 'preview']) {
    const fixture = stage(t, value => { value[mode].files = value[mode].files.filter(name => name !== entry); });
    await assert.rejects(check(fixture), /exact reviewed app entries/);
  }
});

for (const fault of ['close/tests/quit-coordinator.test.cjs', 'drafts/tests/draft-store.test.cjs',
  'startup/tests/startup-session.test.cjs', '**/*.cjs', 'close/**/*.cjs', 'drafts/**/*.cjs', 'startup/**/*.cjs']) {
  test(`test inclusion or broad pattern ${fault} fails`, async t => {
    for (const mode of ['config', 'preview']) {
      await assert.rejects(check(stage(t, value => { value[mode].files.push(fault); })), /exact reviewed app entries/);
    }
  });
}

for (const entry of entries) test(`stale main require for ${entry} fails before application evaluation`, async t => {
  await assert.rejects(check(stage(t, ({root}) => {
    const file = path.join(root, 'main.cjs');
    fs.writeFileSync(file, fs.readFileSync(file, 'utf8').replace('./' + entry, './' + path.basename(entry)));
  })), /main must require/);
});

for (const [entry, dependency] of [
  ['drafts/draft-store.cjs', 'security.cjs'],
  ['startup/startup-session.cjs', 'security.cjs'],
  ['startup/startup-session.cjs', 'supervisor.cjs'],
]) test(`stale installed dependency ${entry} -> ${dependency} fails`, async t => {
  await assert.rejects(check(stage(t, ({root}) => {
    const file = path.join(root, entry);
    const source = fs.readFileSync(file, 'utf8');
    assert.ok(source.includes('../' + dependency));
    fs.writeFileSync(file, source.replace('../' + dependency, './' + dependency));
  })), /Cannot find module/);
});

test('missing installed relative dependency fails', async t => {
  await assert.rejects(check(stage(t, ({root}) => fs.unlinkSync(path.join(root, 'security.cjs')))), /Cannot find module/);
});

for (const entry of entries) test(`moved entry ${entry} missing from stage fails`, async t => {
  await assert.rejects(check(stage(t, ({root}) => fs.unlinkSync(path.join(root, entry)))), /ENOENT/);
});
