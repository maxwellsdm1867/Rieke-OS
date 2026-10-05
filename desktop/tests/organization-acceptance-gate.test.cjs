'use strict';
// Exercise actual preflight source with inert I/O; never load Playwright or spawn.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const filename = path.resolve(__dirname, '../e2e/organization-acceptance.e2e.cjs');
const source = fs.readFileSync(filename, 'utf8');

function fixture(overrides = {}, missing = false) {
  const candidate = '/owned/Disco.app';
  const gate = {
    format: 'disco-organization-execution-gate', version: 1,
    parent_review: 'approved', status: 'passed', quiet_window_reference: 'inert-test',
    valid_until: new Date(Date.now() + 60000).toISOString(),
    candidate_bundle: candidate, candidate_commit: 'reviewed-commit',
    harness_files: {}, ...overrides,
  };
  let launches = 0, processReads = 0;
  const io = {
    async readFile(name) {
      if (name === '/owned/gate.json') {
        if (missing) throw Object.assign(new Error('missing gate'), {code: 'ENOENT'});
        return JSON.stringify(gate);
      }
      return Buffer.from('inert source bytes');
    },
    async realpath(name) { return name; },
  };
  const moduleObject = {exports: {}};
  function inertRequire(name) {
    if (name === 'node:fs/promises') return io;
    if (name === './organization-ownership.cjs') return {
      OwnedProcesses: class { constructor() { launches++; throw Error('forbidden ownership launch'); } },
      within: () => true,
      async run(_command, args) {
        processReads++;
        return {stdout: args[0] === 'rev-parse' ? 'reviewed-commit\n' : ''};
      },
    };
    if (name === './organization-owned-launcher.cjs') return {
      OwnedApplication: class { constructor() { launches++; throw Error('forbidden app launch'); } },
      safeMessage: error => error.message,
    };
    if (!['node:assert/strict', 'node:path', 'node:os', 'node:crypto'].includes(name)) {
      throw Error('Unexpected dependency: ' + name);
    }
    return require(name);
  }
  inertRequire.main = {};
  const context = vm.createContext({require: inertRequire, module: moduleObject,
    __dirname: path.dirname(filename), Buffer, process: {argv: []},
    setTimeout: () => { throw Error('Unexpected timer'); }});
  // Test-only exposure; the shipping harness keeps its public exports unchanged.
  new vm.Script(source + '\nmodule.exports.TestAcceptance = Acceptance;', {filename}).runInContext(context);
  const instance = new moduleObject.exports.TestAcceptance({gate: '/owned/gate.json',
    'candidate-bundle': candidate, 'fixture-directory': '/owned/fixture', output: '/owned/output'});
  instance.verifyLauncherDependencies = async () => {}; // Separate source-bound dependency gate.
  return {instance, effects: () => ({launches, processReads})};
}

for (const [name, overrides, missing, expected, reads] of [
  ['missing gate', {}, true, /missing gate/, 0],
  ['unapproved gate', {parent_review: 'pending'}, false, /pending/, 0],
  ['expired gate', {valid_until: '2000-01-01T00:00:00Z'}, false, /Current reviewed quiet window/, 0],
  ['mismatched bundle', {candidate_bundle: '/other/Disco.app'}, false, /Disco.app/, 0],
  ['mismatched source commit', {candidate_commit: 'other-commit'}, false, /other-commit/, 2],
  ['mismatched harness hash', {}, false, /strictly equal/, 2],
]) {
  test('acceptance preflight refuses ' + name + ' before launch', async () => {
    const sample = fixture(overrides, missing);
    await assert.rejects(sample.instance.preflight(), expected);
    assert.deepEqual(sample.effects(), {launches: 0, processReads: reads});
  });
}
