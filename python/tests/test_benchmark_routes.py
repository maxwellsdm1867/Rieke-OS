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


if __name__ == '__main__':
    unittest.main()
