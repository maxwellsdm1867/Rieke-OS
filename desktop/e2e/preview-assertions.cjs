'use strict';
// Final packaged-smoke assertions, callable from the owned real-project E2E.
// This module never launches Electron, builds, refreshes, or opens a database
// writer. Run only in the parent-approved packaged qualification slot.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path');
const {createHash} = require('node:crypto');
const runFile = require('node:util').promisify(require('node:child_process').execFile);
const REQUIRED = ['workspace_typed_index.py', 'workspace_typed_query.py',
  'workspace_typed_lifecycle.py', 'workspace_explore_queries.py'];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
async function verifyPackagedSource({bundle, source, commit, run = runFile}) {
  assert.match(commit, /^[a-f0-9]{40}$/);
  assert.equal((await run('git', ['-C', source, 'rev-parse', 'HEAD'])).stdout.trim(), commit);
  assert.equal((await run('git', ['-C', source, 'status', '--porcelain'])).stdout.trim(), '', 'Qualification source must be clean');
  const runtime = path.join(bundle, 'Contents/Resources/runtime');
  const raw = await fs.readFile(path.join(runtime, 'runtime-manifest.json')), manifest = JSON.parse(raw);
  assert.equal(manifest.source_commit, commit); assert.equal(manifest.source_dirty, false);
  const release = JSON.parse(await fs.readFile(path.join(source, 'rieke-release.json')));
  assert.equal(manifest.application_version, release.version);
  const profile = JSON.parse(await fs.readFile(path.join(source, 'desktop/application-profile.json')));
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(runtime, 'application/application-profile.json'))), profile);
  for (const name of REQUIRED) assert.ok(profile.python_modules.includes(name), 'Application allowlist omits ' + name);
  const hashes = {};
  for (const name of profile.python_modules) {
    assert.equal(path.basename(name), name);
    const packaged = sha(await fs.readFile(path.join(runtime, 'application/python', name)));
    assert.equal(packaged, sha(await fs.readFile(path.join(source, 'python', name))), 'Stale packaged module ' + name);
    assert.equal(packaged, manifest.resources['application/python/' + name]?.sha256, 'Manifest module hash differs: ' + name);
    hashes[name] = packaged;
  }
  return {source_commit:commit, application_version:manifest.application_version,
    runtime_manifest_sha256:sha(raw), asar_sha256:sha(await fs.readFile(path.join(bundle, 'Contents/Resources/app.asar'))),
    python_module_hashes:hashes};
}
async function assertTypedPublication({page, project, bundle, run = runFile}) {
  // field_registry unconditionally reads the typed owner when generation.typed
  // exists. Matching its token to the actual sealed published sidecar proves
  // that the packaged service exercised that reader, beyond file presence.
  const actual = await page.evaluate(async () => {
    async function request(url, body) {
      const response = await fetch(url, body === undefined ? {} : {method:'POST',
        headers:{'Content-Type':'application/json', 'X-Workspace-Request':'1'}, body:JSON.stringify(body)});
      if (!response.ok) throw new Error('Packaged typed assertion request failed: ' + response.status);
      return response.json();
    }
    return {status:await request('/api/metadata/status'),
      registry:await request('/api/explore/field-registry'),
      page:await request('/api/explore/page', {predicate:{all:[]}, limit:1})};
  });
  assert.equal(actual.status.status, 'ready');
  assert.ok(['built', 'reopened', 'reused'].includes(actual.status.last_refresh?.typed_metadata_index));
  assert.match(actual.registry.generation?.typed || '', /^[a-f0-9]{64}$/);
  assert.ok(actual.registry.fields.length > 0); assert.equal(actual.registry.summary_available, false);
  assert.equal(actual.page.generation?.typed, actual.registry.generation.typed);
  assert.ok(actual.page.rows.length > 0, 'Copied real project must contain metadata');
  const directory = path.join(project, 'cache/typed-metadata');
  const publication = JSON.parse(await fs.readFile(path.join(directory, '.current-generations.json')));
  assert.equal(publication.version, 1); assert.equal(publication.kind, 'metadata');
  assert.ok(publication.keep.length > 0);
  // Use only this bundle's Python and stdlib, with read-only SQLite. No source
  // checkout imports, attachment to native MySQL, or writable connection.
  const program = `import hashlib,json,sqlite3,sys
from pathlib import Path
from urllib.parse import quote
p=Path(sys.argv[1]); seal=json.loads(Path(str(p)+'.sha256.json').read_text())
assert hashlib.sha256(p.read_bytes()).hexdigest()==seal['sha256']
c=sqlite3.connect('file:'+quote(str(p))+'?mode=ro',uri=True)
try: r={k:json.loads(v) for k,v in c.execute('SELECT key,value FROM typed_receipt')}
finally: c.close()
assert r['complete'] is True and r['format']==seal['format']
assert r['generation']==seal['generation'] and r['project_uuid']==seal['project_uuid']
token=hashlib.sha256(json.dumps({'generation':r['generation'],'project_uuid':r['project_uuid'],'source_identity':r['source_identity'],'typed_sha256':seal['sha256'],'format':r['format']},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
print(json.dumps({'token':token,'sha256':seal['sha256'],'project_uuid':r['project_uuid']}))`;
  let exercised;
  for (const name of publication.keep) {
    assert.match(name, /^[a-f0-9]{64}\.sqlite$/);
    const {stdout} = await run(path.join(bundle, 'Contents/Resources/runtime/python/bin/python3.11'),
      ['-I', '-B', '-c', program, path.join(directory, name)], {timeout:30000, maxBuffer:4096});
    const receipt = JSON.parse(stdout);
    assert.equal(receipt.project_uuid, publication.owner);
    if (receipt.token === actual.registry.generation.typed) exercised = {filename:name, ...receipt};
  }
  assert.ok(exercised, 'Packaged field registry did not exercise a published typed sidecar');
  return {published:true, exercised:true, registry_fields:actual.registry.fields.length,
    queried_rows:actual.page.rows.length, typed_generation:actual.registry.generation.typed,
    sidecar:exercised};
}
module.exports = {verifyPackagedSource, assertTypedPublication};
