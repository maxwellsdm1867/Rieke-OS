"""Comparison/refusal tests for the route track; never build a million-row fixture."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import benchmark_routes as routes


def case(median, cold=None, counts=None, **extra):
    return {'status': 'passed', 'median_ms': median, 'cold_ms': cold, 'samples_ms': [median] * 3,
            'attestations': [2, 2, 2], 'bytes': [10, 10, 10], 'counts': counts or {'copy.deepcopy': 3}, **extra}


class RouteComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='route-harness-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = routes.config()
        source = {'commit': 'a' * 40, 'tree': 'b' * 40, 'status': '', 'files': {'python/x.py': 'c' * 64}, 'sha256': 'd' * 64}
        cases = {'epoch.detail': case(10.0, 20.0), 'explore.summaries_poll': case(50.0, counts={'sqlite.execute': 5}),
                 'explore.preview.missing_cell_type': case(30.0)}
        self.base = {'format': routes.FORMAT, 'status': 'passed', 'config': self.cfg, 'environment': {'cpu_model': 'x'},
                     'harness_start': {}, 'source_start': source, 'source_end': source,
                     'profiles': {'smoke': {'profile': self.cfg['profiles']['smoke'], 'load_before': None,
                                            'result': {'status': 'passed', 'cases': cases,
                                                       'predicate_counts': {'missing_cell_type': {'preview': {'matched_count': 0}},
                                                                            'eq_cell': {'preview': {'matched_count': 100}}}}}}}

    def compare(self, candidate):
        paths = []
        for name, value in (('baseline.json', self.base), ('candidate.json', candidate)):
            path = self.root / name
            path.write_text(json.dumps(value))
            paths.append(path)
        with patch.object(routes, 'load_receipt', side_effect=lambda path, **_: json.loads(path.read_text())):
            return routes.compare(paths[0], paths[1], self.root / f'comparison-{len(list(self.root.iterdir()))}.json')

    def candidate(self):
        value = copy.deepcopy(self.base)
        value['source_start'] = value['source_end'] = {**value['source_start'], 'commit': 'e' * 40}
        return value

    def test_identical_evidence_passes(self):
        result = self.compare(self.candidate())
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['count_increases'], [])

    def test_slow_median_and_cold_require_review(self):
        candidate = self.candidate()
        cases = candidate['profiles']['smoke']['result']['cases']
        cases['epoch.detail'].update(median_ms=16.0, cold_ms=26.0)  # >25% and >5 ms
        result = self.compare(candidate)
        self.assertEqual(result['review_required'], ['smoke/epoch.detail/median_ms', 'smoke/epoch.detail/cold_ms'])

    def test_count_increase_is_listed_but_poll_counts_are_not_compared(self):
        candidate = self.candidate()
        cases = candidate['profiles']['smoke']['result']['cases']
        cases['epoch.detail']['counts'] = {'copy.deepcopy': 30}
        self.base['profiles']['smoke']['result']['cases']['explore.summaries_poll']['counts_variable'] = 'timing'
        cases['explore.summaries_poll']['counts'] = {'sqlite.execute': 50}
        result = self.compare(candidate)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([(row['case'], row['count']) for row in result['count_increases']],
                         [('epoch.detail', 'copy.deepcopy')])

    def test_contract_count_change_is_expected_but_other_count_change_is_flagged(self):
        candidate = self.candidate()
        counts = candidate['profiles']['smoke']['result']['predicate_counts']
        counts['missing_cell_type'] = {'preview': {'matched_count': 7}}
        result = self.compare(candidate)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([row['predicate'] for row in result['predicate_count_changes']], ['missing_cell_type'])
        counts['eq_cell'] = {'preview': {'matched_count': 99}}
        result = self.compare(candidate)
        self.assertEqual(result['review_required'], ['smoke/predicate_counts/eq_cell'])

    def test_case_coverage_and_dirty_baseline_are_refused(self):
        candidate = self.candidate()
        del candidate['profiles']['smoke']['result']['cases']['epoch.detail']
        with self.assertRaisesRegex(ValueError, 'case coverage'):
            self.compare(candidate)
        self.base['source_start'] = {**self.base['source_start'], 'status': ' M python/x.py'}
        with self.assertRaisesRegex(ValueError, 'clean'):
            self.compare(self.candidate())

    def test_registry_profiles_cover_flat_line_sizes(self):
        profiles = self.cfg['profiles']
        self.assertEqual({profiles[name]['epochs'] for name in self.cfg['default_profiles']}, {1_000_000, 100_000})
        self.assertIn(20_000, {profiles[name]['protocol_epochs'] for name in self.cfg['default_profiles']})
        self.assertTrue(set(self.cfg['expected_by_contract']) <= {'ne_cell_type', 'exists_cell_type', 'missing_cell_type', 'missing_recorded'})


class CaseGroupTests(unittest.TestCase):
    def group(self, cases, **extra):
        return {'result': {'format': 'f', 'status': 'passed', 'epochs': 1, 'protocol_epochs': 1, 'samples': 3,
                           'cases': {name: case(1.0) for name in cases}, **extra}}

    def test_groups_merge_in_order_and_keep_each_peak(self):
        merged = routes.merge_groups({'explore': self.group(['explore.page.x'], predicate_counts={'x': 1}, peak_rss_bytes=5),
                                      'reads': self.group(['epoch.detail'], peak_rss_bytes=7)})
        self.assertEqual(list(merged['cases']), ['explore.page.x', 'epoch.detail'])
        self.assertEqual(merged['case_group_of'], {'explore.page.x': 'explore', 'epoch.detail': 'reads'})
        self.assertEqual(merged['predicate_counts'], {'x': 1})
        self.assertEqual(merged['peak_rss_bytes_by_group'], {'explore': 5, 'reads': 7})
        self.assertEqual(merged['status'], 'passed')

    def test_overlapping_or_failed_groups_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, 'both'):
            routes.merge_groups({'a': self.group(['epoch.detail']), 'b': self.group(['epoch.detail'])})
        failed = self.group(['tree.root']); failed['result']['status'] = 'failed'
        self.assertEqual(routes.merge_groups({'a': self.group(['epoch.detail']), 'b': failed})['status'], 'failed')

    def test_registry_groups_are_disjoint_prefixes_and_million_profile_is_grouped(self):
        cfg = routes.config()
        prefixes = [p for group in cfg['case_groups'].values() for p in group]
        self.assertEqual(len(prefixes), len(set(prefixes)))
        self.assertTrue(cfg['profiles']['1m-protocol-1m']['grouped'])
        self.assertTrue(cfg['profiles']['smoke-grouped']['grouped'])


class ScalingTests(unittest.TestCase):
    def receipt(self, cases):
        cfg = routes.config()
        profiles = {}
        for name, epochs, protocol, scale in (('10k-protocol-10k', 10000, 10000, 1), ('200k-protocol-200k', 200000, 200000, 20),
                                              ('200k-protocol-10k', 200000, 10000, None)):
            built = {}
            for case_name, (ms, counts, project_ms) in cases.items():
                value = ms if scale == 1 else (ms * scale if scale else project_ms)
                built[case_name] = {'status': 'passed', 'median_ms': value,
                                    'counts': {k: v * (scale or 1) if isinstance(v, int) and scale != 1 and k == 'sqlite.execute' else v
                                               for k, v in counts.items()}}
            profiles[name] = {'profile': {'epochs': epochs, 'protocol_epochs': protocol}, 'result': {'cases': built}}
        return {'config': cfg, 'profiles': profiles, 'source_start': {'commit': 'a' * 40, 'status': ''}}

    def test_flat_expectation_flags_linear_growth_and_project_dependence(self):
        receipt = self.receipt({'epoch.detail': (10.0, {}, 10.0), 'explore.page.eq': (10.0, {}, 10.0),
                                'overview': (10.0, {}, 150.0)})
        receipt['profiles']['200k-protocol-200k']['result']['cases']['epoch.detail']['median_ms'] = 10.5
        receipt['profiles']['200k-protocol-200k']['result']['cases']['overview']['median_ms'] = 11.0
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            path.write_text(json.dumps(receipt))
            result = routes.scaling(path, '10k-protocol-10k', '200k-protocol-200k', '200k-protocol-10k', Path(folder) / 'scaling.json')
            rows = {row['case']: row for row in result['rows']}
            self.assertEqual(rows['epoch.detail']['inferred'], 'flat')
            self.assertEqual(rows['explore.page.eq']['inferred'], 'linear')
            self.assertEqual(rows['explore.page.eq']['expected'], 'linear-allowed')
            self.assertEqual(result['flagged'], ['overview'])  # flat in size, but grows with the project
            self.assertIn('project-size dependent', rows['overview']['flags'][0])
            self.assertTrue((Path(folder) / 'scaling.md').read_text().startswith('# Route scaling'))

    def test_small_times_under_floor_are_flat(self):
        receipt = self.receipt({'tree.root': (0.5, {}, 0.5)})
        receipt['profiles']['200k-protocol-200k']['result']['cases']['tree.root']['median_ms'] = 4.0
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            path.write_text(json.dumps(receipt))
            result = routes.scaling(path, '10k-protocol-10k', '200k-protocol-200k', None, Path(folder) / 's.json')
            self.assertEqual(result['flagged'], [])


class StressLockTests(unittest.TestCase):
    def test_waits_reports_holder_times_out_and_records_itself(self):
        import fcntl
        import io
        with tempfile.TemporaryDirectory(prefix='route-lock-test-') as folder:
            path = Path(folder) / 'stress.lock'
            holder = path.open('a+')
            fcntl.flock(holder, fcntl.LOCK_EX)
            holder.write('pid=1 cmd=other benchmark\n'); holder.flush()
            waiter, log = path.open('a+'), io.StringIO()
            with self.assertRaisesRegex(TimeoutError, 'other benchmark'):
                routes.acquire_lock(waiter, 0.3, poll=0.05, report_every=0.1, out=log)
            self.assertIn('waiting for stress lock held by pid=1 cmd=other benchmark', log.getvalue())
            fcntl.flock(holder, fcntl.LOCK_UN); holder.close()
            routes.acquire_lock(waiter, 1, poll=0.05, out=log)
            self.assertIn(f'pid={__import__("os").getpid()}', path.read_text())
            waiter.close()


if __name__ == '__main__':
    unittest.main()
