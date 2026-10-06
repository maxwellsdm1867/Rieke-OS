'use strict';
// Run against tools/workbench_replacement_e2e.py's owned native source server.
// Raw receipts/screenshots stay beside its temporary server receipt.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');

async function main() {
  const serverPath = process.argv[2];
  assert.ok(serverPath, 'Pass the owned server-receipt.json path');
  const server = JSON.parse(await fs.readFile(serverPath));
  const state = await fs.realpath(server.state);
  assert.match(path.basename(state), /^disco-workbench-replacement-e2e-/);
  assert.equal(path.dirname(serverPath), state);
  assert.equal(server.status, 'ready');
  const origin = `http://127.0.0.1:${server.port}`;
  const runId = new Date().toISOString().replace(/[:.]/g, '-');
  const receipt = {format: 'disco-workbench-replacement-native-e2e', source_root: server.source_root,
    git_head: server.git_head, source_sha256: server.source_sha256,
    project_uuid: server.project_uuid, cases: [], passed: false,
    limits: ['Current source, bundled dependencies, real native MySQL and donor-free H5; not a packaged release.']};
  async function api(route, body, expected = 200, method) {
    const response = await fetch(origin + '/api' + route, {method: method || (body === undefined ? 'GET' : 'POST'),
      headers: {'Content-Type': 'application/json', 'X-Workspace-Request': '1'},
      ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    const value = await response.json();
    assert.ok((Array.isArray(expected) ? expected : [expected]).includes(response.status), `${route}: ${response.status} ${JSON.stringify(value)}`);
    return value;
  }
  async function importFixture(index) {
    const source = path.join(state, `h5-${index}`, `synthetic-${index}.h5`);
    await fs.copyFile(path.join(state, `h5-${index}`, 'synthetic.h5'), source);
    const job = await api('/imports', {source_path: source}, 202);
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      const row = (await api('/jobs')).jobs.find(item => item.job_uuid === job.job_uuid);
      if (row && ['complete', 'complete_with_warnings', 'failed', 'interrupted', 'duplicate'].includes(row.status)) {
        assert.equal(row.status, 'complete', JSON.stringify(row));
        assert.deepEqual(row.warnings || [], []);
        return row;
      }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw new Error('Owned H5 import deadline exceeded');
  }
  try {
    const seeded = await fs.readFile(path.join(state, 'e2e-seed.json')).then(JSON.parse).catch(() => null);
    if (!seeded) {
      const first = await importFixture(0);
      receipt.cases.push({name: 'normal donor-free H5 import', job_uuid: first.job_uuid});
    }
    const overview = await api('/overview');
    assert.equal(overview.counts.epochs, process.argv.includes('--merge-only') ? 126 : 63);
    assert.equal(overview.protocols.length, 1);
    const protocol = overview.protocols[0].protocol_uuid;
    receipt.protocol_uuid = protocol;
    const profile = seeded?.profile || await api('/annotation-profiles', {display_name: 'Owned Workbench E2E'}, 201);
    await api('/annotation-profiles/selected', {profile_uuid: profile.profile_uuid});
    receipt.profile = profile;
    await fs.writeFile(path.join(state, 'e2e-seed.json'), JSON.stringify({protocol, profile}, null, 2));
    const base = `/protocols/${protocol}`;
    const members = async () => (await api(base + '/epochs?limit=200')).epochs.map(row => row.epoch_uuid).sort();
    const oracle0 = JSON.parse(await fs.readFile(path.join(state, 'h5-0/oracle.json')));
    const oracle1 = JSON.parse(await fs.readFile(path.join(state, 'h5-1/oracle.json')));
    const retainedCuration = oracle0.epochs.find(row => row.ordinal === 60).uuid;
    if (!process.argv.includes('--continue') && !process.argv.includes('--merge-only')) {
    const original = await members();
    assert.deepEqual(original, oracle0.epochs.map(row => row.uuid).sort());
    await api(base + '/curation', {epoch_uuids: [retainedCuration], changes: {included: false},
      expected_revisions: {[retainedCuration]: 0}, query_revision: (await api(base)).query_revision});
    const predicate = {field: 'parameters/fixtureOrdinal', operator: 'lt', value: 61};
    await api('/explore/preview', {predicate, splits: 'cell'});
    assert.deepEqual(await members(), original);
    assert.equal((await api(base + '/workbench')).replacement_reviews.length, 0);
    receipt.cases.push({name: 'exploratory Search leaves membership and review queue unchanged'});
    const saved = await api('/explore/revisions', {predicate, splits: 'cell', name: 'Narrow to cell A'}, 201);
    const sourceRoot = `/explore/revisions/${saved.revision_uuid}`;
    const compared = await api(sourceRoot + '/compare-to-protocol', {protocol_uuid: protocol});
    const submitBody = {protocol_uuid: protocol, operation_uuid: randomUUID(),
      expected_binding_version: compared.expected_binding_version, expected_query_revision: compared.expected_query_revision};
    const proposal = await api(sourceRoot + '/propose-to-protocol', submitBody, 201);
    assert.deepEqual(await members(), original);
    assert.deepEqual(await api(sourceRoot + '/propose-to-protocol', submitBody), proposal);
    const queue = await api(base + '/workbench');
    assert.equal(queue.replacement_reviews.length, 1);
    assert.equal(queue.replacement_pending_cell_count, 1);
    assert.equal(queue.replacement_pending_epoch_count, 2);
    assert.equal(queue.total_pending_cell_count, 1);
    assert.equal(queue.pending_epoch_count, 0);
    assert.equal(queue.candidates.length, 0);
    const preview = await api(proposal.root + '/replacement-preview');
    assert.deepEqual(preview.diff_counts, {added: 0, removed: 2, changed: 0});
    assert.deepEqual(preview.diff_summary.cell_changes.counts, {added: 0, removed: 1, updated: 0});
    const acceptBody = {operation_uuid: randomUUID(), confirm_removals: true};
    for (const key of ['expected_candidate_scope_revision', 'expected_binding_version', 'expected_query_revision', 'preview_sha256']) acceptBody[key] = preview[key];
    const competing = await api('/explore/revisions', {predicate: {...predicate, value: 60}, splits: 'cell', name: 'Competing narrower proposal'}, 201);
    const competingSource = `/explore/revisions/${competing.revision_uuid}`;
    const competingCompare = await api(competingSource + '/compare-to-protocol', {protocol_uuid: protocol});
    const competingProposal = await api(competingSource + '/propose-to-protocol', {protocol_uuid: protocol,
      expected_binding_version: competingCompare.expected_binding_version, expected_query_revision: competingCompare.expected_query_revision,
      operation_uuid: randomUUID()}, 201);
    const competingPreview = await api(competingProposal.root + '/replacement-preview');
    assert.deepEqual(competingPreview.diff_summary.cell_changes.counts, {added: 0, removed: 1, updated: 1});
    const competingBody = {operation_uuid: randomUUID(), confirm_removals: true};
    for (const key of ['expected_candidate_scope_revision', 'expected_binding_version', 'expected_query_revision', 'preview_sha256']) competingBody[key] = competingPreview[key];
    await api(proposal.root + '/replacement-accept', {...acceptBody, confirm_removals: false}, 400);
    assert.deepEqual(await members(), original);
    const accepted = await api(proposal.root + '/replacement-accept', acceptBody);
    assert.equal(accepted.removed_epoch_count, 2);
    assert.deepEqual(await members(), oracle0.cells[0].epoch_ids.toSorted());
    assert.equal((await api(`/epochs/${retainedCuration}?protocol_uuid=${protocol}`)).curation.included, false);
    assert.deepEqual(await api(proposal.root + '/replacement-accept', acceptBody), accepted);
    await api(proposal.root + '/replacement-accept', {...acceptBody, confirm_removals: false}, 409);
    receipt.cases.push({name: 'removal-only predicate proposal, explicit confirmation, exact acceptance, durable replay', proposal, accepted});
    await api(competingProposal.root + '/replacement-accept', competingBody, 409);
    assert.deepEqual(await members(), oracle0.cells[0].epoch_ids.toSorted());
    const superseded = await api(base + '/workbench');
    assert.equal(superseded.replacement_reviews.find(row => row.candidate_revision_uuid === competingProposal.candidate_revision_uuid).status, 'superseded');
    assert.equal(superseded.replacement_pending_epoch_count, 0);
    receipt.cases.push({name: 'partial cell removal counts updated; competing stale replacement refused and superseded'});
    }
    const beforeImport = await members();
    assert.equal(beforeImport.length, 61);
    if (!process.argv.includes('--merge-only')) await importFixture(1);
    assert.deepEqual(await members(), beforeImport);
    const afterImport = await api(base + '/workbench');
    assert.equal(afterImport.pending_epoch_count, 61);
    assert.equal(afterImport.candidates.length, 1);
    assert.equal(afterImport.replacement_reviews.filter(row => row.status === 'pending').length, 0);
    const prepared = await api(base + '/workbench/prepare', {expected_queue_revision: afterImport.queue_revision}, [200, 201]);
    const incomingRoot = prepared.root || prepared.candidate_root;
    assert.ok(incomingRoot, JSON.stringify(prepared));
    let context = await api(incomingRoot + '/context');
    context = await api(incomingRoot + '/draft', {expected_version: context.draft.draft_version,
      expected_candidate_scope_revision: context.candidate_scope_revision, decisions: [], selection_mode: 'all'}, 200, 'PATCH');
    const mergeBody = {expected_candidate_scope_revision: context.candidate_scope_revision,
      expected_draft_version: context.draft.draft_version, mode: 'all'};
    const mergePreview = await api(incomingRoot + '/preview', mergeBody);
    for (const key of ['preview_sha256', 'expected_binding_version', 'expected_query_revision']) mergeBody[key] = mergePreview[key];
    mergeBody.operation_uuid = randomUUID();
    const merged = await api(incomingRoot + '/accept', mergeBody);
    assert.deepEqual(await members(), [...oracle0.cells[0].epoch_ids, ...oracle1.cells[0].epoch_ids].sort());
    assert.equal((await api(`/epochs/${retainedCuration}?protocol_uuid=${protocol}`)).curation.included, false);
    assert.ok(beforeImport.every(key => merged.accepted_epoch_uuids?.includes(key) !== true));
    receipt.cases.push({name: 'H5 after predicate acceptance reruns accepted predicate and preserves additive merge', merged});
    receipt.passed = true;
  } finally {
    await fs.writeFile(path.join(state, `e2e-receipt-${runId}.json`), JSON.stringify(receipt, null, 2));
    await fs.writeFile(path.join(state, 'e2e-receipt.json'), JSON.stringify(receipt, null, 2));
  }
  console.log(JSON.stringify({passed: receipt.passed, cases: receipt.cases.map(row => row.name), state}));
}
main().catch(error => {console.error(error); process.exitCode = 1;});
