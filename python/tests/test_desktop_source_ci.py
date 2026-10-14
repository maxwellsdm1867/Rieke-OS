"""Exact-source publication refuses missing, stale, skipped and failed evidence."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import desktop_source_ci as gate
import desktop_test_release as testing
sys.path.pop(0)

SHA = 'a' * 40
REPO = 'maxwellsdm1867/Rieke-OS'


class SourceCITests(unittest.TestCase):
    def setUp(self):
        self.runs = {name: dict(id=index, run_attempt=2, path='.github/workflows/' + name,
            status='completed', conclusion='success', head_sha=SHA) for index, name in
            enumerate(['workspace-ci.yml', 'everyday-million.yml', 'desktop-candidate.yml'], 1)}
        self.plans = {
            'architecture-plan.json': dict(head=SHA, dirty=False, selection='all', source_changed=True),
            'release-plan.json': dict(head=SHA, build_required=True, updater=True, database=False,
                                      packaging=False, full_ui=False)}
        source = dict(commit=SHA, status='')
        self.benchmark = dict(status='passed', source_start=source, source_end=copy.deepcopy(source))
        self.comparison = dict(status='passed', review_required=[], candidate_commit=SHA,
                               candidate_receipt_sha256='c' * 64)
        self.jobs = {1: [dict(name=name, conclusion='success') for name in
            ['Adopted architecture contract discovery', 'frontend', 'python',
             'Scoped desktop lifecycle contracts', 'Apple Silicon native project lifecycle and transfer']],
            2: [dict(name=name, conclusion='success') for name in
                ['Backend million query regression', 'Browser million workflow regression',
                 'Actual million metadata query regression']],
            3: [dict(name=name, conclusion='success') for name in ['build', 'Verify smoke', 'Verify updater']]}
        self.api_patch = patch.object(gate, 'api', side_effect=self.api)
        self.artifact_patch = patch.object(gate, 'artifact', side_effect=self.artifact)
        self.api_mock = self.api_patch.start(); self.addCleanup(self.api_patch.stop)
        self.artifact_mock = self.artifact_patch.start(); self.addCleanup(self.artifact_patch.stop)

    def api(self, path):
        if '/actions/workflows/' in path:
            name = path.split('/actions/workflows/')[1].split('/')[0]
            self.assertIn('head_sha=' + SHA, path)
            return {'workflow_runs': [self.runs[name]]}
        if '/attempts/' in path:
            identity = int(path.split('/actions/runs/')[1].split('/')[0])
            self.assertIn('/attempts/2/jobs?', path)
            return {'jobs': self.jobs[identity]}
        self.assertEqual(path, f'repos/{REPO}/actions/runs/3')
        return self.runs['desktop-candidate.yml']

    def artifact(self, repository, run, name, filename, *, with_digest=False):
        self.assertEqual(repository, REPO)
        if filename in self.plans: return self.plans[filename]
        self.assertEqual(name, 'everyday-million-2-2')
        if with_digest: return self.benchmark, 'c' * 64
        return self.comparison if filename.endswith('comparison.json') else self.benchmark

    def check(self):
        return gate.require_source_ci(REPO, SHA, '3')

    def test_full_matching_evidence_passes(self):
        self.assertEqual(self.check(), dict(source_commit=SHA, regression_run=1, million_run=2, candidate_run=3))

    def test_latest_required_run_must_finish_successfully(self):
        for workflow in self.runs:
            for status, conclusion in [('queued', None), ('in_progress', None), ('completed', 'failure'),
                                       ('completed', 'cancelled'), ('completed', 'timed_out'), ('completed', 'skipped')]:
                with self.subTest(workflow=workflow, status=status, conclusion=conclusion):
                    saved = self.runs[workflow].copy()
                    self.runs[workflow].update(status=status, conclusion=conclusion)
                    with self.assertRaises(ValueError): self.check()
                    self.runs[workflow] = saved

    def test_absent_or_wrong_source_run_is_not_a_green_substitute(self):
        with patch.object(gate, 'api', return_value={'workflow_runs': []}):
            with self.assertRaisesRegex(ValueError, 'Missing exact-source'): self.check()
        self.runs['workspace-ci.yml']['head_sha'] = 'b' * 40
        with self.assertRaises(ValueError): self.check()

    def test_pr_merge_docs_plan_or_skipped_native_job_cannot_qualify(self):
        original = self.plans['architecture-plan.json'].copy()
        for key, value in [('head', 'b' * 40), ('dirty', True), ('selection', 'changed'), ('source_changed', False)]:
            self.plans['architecture-plan.json'] = {**original, key: value}
            with self.assertRaisesRegex(ValueError, 'full_checks'): self.check()
        self.plans['architecture-plan.json'] = original
        self.jobs[1][-1]['conclusion'] = 'skipped'
        with self.assertRaisesRegex(ValueError, 'required successful job'): self.check()

    def test_wrong_dirty_changed_or_failed_benchmark_source_blocks(self):
        original = copy.deepcopy(self.benchmark)
        variants = [dict(status='failed'), dict(source_start=dict(commit='b' * 40, status='')),
                    dict(source_start=dict(commit=SHA, status=' M file')),
                    dict(source_end=dict(commit='b' * 40, status=''))]
        for change in variants:
            self.benchmark = {**original, **change}
            with self.assertRaisesRegex(ValueError, 'exact clean publication source'): self.check()

    def test_each_performance_family_and_aggregate_must_succeed_in_this_attempt(self):
        original = copy.deepcopy(self.jobs[2])
        for index, job in enumerate(original):
            for conclusion in (None, 'skipped', 'failure', 'cancelled', 'timed_out', 'neutral'):
                with self.subTest(job=job['name'], conclusion=conclusion):
                    self.jobs[2] = copy.deepcopy(original)
                    self.jobs[2][index]['conclusion'] = conclusion
                    with self.assertRaisesRegex(ValueError, 'required successful job'):
                        self.check()
            for duplicate in (False, True):
                with self.subTest(job=job['name'], duplicate=duplicate):
                    self.jobs[2] = copy.deepcopy(original)
                    if duplicate:
                        self.jobs[2].append(job.copy())
                    else:
                        self.jobs[2].pop(index)
                    with self.assertRaisesRegex(ValueError, 'required successful job'):
                        self.check()
        self.jobs[2] = original
        self.check()

    def test_review_trigger_blocks_even_if_workflow_claims_success(self):
        self.comparison.update(status='review_required', review_required=['selection/total_ms'])
        with self.assertRaisesRegex(ValueError, 'performance comparison'): self.check()

    def test_focused_candidate_or_missing_selected_check_cannot_qualify(self):
        self.jobs[3][0]['conclusion'] = 'skipped'
        with self.assertRaisesRegex(ValueError, 'build'): self.check()
        self.jobs[3][0]['conclusion'] = 'success'
        self.jobs[3].pop()
        with self.assertRaisesRegex(ValueError, 'Verify updater'): self.check()

    def test_each_comparison_must_bind_the_exact_candidate_receipt(self):
        for filename in ('pinned-comparison.json', 'previous-comparison.json',
                         'workflow-pinned-comparison.json', 'workflow-previous-comparison.json'):
            for change in ({'candidate_commit': 'b' * 40}, {'candidate_receipt_sha256': 'd' * 64}):
                with self.subTest(filename=filename, change=change):
                    def changed(repository, run, name, member, **kwargs):
                        result = self.artifact(repository, run, name, member, **kwargs)
                        return {**result, **change} if member == filename else result
                    with patch.object(gate, 'artifact', side_effect=changed):
                        with self.assertRaisesRegex(ValueError, 'exact candidate receipt'): self.check()

    def test_query_comparison_can_bind_source_through_receipt_hash(self):
        def query_schema(repository, run, name, filename, **kwargs):
            result = self.artifact(repository, run, name, filename, **kwargs)
            if filename in ('pinned-comparison.json', 'previous-comparison.json'):
                return {key: value for key, value in result.items() if key != 'candidate_commit'}
            return result
        with patch.object(gate, 'artifact', side_effect=query_schema):
            self.check()

    def test_incomplete_or_wrong_candidate_plan_blocks(self):
        self.plans['release-plan.json']['head'] = 'b' * 40
        with self.assertRaises(ValueError): self.check()
        self.plans['release-plan.json']['head'] = SHA
        del self.plans['release-plan.json']['packaging']
        with self.assertRaises(ValueError): self.check()

    def test_immutable_tag_must_resolve_to_qualified_source(self):
        tag = 'desktop-test-v0.1.14'
        with patch.object(gate, 'api', return_value=[]):
            gate.require_tag(REPO, tag, SHA, allow_missing=True)
            with self.assertRaises(ValueError): gate.require_tag(REPO, tag, SHA)
        ref = dict(ref='refs/tags/' + tag, object=dict(type='commit', sha='b' * 40))
        with patch.object(gate, 'api', return_value=[ref]):
            with self.assertRaises(ValueError): gate.require_tag(REPO, tag, SHA)
            ref['object']['sha'] = SHA
            gate.require_tag(REPO, tag, SHA)


class ArtifactProofTests(unittest.TestCase):
    def test_digest_binds_original_member_bytes_not_reserialized_json(self):
        raw = b'{ "status" : "passed" }\n'
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('candidate/receipt.json', raw)
        listing = {'artifacts': [{'id': 7, 'name': 'proof', 'expired': False,
                                 'size_in_bytes': len(archive.getvalue())}]}
        with patch.object(gate, 'api', return_value=listing), \
             patch.object(gate.subprocess, 'check_output', return_value=archive.getvalue()):
            parsed, digest = gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json', with_digest=True)
        self.assertEqual(parsed, {'status': 'passed'})
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(digest, hashlib.sha256(json.dumps(parsed).encode()).hexdigest())


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / 'Disco-0.1.14-arm64.zip'; self.archive.write_bytes(b'owned fixture archive')
        self.notes = self.root / 'notes.md'; self.notes.write_text('Owned testing notes')
        self.output = self.root / 'desktop-release.json'
        self.descriptor = dict(source_commit=SHA, source_dirty=False, application_version='0.1.14')
        self.mutations = []
        def mutate(command, **kwargs): self.mutations.append(command)
        def remote(path):
            self.assertEqual(path, f'repos/{REPO}/releases/41')
            command = self.mutations[0]
            paths = [Path(name) for name in command[command.index('--notes-file') + 2:]]
            return {'id': 41, 'draft': True, 'tag_name': 'desktop-test-v0.1.14',
                    'target_commitish': SHA, 'assets': [dict(name=p.name, digest='sha256:' + hashlib.sha256(p.read_bytes()).hexdigest(),
                                   size=p.stat().st_size) for p in paths]}
        for owner, name, kwargs in [
            (testing, 'build_descriptor', dict(return_value=self.descriptor)),
            (gate, 'require_source_ci', dict(return_value={'candidate_run': 3})),
            (gate, 'artifact', dict(return_value=self.descriptor.copy())),
            (gate, 'require_tag', dict(return_value=None)),
            (gate, 'api', dict(side_effect=remote)),
            (testing.subprocess, 'run', dict(side_effect=mutate)),
            (testing.subprocess, 'check_output', dict(return_value=json.dumps({
                'databaseId': 41, 'tagName': 'desktop-test-v0.1.14',
                'isDraft': True, 'targetCommitish': SHA})))]:
            started = patch.object(owner, name, **kwargs); mock = started.start(); self.addCleanup(started.stop)
            setattr(self, name + '_mock', mock)

    def publish(self):
        return testing.publish(self.root / 'Disco.app', self.archive, self.output, self.notes, '3')

    def test_failed_source_ci_never_creates_release_or_descriptor(self):
        self.require_source_ci_mock.side_effect = ValueError('required CI failed')
        with self.assertRaisesRegex(ValueError, 'required CI failed'): self.publish()
        self.assertEqual(self.mutations, [])
        self.assertFalse(self.output.exists())

    def test_exact_candidate_bytes_must_match_before_mutation(self):
        self.artifact_mock.return_value = {**self.descriptor, 'source_commit': 'b' * 40}
        with self.assertRaisesRegex(ValueError, 'Local archive differs'): self.publish()
        self.assertEqual(self.mutations, [])

    def test_success_rechecks_ci_and_tag_before_public_visibility(self):
        self.publish()
        self.assertEqual([row[2] for row in self.mutations], ['create', 'edit'])
        self.assertIn('--draft', self.mutations[0]); self.assertIn('--draft=false', self.mutations[1])
        self.assertEqual(self.require_source_ci_mock.call_count, 2)
        self.assertEqual(self.require_tag_mock.call_count, 2)
        self.assertEqual(self.require_tag_mock.call_args_list[0].kwargs, {})
        self.assertEqual(self.check_output_mock.call_args.args[0][:3], ['gh', 'release', 'view'])

    def test_missing_preexisting_tag_blocks_before_draft_creation(self):
        self.require_tag_mock.side_effect = ValueError('Missing publication tag')
        with self.assertRaisesRegex(ValueError, 'Missing publication tag'): self.publish()
        self.assertEqual(self.mutations, [])

    def test_draft_lookup_cannot_borrow_another_release_or_published_release(self):
        original = json.loads(self.check_output_mock.return_value)
        for key, value in [('databaseId', None), ('tagName', 'other'),
                           ('isDraft', False), ('targetCommitish', 'b' * 40)]:
            with self.subTest(key=key):
                self.mutations.clear()
                self.check_output_mock.return_value = json.dumps({**original, key: value})
                with self.assertRaisesRegex(ValueError, 'draft identity differs'): self.publish()
                self.assertEqual([row[2] for row in self.mutations], ['create'])

    def test_release_id_read_rechecks_draft_identity(self):
        self.api_mock.side_effect = None
        self.api_mock.return_value = {'id': 41, 'draft': False,
            'tag_name': 'desktop-test-v0.1.14', 'target_commitish': SHA, 'assets': []}
        with self.assertRaisesRegex(ValueError, 'draft identity differs'): self.publish()
        self.assertEqual([row[2] for row in self.mutations], ['create'])

    def test_new_failure_during_upload_keeps_release_draft(self):
        self.require_source_ci_mock.side_effect = [{'candidate_run': 3}, ValueError('new failing run')]
        with self.assertRaisesRegex(ValueError, 'new failing run'): self.publish()
        self.assertEqual([row[2] for row in self.mutations], ['create'])

    def test_remote_digest_mismatch_never_publishes(self):
        self.api_mock.return_value = {'id': 41, 'draft': True, 'tag_name': 'desktop-test-v0.1.14',
            'target_commitish': SHA, 'assets': []}; self.api_mock.side_effect = None
        with self.assertRaisesRegex(ValueError, 'Uploaded bytes differ'): self.publish()
        self.assertEqual([row[2] for row in self.mutations], ['create'])


if __name__ == '__main__': unittest.main()
