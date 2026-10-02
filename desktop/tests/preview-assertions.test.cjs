'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const {createHash} = require('node:crypto');
const {verifyPackagedSource, assertTypedPublication} = require('../e2e/preview-assertions.cjs');
async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'preview-assertions-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  const bundle = path.join(root, 'Rieke OS.app'), source = path.join(root, 'source'), project = path.join(root, 'project');
  const runtime = path.join(bundle, 'Contents/Resources/runtime'), commit = 'a'.repeat(40);
  const renderer = path.join(source, 'desktop/build/renderer');
  const modules = ['workspace_typed_index.py','workspace_typed_query.py','workspace_typed_lifecycle.py','workspace_explore_queries.py'];
  const profile = {python_modules:modules}, manifest = {source_commit:commit, source_dirty:false, application_version:'0.1.6',resources:{}};
  async function write(file, value) {await fs.mkdir(path.dirname(file), {recursive:true}); await fs.writeFile(file, typeof value === 'string' ? value : JSON.stringify(value));}
  await write(path.join(source, 'rieke-release.json'), {version:'0.1.6'});
  await write(path.join(source, 'desktop/application-profile.json'), profile);
  await write(path.join(runtime, 'application/application-profile.json'), profile);
  for (const name of modules) {
    const bytes = '# current ' + name;
    await write(path.join(source, 'python', name), bytes); await write(path.join(runtime, 'application/python', name), bytes);
    manifest.resources['application/python/' + name] = {sha256:createHash('sha256').update(bytes).digest('hex')};
  }
  const frontendSources = {
    'workspace-app/index.html':'<script type="module" src="/src/main.jsx"></script>',
    'workspace-app/package.json':'{"version":"0.1.6"}',
    'workspace-app/package-lock.json':'{"lockfileVersion":3}',
    'workspace-app/vite.config.js':'export default {plugins:[]};',
    'workspace-app/src/main.jsx':'// final integrated frontend',
    'workspace-app/public/icon.png':'icon bytes',
  };
  for (const [name, bytes] of Object.entries(frontendSources)) await write(path.join(source, name), bytes);
  const assets = {
    'index.html':'<link rel="stylesheet" href="/assets/index.css"><script type="module" src="/assets/index.js"></script>',
    'assets/index.js':'import("./lazy.js");', 'assets/lazy.js':'// final lazy chunk',
    'assets/index.css':':root {color:purple}', 'icon.png':'icon bytes',
  };
  for (const [name, bytes] of Object.entries(assets)) {
    await write(path.join(renderer, name), bytes); await write(path.join(runtime, 'frontend', name), bytes);
    manifest.resources['frontend/' + name] = {sha256:createHash('sha256').update(bytes).digest('hex'),size:Buffer.byteLength(bytes)};
  }
  await fs.mkdir(path.join(runtime, 'application/workspace-app'), {recursive:true});
  await fs.symlink('../../frontend', path.join(runtime, 'application/workspace-app/dist'));
  manifest.resources['application/workspace-app/dist'] = {symlink:'../../frontend'};
  await write(path.join(runtime, 'runtime-manifest.json'), manifest);
  await write(path.join(bundle, 'Contents/Resources/app.asar'), 'exact asar');
  const run = async (_command, args) => ({stdout:args.includes('rev-parse') ? commit :
    args.includes('ls-files') ? Object.keys(frontendSources).join('\0') + '\0' : ''});
  async function saveManifest() {await write(path.join(runtime, 'runtime-manifest.json'), manifest);}
  return {bundle, source, project, runtime, renderer, commit, run, write, manifest, saveManifest};
}
test('packaged source assertion records all module hashes and rejects stale modules or dirty provenance', async t => {
  const f = await fixture(t), evidence = await verifyPackagedSource(f);
  assert.equal(Object.keys(evidence.python_module_hashes).length, 4);
  assert.equal(evidence.source_commit, f.commit);
  assert.match(evidence.runtime_manifest_sha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(evidence.renderer.built_asset_hashes, evidence.renderer.packaged_asset_hashes);
  assert.equal(Object.keys(evidence.renderer.packaged_asset_hashes).length, 5);
  assert.equal(Object.keys(evidence.renderer.source_file_hashes).length, 6);
  assert.equal(evidence.renderer.source_commit, f.commit);
  assert.equal(evidence.renderer.build_output, 'desktop/build/renderer');
  assert.match(evidence.renderer.source_inventory_sha256, /^[a-f0-9]{64}$/);
  await f.write(path.join(f.runtime, 'application/python/workspace_explore_queries.py'), '# stale summary');
  await assert.rejects(verifyPackagedSource(f), /Stale packaged module/);
  await assert.rejects(verifyPackagedSource({...f,
    run:async(_command, args) => ({stdout:args.includes('rev-parse') ? f.commit : ' M desktop/main.cjs'})}), /source must be clean/);
});
test('renderer provenance rejects stale lazy chunks even with a matching updated packaged manifest', async t => {
  const f = await fixture(t), file = path.join(f.runtime, 'frontend/assets/lazy.js');
  await f.write(file, '// old lazy chunk');
  f.manifest.resources['frontend/assets/lazy.js'] = {
    sha256:createHash('sha256').update('// old lazy chunk').digest('hex'),size:Buffer.byteLength('// old lazy chunk')};
  await f.saveManifest();
  await assert.rejects(verifyPackagedSource(f), /Stale packaged renderer asset: assets\/lazy.js/);
});
test('renderer provenance rejects missing or extra packaged files and manifest inventory/hash/size drift', async t => {
  const f = await fixture(t), extra = path.join(f.runtime, 'frontend/assets/stale.js');
  await f.write(extra, 'stale accumulated Vite output');
  await assert.rejects(verifyPackagedSource(f), /Packaged renderer inventory differs/);
  await fs.rm(extra);
  const asset = 'frontend/assets/index.css', entry = f.manifest.resources[asset];
  delete f.manifest.resources[asset]; await f.saveManifest();
  await assert.rejects(verifyPackagedSource(f), /Renderer manifest inventory differs/);
  f.manifest.resources[asset] = {...entry,sha256:'0'.repeat(64)}; await f.saveManifest();
  await assert.rejects(verifyPackagedSource(f), /Renderer manifest hash differs/);
  f.manifest.resources[asset] = {...entry,size:entry.size + 1}; await f.saveManifest();
  await assert.rejects(verifyPackagedSource(f), /Renderer manifest size differs/);
  f.manifest.resources[asset] = entry; await f.saveManifest();
  await fs.rm(path.join(f.runtime, asset));
  await assert.rejects(verifyPackagedSource(f), /Packaged renderer inventory differs/);
});
test('renderer provenance rejects redirected static routes, symlink assets and untracked source inventories', async t => {
  const f = await fixture(t), route = path.join(f.runtime, 'application/workspace-app/dist');
  await fs.rm(route); await fs.symlink(f.renderer, route);
  await assert.rejects(verifyPackagedSource(f), /Renderer route is redirected/);
  await fs.rm(route); await fs.symlink('../../frontend', route);
  const file = path.join(f.runtime, 'frontend/icon.png');
  await fs.rm(file); await fs.symlink(path.join(f.renderer, 'icon.png'), file);
  await assert.rejects(verifyPackagedSource(f), /Renderer tree contains a symlink/);
  await fs.rm(file); await f.write(file, 'icon bytes');
  await assert.rejects(verifyPackagedSource({...f, run:async(command, args) => args.includes('ls-files') ?
    {stdout:'workspace-app/src/main.jsx\0'} : f.run(command, args)}), /source inventory omits index.html/);
});
test('renderer provenance rejects devserver and source entrypoints even when all three asset hashes match', async t => {
  const f = await fixture(t);
  for (const url of ['http://127.0.0.1:5173/src/main.jsx', '//localhost:5173/assets/index.js', '/src/main.jsx', '/assets/missing.js']) {
    const index = '<script type="module" src="' + url + '"></script>';
    await f.write(path.join(f.renderer, 'index.html'), index);
    await f.write(path.join(f.runtime, 'frontend/index.html'), index);
    f.manifest.resources['frontend/index.html'] = {sha256:createHash('sha256').update(index).digest('hex'),size:Buffer.byteLength(index)};
    await f.saveManifest();
    await assert.rejects(verifyPackagedSource(f), /external server|not a bundled production asset/);
  }
});
test('typed assertion requires publication plus a live API token matching a sealed bundled-reader receipt', async t => {
  const f = await fixture(t), token = 'b'.repeat(64), name = 'c'.repeat(64) + '.sqlite';
  await f.write(path.join(f.project, 'cache/typed-metadata/.current-generations.json'),
    {version:1, kind:'metadata', owner:'copied-project', keep:[name]});
  const response = {status:{status:'ready',last_refresh:{typed_metadata_index:'reopened'}},
    registry:{generation:{typed:token},fields:[{id:'date'}],summary_available:false},
    page:{generation:{typed:token},rows:[{}]}};
  const page = {evaluate:async() => response};
  const run = async (command, args) => {
    assert.equal(command, path.join(f.bundle, 'Contents/Resources/runtime/python/bin/python3.11'));
    assert.deepEqual(args.slice(0, 3), ['-I', '-B', '-c']); assert.match(args[3], /mode=ro/);
    return {stdout:JSON.stringify({token,sha256:'d'.repeat(64),project_uuid:'copied-project'})};
  };
  const result = await assertTypedPublication({...f, page, run});
  assert.equal(result.published, true); assert.equal(result.exercised, true);
  await assert.rejects(assertTypedPublication({...f, page, run:async() => ({stdout:JSON.stringify({token:'wrong',project_uuid:'copied-project'})})}), /did not exercise/);
  response.registry.generation.typed = null;
  await assert.rejects(assertTypedPublication({...f, page, run}));
});
