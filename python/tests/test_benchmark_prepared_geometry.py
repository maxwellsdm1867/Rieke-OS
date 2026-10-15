"""Receipt refusal and relative timing policy for the canonical geometry lane."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import benchmark_prepared_geometry as runner


def receipt():
    return {'status': 'passed', 'source_start': {'commit': 'a' * 40, 'tree': 'b' * 40, 'dirty': '', 'files': {'app.py': 'd' * 64}},
        'source_end': {'commit': 'a' * 40, 'tree': 'b' * 40, 'dirty': '', 'files': {'app.py': 'd' * 64}},
        'harness': {'test': 'fixture'}, 'environment': {'browser': 'fixed'}, 'fixture': 'fixed', 'payload_sha256': 'fixed', 'dependencies': {'lock': 'fixed'},
        'cleanup': {'server_closed': True, 'fixture_closed': True},
        'samples': [{'exact': {key: True for key in ('all_emitted_point_bytes_match', 'all_source_indices_match', 'whole_statistics_exact', 'all_canvas_coordinates_exact', 'prepared_display_context_exact')}, 'cursor': {'all_tile_bytes_exact': True},
                     'trace': {'first_visible_ms': 20, 'first_raf_ms': 25, 'complete_ms': 30}} for _ in range(3)]}


class PreparedGeometryTests(unittest.TestCase):
    def test_missing_failed_dirty_changed_or_unclean_evidence_is_not_comparable(self):
        for mutate in [lambda r: r.update(status='failed'), lambda r: r['samples'].pop(),
                       lambda r: r['samples'][0]['cursor'].clear(), lambda r: r['samples'][0]['exact'].clear(),
                       lambda r: r['source_end'].update(tree='c' * 40), lambda r: r.update(cleanup=None),
                       lambda r: (r['source_start'].update(dirty='M file'), r['source_end'].update(dirty='M file'))]:
            value = receipt(); mutate(value)
            with self.assertRaises(ValueError): runner.compare(receipt(), value)

    def test_mismatched_environment_harness_fixture_and_dependencies_refuse(self):
        for key in ('environment', 'harness', 'fixture', 'dependencies', 'payload_sha256'):
            value = receipt(); value[key] = 'different'
            with self.assertRaises(ValueError): runner.compare(receipt(), value)

    def test_large_regression_fails_existing_relative_policy(self):
        value = receipt()
        for row in value['samples']: row['trace'] = {'first_visible_ms': 40, 'first_raf_ms': 45, 'complete_ms': 60}
        result = runner.compare(receipt(), value)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['policy'], {'relative': .25, 'absolute_ms': 5.})
        self.assertEqual(runner.compare(receipt(), receipt())['status'], 'passed')

    def test_incomplete_or_malformed_source_identity_refuses(self):
        for field in ('commit', 'tree', 'dirty', 'files'):
            changed = receipt()
            for key in ('source_start', 'source_end'): del changed[key][field]
            with self.subTest(missing=field), self.assertRaises(ValueError): runner.validate(changed)
        for field, value in [('commit', None), ('commit', 'abc'), ('tree', 123), ('dirty', False),
                             ('files', {}), ('files', {'app.py': None}), ('files', {'../app.py': 'd' * 64}),
                             ('files', {'/app.py': 'd' * 64}), ('files', {'app.py': 'short'})]:
            changed = receipt()
            for key in ('source_start', 'source_end'): changed[key][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): runner.validate(changed)

    def test_nonfinite_and_invalid_observation_order_refuse(self):
        for value in (True, False, float('nan'), float('inf'), -1, 40):
            changed = receipt(); changed['samples'][0]['trace']['first_visible_ms'] = value
            with self.assertRaises(ValueError): runner.validate(changed)

if __name__ == '__main__': unittest.main()
