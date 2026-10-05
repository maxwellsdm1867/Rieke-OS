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
async function regularFiles(directory) {
  const files = [];
  async function visit(relative) {
    const file = path.join(directory, relative), stat = await fs.lstat(file);
    assert.ok(!stat.isSymbolicLink(), 'Renderer tree contains a symlink: ' + file);
    if (stat.isDirectory()) {
      for (const name of (await fs.readdir(file)).sort()) await visit(path.join(relative, name));
    } else {
      assert.ok(stat.isFile(), 'Renderer tree contains a non-file: ' + file);
      files.push(relative.split(path.sep).join('/'));
    }
  }
  await visit('');
  return files.sort();
}
async function rendererProvenance({runtime, source, renderer, manifest, commit, run}) {
  // The build owner must freshly build renderer from this clean commit first.
  // These checks bind that retained output to the final bundle and record its
  // source inputs; they do not reconstruct the compilation from source bytes.
  const packagedRoot = path.join(runtime, 'frontend');
  const builtFiles = await regularFiles(renderer), packagedFiles = await regularFiles(packagedRoot);
  assert.ok(builtFiles.includes('index.html'), 'Built renderer omits index.html');
  assert.ok(builtFiles.some(name => name.endsWith('.js')), 'Built renderer omits JavaScript');
  assert.ok(builtFiles.some(name => name.endsWith('.css')), 'Built renderer omits CSS');
  assert.deepEqual(packagedFiles, builtFiles, 'Packaged renderer inventory differs from final build');
  const manifestFiles = Object.keys(manifest.resources).filter(name => name.startsWith('frontend/'))
    .map(name => name.slice('frontend/'.length)).sort();
  assert.deepEqual(manifestFiles, builtFiles, 'Renderer manifest inventory differs from final build');
  const builtHashes = {}, packagedHashes = {};
  for (const name of builtFiles) {
    const built = await fs.readFile(path.join(renderer, name));
    const packaged = await fs.readFile(path.join(packagedRoot, name));
    builtHashes[name] = sha(built); packagedHashes[name] = sha(packaged);
    assert.equal(packagedHashes[name], builtHashes[name], 'Stale packaged renderer asset: ' + name);
    const entry = manifest.resources['frontend/' + name];
    assert.equal(entry.sha256, packagedHashes[name], 'Renderer manifest hash differs: ' + name);
    assert.equal(entry.size, packaged.length, 'Renderer manifest size differs: ' + name);
  }
  // Match the application's relocatable static-route link as well as the
  // physical resource tree. Never follow a replacement link outside the bundle.
  const route = path.join(runtime, 'application/workspace-app/dist');
  assert.equal(await fs.readlink(route), '../../frontend', 'Renderer route is redirected');
  assert.equal(manifest.resources['application/workspace-app/dist']?.symlink, '../../frontend');
  assert.equal(await fs.realpath(route), await fs.realpath(packagedRoot));
  const index = await fs.readFile(path.join(packagedRoot, 'index.html'), 'utf8');
  const scripts = [...index.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi)].map(match => match[1]);
  assert.ok(scripts.length > 0, 'Built renderer has no script entrypoint');
  for (const url of scripts) {
    assert.ok(!/^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(url), 'Renderer script depends on an external server: ' + url);
    const local = new URL(url, 'http://packaged.invalid/');
    const name = decodeURIComponent(local.pathname).replace(/^\//, '');
    assert.ok(name.startsWith('assets/') && name.endsWith('.js') && packagedFiles.includes(name),
      'Renderer script is not a bundled production asset: ' + url);
  }
  const {stdout} = await run('git', ['-C', source, 'ls-files', '--cached', '-z', '--', 'workspace-app']);
  const tracked = stdout.split('\0').filter(Boolean).sort(), sourceHashes = {};
  for (const required of ['index.html', 'package.json', 'package-lock.json', 'vite.config.js']) {
    assert.ok(tracked.includes('workspace-app/' + required), 'Renderer source inventory omits ' + required);
  }
  assert.ok(tracked.some(name => name.startsWith('workspace-app/src/')), 'Renderer source inventory omits src');
  for (const name of tracked) {
    assert.ok(name.startsWith('workspace-app/') && !name.split('/').includes('..') && !name.includes('\\'));
    const file = path.join(source, name);
    assert.ok((await fs.lstat(file)).isFile(), 'Renderer source must be a regular tracked file: ' + name);
    assert.equal(await fs.realpath(file), path.join(await fs.realpath(source), name), 'Renderer source is redirected: ' + name);
    sourceHashes[name] = sha(await fs.readFile(file));
  }
  return {source_commit:commit, build_output:path.relative(source, renderer),
    source_file_hashes:sourceHashes, source_inventory_sha256:sha(JSON.stringify(sourceHashes)),
    built_asset_hashes:builtHashes, packaged_asset_hashes:packagedHashes,
    asset_inventory_sha256:sha(JSON.stringify(packagedHashes)), script_entrypoints:scripts,
    static_route:'application/workspace-app/dist -> ../../frontend'};
}
function validatePythonProfile(profile) {
  assert.equal(profile.format, 'rieke-application-profile', 'Invalid application profile format');
  assert.ok([1, 2].includes(profile.version), 'Unsupported application profile version');
  const names = profile.python_modules;
  assert.ok(Array.isArray(names) && names.length && names.every(name => typeof name === 'string' && name), 'Invalid application module list');
  assert.equal(new Set(names).size, names.length, 'Duplicate application module');
  const folded = new Set(), identities = new Set();
  for (const name of names) {
    const parts = name.split('/');
    assert.ok(!parts.some(part => ['', '.', '..'].includes(part)) && !/[\\\0:]/.test(name) && name.endsWith('.py') &&
      (profile.version !== 1 || parts.length === 1), 'Unsafe application Python path: ' + name);
    if (profile.version === 2) {
      assert.ok([...parts.slice(0, -1), parts.at(-1).slice(0, -3)].every(part => /^[A-Za-z_][A-Za-z_0-9]*$/.test(part)), 'Invalid application module identifier: ' + name);
      assert.notEqual(name, '__init__.py', 'Python source root is not an application package');
      assert.ok(!parts.includes('tests') && !parts.at(-1).startsWith('test_'), 'Test source in application profile: ' + name);
      assert.ok(!folded.has(name.toLowerCase()), 'Case-colliding application paths: ' + name); folded.add(name.toLowerCase());
      const identity = name.slice(0, -3).replace(/\/__init__$/, '').split('/').join('.');
      assert.ok(!identities.has(identity), 'Ambiguous application module identity: ' + name); identities.add(identity);
      for (let end = 1; end < parts.length; end++)
        assert.ok(names.includes(parts.slice(0, end).join('/') + '/__init__.py'), 'Missing application package initializer: ' + name);
      const sourceName = 'python/' + name;
      assert.ok(!(profile.source_excluded_paths || []).includes(sourceName) &&
        !(profile.runtime_only_exclusions || []).some(item => item.path === sourceName), 'Excluded application source: ' + name);
      // Source exclusions use the profile's fnmatch subset (* and ?). Reject
      // unsupported patterns rather than silently disagree with Python.
      for (const {pattern} of profile.source_exclusions || []) {
        assert.ok(typeof pattern === 'string' && !/[\[\]\\]/.test(pattern), 'Unsupported source exclusion pattern');
        const expression = '^' + pattern.split('').map(c => c === '*' ? '.*' : c === '?' ? '.' : c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('') + '$';
        assert.ok(!new RegExp(expression).test(sourceName), 'Excluded application source: ' + name);
      }
    }
  }
}
async function regularPythonFile(base, relative) {
  let target = base;
  const baseStat = await fs.lstat(base);
  assert.ok(baseStat.isDirectory() && !baseStat.isSymbolicLink(), 'Redirected Python root: ' + base);
  const parts = relative.split('/');
  for (let i = 0; i < parts.length; i++) {
    target = path.join(target, parts[i]);
    const stat = await fs.lstat(target);
    assert.ok(!stat.isSymbolicLink() && (i === parts.length - 1 ? stat.isFile() : stat.isDirectory()), 'Redirected Python file/parent: ' + relative);
  }
  return target;
}
async function pythonInventory(base) {
  const files = [];
  async function visit(relative) {
    const current = path.join(base, relative), stat = await fs.lstat(current);
    assert.ok(!stat.isSymbolicLink(), 'Redirected Python inventory: ' + relative);
    if (stat.isDirectory()) for (const name of await fs.readdir(current)) await visit(relative ? relative + '/' + name : name);
    else if (relative.endsWith('.py')) {assert.ok(stat.isFile(), 'Non-file Python source'); files.push(relative);}
  }
  await visit('');
  return files.sort();
}
async function verifyPackagedSource({bundle, source, commit, renderer = path.join(source, 'desktop/build/renderer'), run = runFile}) {
  assert.match(commit, /^[a-f0-9]{40}$/);
  assert.equal((await run('git', ['-C', source, 'rev-parse', 'HEAD'])).stdout.trim(), commit);
  assert.equal((await run('git', ['-C', source, 'status', '--porcelain'])).stdout.trim(), '', 'Qualification source must be clean');
  const runtime = path.join(bundle, 'Contents/Resources/runtime');
  const raw = await fs.readFile(path.join(runtime, 'runtime-manifest.json')), manifest = JSON.parse(raw);
  assert.equal(manifest.source_commit, commit); assert.equal(manifest.source_dirty, false);
  const release = JSON.parse(await fs.readFile(path.join(source, 'rieke-release.json')));
  assert.equal(manifest.application_version, release.version);
  const profile = JSON.parse(await fs.readFile(await regularPythonFile(source, 'desktop/application-profile.json')));
  assert.deepEqual(JSON.parse(await fs.readFile(await regularPythonFile(runtime, 'application/application-profile.json'))), profile);
  validatePythonProfile(profile);
  assert.deepEqual(await pythonInventory(path.join(runtime, 'application/python')), [...profile.python_modules].sort(), 'Packaged Python inventory differs');
  for (const name of REQUIRED) assert.ok(profile.python_modules.includes(name), 'Application allowlist omits ' + name);
  const hashes = {};
  for (const name of profile.python_modules) {
    const packaged = sha(await fs.readFile(await regularPythonFile(runtime, 'application/python/' + name)));
    assert.equal(packaged, sha(await fs.readFile(await regularPythonFile(source, 'python/' + name))), 'Stale packaged module ' + name);
    assert.equal(packaged, manifest.resources['application/python/' + name]?.sha256, 'Manifest module hash differs: ' + name);
    hashes[name] = packaged;
  }
  return {source_commit:commit, application_version:manifest.application_version,
    runtime_manifest_sha256:sha(raw), asar_sha256:sha(await fs.readFile(path.join(bundle, 'Contents/Resources/app.asar'))),
    python_module_hashes:hashes,
    renderer:await rendererProvenance({runtime, source, renderer, manifest, commit, run})};
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
