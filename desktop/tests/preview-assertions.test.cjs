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
  await write(path.join(runtime, 'runtime-manifest.json'), manifest);
  await write(path.join(bundle, 'Contents/Resources/app.asar'), 'exact asar');
  const run = async (_command, args) => ({stdout:args.includes('rev-parse') ? commit : ''});
  return {bundle, source, project, runtime, commit, run, write};
}
test('packaged source assertion records all module hashes and rejects stale modules or dirty provenance', async t => {
  const f = await fixture(t), evidence = await verifyPackagedSource(f);
  assert.equal(Object.keys(evidence.python_module_hashes).length, 4);
  assert.equal(evidence.source_commit, f.commit);
  assert.match(evidence.runtime_manifest_sha256, /^[a-f0-9]{64}$/);
  await f.write(path.join(f.runtime, 'application/python/workspace_explore_queries.py'), '# stale summary');
  await assert.rejects(verifyPackagedSource(f), /Stale packaged module/);
  await assert.rejects(verifyPackagedSource({...f,
    run:async(_command, args) => ({stdout:args.includes('rev-parse') ? f.commit : ' M desktop/main.cjs'})}), /source must be clean/);
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
