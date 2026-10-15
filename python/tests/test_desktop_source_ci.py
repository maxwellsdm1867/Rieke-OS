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
ROOT = Path(__file__).resolve().parents[2]


class SourceCITests(unittest.TestCase):
    def setUp(self):
        module_path = patch.object(sys, 'path', [str(ROOT / 'tools'), str(ROOT), *sys.path])
        module_path.start(); self.addCleanup(module_path.stop)
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
        trace_source = dict(commit=SHA, tree='b' * 40, dirty='', files={'app.py': 'd' * 64})
        self.trace_candidate = dict(status='passed', source_start=trace_source,
            source_end=copy.deepcopy(trace_source), harness={'fixture': 'same'},
            environment={'browser': 'same'}, dependencies={'lock': 'same'},
            fixture='prepared-geometry-v2', payload_sha256='e' * 64,
            cleanup={'server_closed': True, 'fixture_closed': True},
            samples=[{'exact': {key: True for key in ('all_emitted_point_bytes_match',
                'all_source_indices_match', 'whole_statistics_exact',
                'all_canvas_coordinates_exact', 'prepared_display_context_exact')},
                'cursor': {'all_tile_bytes_exact': True},
                'authority': {'foreground_extraction': {'requested': index + 1,
                    'entry_calls': index + 1, 'default_entry_calls': 0}},
                'trace': {'first_visible_ms': 20, 'first_raf_ms': 25, 'complete_ms': 30}}
                for index in range(3)])
        self.trace_baseline = copy.deepcopy(self.trace_candidate)
        for key in ('source_start', 'source_end'):
            self.trace_baseline[key]['commit'] = '4de896f2e0b4ea966b5a428c3d2314f93fba935f'
        from benchmark_prepared_geometry import compare
        self.trace_comparison = compare(self.trace_baseline, self.trace_candidate)
        self.jobs = {1: [dict(name=name, conclusion='success') for name in
            ['Adopted architecture contract discovery', 'frontend', 'python',
             'Scoped desktop lifecycle contracts', 'Apple Silicon native project lifecycle and transfer']],
            2: [dict(name=name, conclusion='success') for name in
                ['Backend million query regression', 'Browser million workflow regression',
                 'Actual million metadata query regression', 'macOS foreground trace regression']],
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
        if name.startswith('trace-macos-proof-'):
            self.assertEqual(name, 'trace-macos-proof-2-2')
            return {'baseline/receipt.json': self.trace_baseline,
                    'candidate/receipt.json': self.trace_candidate,
                    'comparison.json': self.trace_comparison}[filename]
        self.assertEqual(name, 'everyday-million-2-2')
        if with_digest: return self.benchmark, 'c' * 64
        return self.comparison if filename.endswith('comparison.json') else self.benchmark

    def check(self):
        return gate.require_source_ci(REPO, SHA, '3')

    def test_full_matching_evidence_passes(self):
        self.assertEqual(self.check(), dict(source_commit=SHA, regression_run=1, million_run=2, candidate_run=3))

    def test_package_import_uses_the_same_trace_gate(self):
        from tools import desktop_source_ci as package_gate
        with patch.object(package_gate, 'api', side_effect=self.api), \
             patch.object(package_gate, 'artifact', side_effect=self.artifact), \
             patch.object(sys, 'path', [path for path in sys.path if path != str(ROOT / 'tools')]):
            result = package_gate.require_source_ci(REPO, SHA, '3')
        self.assertEqual(result, self.check())

    def test_missing_or_wrong_attempt_trace_proof_blocks(self):
        def missing(repository, run, name, filename, **kwargs):
            if name.startswith('trace-macos-proof-'):
                raise ValueError('Missing or ambiguous CI artifact: ' + name)
            return self.artifact(repository, run, name, filename, **kwargs)
        with patch.object(gate, 'artifact', side_effect=missing):
            with self.assertRaisesRegex(ValueError, 'trace-macos-proof-2-2'): self.check()

    def test_trace_source_or_correctness_failure_blocks_publication(self):
        original = copy.deepcopy(self.trace_candidate)
        mutations = [lambda r: r.update(status='failed'),
            lambda r: r['source_start'].update(commit='f' * 40),
            lambda r: (r['source_start'].update(dirty=' M app.py'), r['source_end'].update(dirty=' M app.py')),
            lambda r: r['source_end'].update(tree='f' * 40),
            lambda r: r['samples'].pop(),
            lambda r: r['samples'][0]['authority']['foreground_extraction'].update(default_entry_calls=1),
            lambda r: r.update(environment={'browser': 'different'})]
        for mutation in mutations:
            self.trace_candidate = copy.deepcopy(original); mutation(self.trace_candidate)
            with self.assertRaises(ValueError): self.check()
        self.trace_candidate = original
        self.trace_baseline['source_start']['commit'] = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'pinned baseline'): self.check()

    def test_trace_comparison_is_recomputed_not_trusted(self):
        original = copy.deepcopy(self.trace_comparison)
        for value in ({}, {**original, 'status': 'review_required'},
                      {**original, 'metrics': []}):
            self.trace_comparison = value
            with self.assertRaisesRegex(ValueError, 'foreground trace comparison'): self.check()
        self.trace_comparison = original
        self.trace_candidate['samples'][2]['trace'] = {
            'first_visible_ms': 120, 'first_raf_ms': 125, 'complete_ms': 130}
        with self.assertRaisesRegex(ValueError, 'foreground trace comparison'): self.check()

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
    def archive(self, entries=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in entries or [('candidate/receipt.json', b'{ "status" : "passed" }\n')]:
                archive.writestr(name, raw)
        return output.getvalue()

    def ports(self, raw, *, name='proof', declared=None, digest=None, status=0):
        row = {'id': 7, 'name': name, 'expired': False,
               'size_in_bytes': len(raw) if declared is None else declared}
        if digest is not None: row['digest'] = digest
        process = unittest.mock.Mock()
        process.stdout = io.BytesIO(raw)
        process.wait.return_value = status
        process.poll.return_value = status
        return patch.object(gate, 'api', return_value={'artifacts': [row]}), \
            patch.object(gate.subprocess, 'Popen', return_value=process)

    def test_digest_binds_original_member_bytes_not_reserialized_json(self):
        raw = b'{ "status" : "passed" }\n'; archive = self.archive()
        api, process = self.ports(archive, digest='sha256:' + hashlib.sha256(archive).hexdigest())
        with api, process:
            parsed, digest = gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json', with_digest=True)
        self.assertEqual(parsed, {'status': 'passed'})
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(digest, hashlib.sha256(json.dumps(parsed).encode()).hexdigest())

    def test_only_exact_diagnostic_family_gets_larger_disk_budget(self):
        self.assertEqual(gate.SMALL_ARCHIVE_LIMIT, 16 * 1024 * 1024)
        self.assertEqual(gate.DIAGNOSTIC_ARCHIVE_LIMIT, 256 * 1024 * 1024)
        self.assertEqual(gate.MEMBER_LIMIT, 8 * 1024 * 1024)
        raw = self.archive()
        for name in ('proof', 'everyday-million-2-1', 'everyday-million-2-2'):
            api, process = self.ports(raw, name=name)
            with api, process as download, patch.object(gate, 'SMALL_ARCHIVE_LIMIT', len(raw) - 1):
                if name == 'everyday-million-2-1':
                    self.assertEqual(gate.artifact(REPO, {'id': 2, 'run_attempt': 1}, name,
                                                  'candidate/receipt.json')['status'], 'passed')
                else:
                    with self.assertRaisesRegex(ValueError, 'transport bound'):
                        gate.artifact(REPO, {'id': 2, 'run_attempt': 1}, name, 'candidate/receipt.json')
                    download.assert_not_called()

    def test_actual_oversize_size_mismatch_digest_and_transport_errors_refuse(self):
        raw = self.archive()
        for options, message in [({'declared': len(raw) - 1}, 'size differs'),
                ({'declared': len(raw) + 1}, 'size differs'),
                ({'digest': 'sha256:' + '0' * 64}, 'digest differs'),
                ({'digest': 'invalid'}, 'Malformed'), ({'status': 1}, 'download failed')]:
            api, process = self.ports(raw, **options)
            with api, process, self.assertRaisesRegex(ValueError, message):
                gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json')

    def test_actual_byte_limit_stops_running_download_and_cleans_partial_file(self):
        raw = self.archive()
        api, process = self.ports(raw, declared=1)
        with api, process as download, patch.object(gate, 'SMALL_ARCHIVE_LIMIT', len(raw) - 1):
            download.return_value.poll.return_value = None
            with self.assertRaisesRegex(ValueError, 'actual-byte transport bound'):
                with gate._artifact_scope():
                    folder = gate._ARTIFACT_CACHE.get()[0]
                    gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json')
            download.return_value.kill.assert_called_once()
            download.return_value.wait.assert_called_once()
            self.assertTrue(download.return_value.stdout.closed)
            self.assertFalse(folder.exists())
        api, process = self.ports(raw, declared=1)
        with api, process, patch.object(gate, 'SMALL_ARCHIVE_LIMIT', len(raw) - 1):
            with self.assertRaisesRegex(ValueError, 'actual-byte transport bound'):
                gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json')

    def test_duplicate_missing_and_oversized_members_refuse_without_extracting(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            duplicate = self.archive([('candidate/receipt.json', b'{}'), ('candidate/receipt.json', b'{}')])
        for raw, member, error in [(duplicate, 'candidate/receipt.json', 'duplicate'),
                (self.archive(), 'missing.json', 'Missing'),
                (self.archive([('candidate/receipt.json', b' ' * (gate.MEMBER_LIMIT + 1))]),
                 'candidate/receipt.json', 'metadata bound')]:
            api, process = self.ports(raw)
            with api, process, patch.object(zipfile.ZipFile, 'extract') as extract, \
                 patch.object(zipfile.ZipFile, 'extractall') as extractall:
                with self.assertRaisesRegex(ValueError, error):
                    gate.artifact(REPO, {'id': 2}, 'proof', member)
                extract.assert_not_called(); extractall.assert_not_called()

    def test_cache_is_scoped_and_removed_on_success_or_failure(self):
        raw = self.archive()
        for fail in (False, True):
            api, process = self.ports(raw)
            with api, process as download:
                try:
                    with gate._artifact_scope():
                        folder = gate._ARTIFACT_CACHE.get()[0]
                        for _ in range(2):
                            gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json')
                        self.assertEqual(download.call_count, 1)
                        self.assertTrue(folder.exists())
                        if fail: raise ValueError('owned failure')
                except ValueError:
                    if not fail: raise
                self.assertFalse(folder.exists())
                self.assertIsNone(gate._ARTIFACT_CACHE.get())
            api, process = self.ports(raw)
            with api, process as fresh:
                gate.artifact(REPO, {'id': 2}, 'proof', 'candidate/receipt.json')
                fresh.assert_called_once()


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
