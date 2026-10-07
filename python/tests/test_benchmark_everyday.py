"""Evidence/refusal tests for the stress runner; never build a million-row fixture."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
from tools import benchmark_everyday as bench


class EverydayBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='everyday-harness-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        (self.repo / 'python').mkdir(parents=True)
        (self.repo / 'python' / 'application.py').write_text('VALUE = 1\n')
        for args in [('init', '-q'), ('add', '.'),
                     ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                      'commit', '-qm', 'Disposable source')]:
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        self.cfg = bench.config()
        self.source = bench.source(self.repo)
        self.env = bench.environment()

    def lane(self, name):
        operations = {}
        for case in self.cfg['cases'][name]:
            count = 1 if case == 'tree.first_root' else self.cfg['samples']
            operations[case] = {'milliseconds': [100.0] * count, 'median_ms': 100.0,
                                'oracle_passed': True, 'answer_sha256': ['a' * 64] * count}
        return {'status': 'passed', 'lane': name, 'epochs': 1_000_000,
                'operations': operations, 'guards': dict.fromkeys(self.cfg['guards'][name], True),
                'h5_open_attempts': [], 'peak_rss_bytes': 100_000_000,
                'setup_seconds': 1.0, 'elapsed_seconds': 2.0}

    def receipt(self, name):
        directory = self.root / name
        directory.mkdir()
        harness = {p: bench.sha((ROOT / p).read_bytes()) for p in bench.HARNESS}
        receipt = {'format': bench.FORMAT, 'status': 'passed', 'config': copy.deepcopy(self.cfg),
                   'source_root': str(self.repo), 'source_start': copy.deepcopy(self.source),
                   'source_end': copy.deepcopy(self.source), 'environment': copy.deepcopy(self.env),
                   'harness_start': harness, 'harness_end': dict(harness), 'lanes': {}}
        for lane in ('tree', 'typed'):
            data = self.lane(lane)
            bench.write(directory / (lane + '.json'), data)
            log = directory / (lane + '.log')
            log.write_text('Disposable evidence validator fixture; no benchmark was run.\n')
            receipt['lanes'][lane] = {'result': data,
                                     'sha256': bench.sha((directory / (lane + '.json')).read_bytes()),
                                     'log_sha256': bench.sha(log.read_bytes())}
        path = directory / 'receipt.json'
        self.seal_provenance(path, receipt)
        return path, receipt

    def seal_provenance(self, path, receipt):
        provenance = path.parent / 'provenance.json'
        bench.write(provenance, {key: receipt[key] for key in bench.PROVENANCE})
        receipt['provenance_sha256'] = bench.sha(provenance.read_bytes())
        bench.write(path, receipt)

    def update_lane(self, path, receipt, lane):
        raw = path.parent / (lane + '.json')
        bench.write(raw, receipt['lanes'][lane]['result'])
        receipt['lanes'][lane]['sha256'] = bench.sha(raw.read_bytes())
        bench.write(path, receipt)

    def test_complete_matched_evidence_compares_without_worker(self):
        baseline, _ = self.receipt('baseline')
        candidate, _ = self.receipt('candidate')
        result = bench.compare(baseline, candidate, self.root / 'comparison.json')
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['review_required'], [])
        self.assertEqual(len(result['metrics']), sum(map(len, self.cfg['cases'].values())) + 4)
        self.assertIn('not native/UI/release qualification', result['qualification'])

    def test_incomplete_failed_and_wrong_scale_lanes_refused(self):
        for lane in ('tree', 'typed'):
            for update in ({'status': 'running'}, {'status': 'failed'}, {'epochs': 999_999},
                           {'epochs': 100_000}, {'lane': 'other'}):
                with self.subTest(lane=lane, update=update):
                    data = self.lane(lane)
                    data.update(update)
                    with self.assertRaises(ValueError):
                        bench.validate_lane(lane, data, self.cfg)

    def test_missing_extra_cases_failed_oracles_guards_and_h5_refused(self):
        for lane in ('tree', 'typed'):
            case = self.cfg['cases'][lane][0]
            guard = self.cfg['guards'][lane][0]
            changes = [lambda d: d['operations'].pop(case),
                       lambda d: d['operations'].update(unregistered=d['operations'][case]),
                       lambda d: d['operations'][case].update(oracle_passed=False),
                       lambda d: d['guards'].pop(guard),
                       lambda d: d['guards'].update({guard: False}),
                       lambda d: d.update(h5_open_attempts=['never-open.h5'])]
            for i, change in enumerate(changes):
                with self.subTest(lane=lane, fault=i):
                    data = self.lane(lane)
                    change(data)
                    with self.assertRaises(ValueError):
                        bench.validate_lane(lane, data, self.cfg)

    def test_short_nonfinite_negative_boolean_and_inconsistent_samples_refused(self):
        case = 'typed.first'
        for samples in ([], [1], [float('nan')] * 3, [float('inf')] * 3, [-1] * 3, [True] * 3):
            with self.subTest(samples=samples):
                data = self.lane('typed')
                data['operations'][case]['milliseconds'] = samples
                with self.assertRaises(ValueError):
                    bench.validate_lane('typed', data, self.cfg)
        for change in ({'median_ms': 99}, {'answer_sha256': []}):
            data = self.lane('typed')
            data['operations'][case].update(change)
            with self.assertRaises(ValueError):
                bench.validate_lane('typed', data, self.cfg)

    def test_malformed_answer_digests_refused(self):
        for digest in ('', 'a' * 63, 'g' * 64, None, {}, 12):
            with self.subTest(digest=digest):
                data = self.lane('typed')
                data['operations']['typed.first']['answer_sha256'][0] = digest
                with self.assertRaisesRegex(ValueError, 'invalid raw samples/oracle'):
                    bench.validate_lane('typed', data, self.cfg)

    def test_recorded_resource_cap_overages_refused(self):
        for metric, limit in (('peak_rss_bytes', self.cfg['max_rss_bytes']),
                              ('elapsed_seconds', self.cfg['max_worker_seconds'])):
            with self.subTest(metric=metric):
                data = self.lane('tree')
                data[metric] = limit
                bench.validate_lane('tree', data, self.cfg)
                data[metric] = limit + 1
                with self.assertRaisesRegex(ValueError, 'resource cap exceeded'):
                    bench.validate_lane('tree', data, self.cfg)

    def test_missing_cpu_identity_refused(self):
        for cpu in ('', None):
            with self.subTest(cpu=cpu):
                environment = copy.deepcopy(self.env)
                environment['cpu_model'] = cpu
                with self.assertRaises(ValueError):
                    bench.validate_environment(environment)
        environment = copy.deepcopy(self.env)
        environment.pop('cpu_model')
        with self.assertRaises(ValueError):
            bench.validate_environment(environment)

    def test_raw_and_log_tampering_refused(self):
        for filename in ('tree.json', 'typed.json', 'tree.log', 'typed.log'):
            with self.subTest(file=filename):
                path, _ = self.receipt(filename.replace('.', '-'))
                evidence = path.parent / filename
                evidence.write_bytes(evidence.read_bytes() + b'\n')
                with self.assertRaisesRegex(ValueError, 'evidence changed'):
                    bench.load_receipt(path)

    def test_resealed_raw_cannot_disagree_with_embedded_evidence(self):
        path, receipt = self.receipt('mismatch')
        raw = path.parent / 'typed.json'
        changed = copy.deepcopy(receipt['lanes']['typed']['result'])
        changed['operations']['typed.first'].update(milliseconds=[90] * 3, median_ms=90)
        bench.write(raw, changed)
        receipt['lanes']['typed']['sha256'] = bench.sha(raw.read_bytes())
        bench.write(path, receipt)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            bench.load_receipt(path)

    def test_incomplete_receipt_missing_lane_and_source_changes_refused(self):
        changes = [lambda r: r.update(status='running'), lambda r: r.update(status='failed'),
                   lambda r: r['lanes'].pop('typed'),
                   lambda r: r['source_end'].update(commit='b' * 40),
                   lambda r: r['harness_end'].update({'tools/benchmark_everyday.py': 'b' * 64}),
                   lambda r: r['config'].update(epochs=100)]
        for i, change in enumerate(changes):
            with self.subTest(fault=i):
                path, receipt = self.receipt('incomplete-' + str(i))
                change(receipt)
                bench.write(path, receipt)
                with self.assertRaises(ValueError):
                    bench.load_receipt(path)

    def test_incompatible_environment_refused_before_comparison(self):
        baseline, _ = self.receipt('baseline')
        for field, value in [('python', 'different Python'), ('sqlite', 'other SQLite'),
                             ('os', 'other OS'), ('machine', 'other architecture'),
                             ('host', 'other host'), ('cpu_model', 'Other CPU'), ('cpu_count', 999),
                             ('packages', [['fixture', '1.0']])]:
            with self.subTest(field=field):
                candidate, receipt = self.receipt('candidate-' + field)
                receipt['environment'][field] = value
                self.seal_provenance(candidate, receipt)
                output = self.root / ('comparison-' + field + '.json')
                with self.assertRaisesRegex(ValueError, 'environment'):
                    bench.compare(baseline, candidate, output)
                self.assertFalse(output.exists())

    def test_single_case_regression_cannot_be_averaged_away(self):
        baseline, _ = self.receipt('baseline')
        candidate, receipt = self.receipt('candidate')
        for lane in ('tree', 'typed'):
            for operation in receipt['lanes'][lane]['result']['operations'].values():
                operation.update(milliseconds=[1] * len(operation['milliseconds']), median_ms=1)
            self.update_lane(candidate, receipt, lane)
        receipt['lanes']['typed']['result']['operations']['typed.deep'].update(
            milliseconds=[140] * 3, median_ms=140)
        self.update_lane(candidate, receipt, 'typed')
        result = bench.compare(baseline, candidate, self.root / 'comparison.json')
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['review_required'], ['typed.deep'])
        metric = next(m for m in result['metrics'] if m['case'] == 'typed.deep')
        self.assertEqual(metric['threshold'], 125)

    def test_missing_or_forged_source_identity_refused(self):
        for i, change in enumerate([
            lambda s: s.clear(),
            lambda s: s.update(sha256='f' * 64),
            lambda s: s.update(commit='f' * 40),
            lambda s: s.update(tree='f' * 40),
        ]):
            with self.subTest(fault=i):
                path, receipt = self.receipt('source-fault-' + str(i))
                change(receipt['source_start'])
                receipt['source_end'] = copy.deepcopy(receipt['source_start'])
                bench.write(path, receipt)
                with self.assertRaises(ValueError):
                    bench.load_receipt(path)

    def test_dirty_baseline_refused_but_dirty_candidate_remains_diagnostic(self):
        baseline, before = self.receipt('baseline')
        candidate, after = self.receipt('candidate')
        for key in ('source_start', 'source_end'):
            after[key]['status'] = ' M python/application.py'
        self.seal_provenance(candidate, after)
        result = bench.compare(baseline, candidate, self.root / 'diagnostic.json')
        self.assertEqual(result['status'], 'passed')
        for key in ('source_start', 'source_end'):
            before[key]['status'] = ' M python/application.py'
        self.seal_provenance(baseline, before)
        with self.assertRaisesRegex(ValueError, 'Baseline source must be clean'):
            bench.compare(baseline, candidate, self.root / 'invalid.json')

    def test_source_manifest_binds_dirty_new_and_deleted_application_files(self):
        original = bench.source(self.repo)
        application = self.repo / 'python/application.py'
        application.write_text('VALUE = 2\n')
        dirty = bench.source(self.repo)
        self.assertEqual(original['commit'], dirty['commit'])
        self.assertNotEqual(original['sha256'], dirty['sha256'])
        added = self.repo / 'python/new_module.py'
        added.write_text('NEW = True\n')
        with_added = bench.source(self.repo)
        self.assertIn('python/new_module.py', with_added['files'])
        self.assertNotEqual(dirty['sha256'], with_added['sha256'])
        application.unlink()
        deleted = bench.source(self.repo)
        self.assertEqual(deleted['files']['python/application.py'], 'deleted')
        self.assertNotEqual(with_added['sha256'], deleted['sha256'])

    def test_failed_worker_retains_failed_receipt_and_does_not_start_next_lane(self):
        process = Mock()
        process.poll.return_value = 7
        process.wait.return_value = 7
        output = self.root / 'failed-run'
        # Patch source too: it uses subprocess.check_output, which shares Popen.
        with patch.object(bench, 'source', return_value=self.source), \
             patch.object(bench, 'environment', return_value=self.env), \
             patch.object(bench.subprocess, 'Popen', return_value=process) as launch:
            with self.assertRaisesRegex(RuntimeError, 'worker failed'):
                bench.run(self.repo, output)
        launch.assert_called_once()
        receipt = json.loads((output / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'failed')
        self.assertIn('worker failed', receipt['error'])
        self.assertEqual(receipt['lanes'], {})
        self.assertTrue((output / 'tree.log').exists())
        self.assertFalse((output / 'typed.log').exists())
        with self.assertRaises(ValueError):
            bench.load_receipt(output / 'receipt.json')

    def test_matched_but_empty_environment_is_not_comparable(self):
        baseline, before = self.receipt('baseline')
        candidate, after = self.receipt('candidate')
        for path, receipt in ((baseline, before), (candidate, after)):
            receipt['environment'] = {}
            bench.write(path, receipt)
        with self.assertRaises(ValueError):
            bench.compare(baseline, candidate, self.root / 'comparison.json')


if __name__ == '__main__':
    unittest.main()
