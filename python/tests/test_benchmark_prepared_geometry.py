"""Receipt refusal and relative timing policy for the canonical geometry lane."""
import copy
import importlib.util
import json
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
import subprocess
import signal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import benchmark_prepared_geometry as runner


def receipt(role='candidate'):
    from benchmark_workflow import DEPENDENCY_POLICY
    result = {'status': 'passed', 'dependency_policy': DEPENDENCY_POLICY, 'source_start': {'commit': 'a' * 40, 'tree': 'b' * 40, 'dirty': '', 'files': {'app.py': 'd' * 64}},
        'source_end': {'commit': 'a' * 40, 'tree': 'b' * 40, 'dirty': '', 'files': {'app.py': 'd' * 64}},
        'harness': {'test': 'fixture'}, 'environment': {'browser': {'click_dispatch_protocol': 'raf-aligned-click-v1', 'browser': 'pinned', 'sampling_protocol': runner.PAIRED_PROTOCOL, 'timing_mode': 'ordinary', 'browser_launch': {'distribution': 'playwright-chromium-headless-shell', 'playwright_version': '1.61.1', 'executable_override': False}}}, 'fixture': 'fixed', 'payload_sha256': 'fixed', 'dependencies': {'lock': 'fixed'},
        'cleanup': {'server_closed': True, 'fixture_closed': True},
        'samples': [{'observer': {'dispatch_protocol': 'raf-aligned-click-v1', 'dispatch_requested_at': 0, 'dispatch_frame_timestamp': 16, 'dispatch_wait_ms': 16, 'armed_at': 16, 'intent_at': 16, 'first_raf_at': 32, 'ready_at': 46, 'required_correct_raf_callbacks': 2, 'raf_callbacks': 2}, 'exact': {key: True for key in ('all_emitted_point_bytes_match', 'all_source_indices_match', 'whole_statistics_exact', 'all_canvas_coordinates_exact', 'prepared_display_context_exact')}, 'cursor': {'all_tile_bytes_exact': True},
                     'authority': {'foreground_extraction': {'requested': index + 1, 'entry_calls': index + 1, 'default_entry_calls': 0}},
                     'total_ms': 30, 'trace': {'first_visible_ms': 20, 'first_raf_ms': 25, 'complete_ms': 30}} for index in range(3)]}
    result['pair'] = {'id': '1' * 32, 'protocol': runner.PAIRED_PROTOCOL,
                      'sources': {role: runner.source_binding(result['source_start']) for role in ('baseline', 'candidate')},
                      'order': runner.PAIRED_ORDER, 'browser_version': 'pinned', 'browser_instances': {'baseline': 100, 'candidate': 101},
                      'completed': [dict(item, execution_index=i) for i, item in enumerate(runner.PAIRED_ORDER)]}
    return role_receipt(result, role)


def role_receipt(result, role):
    result['pair_role'] = role
    for index, row in enumerate(result['samples']):
        row.update(pair_id=result['pair']['id'], protocol=runner.PAIRED_PROTOCOL, source_role=role,
                   sample_index=index, browser_instance=result['pair']['browser_instances'][role], execution_index=runner.PAIRED_ORDER.index({'role': role, 'sample': index}),
                   sample_class='first_trace_after_setup_warm_OS' if index == 0 else 'subsequent_trace_fresh_renderer_warm_OS')
    return result



class PreparedGeometryTests(unittest.TestCase):
    def test_release_version_only_changes_preserve_locked_dependency_comparability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for package in ('workspace-app', 'desktop'):
                (root / package).mkdir()
                (root / package / 'package-lock.json').write_text(json.dumps({
                    'version': '0.1.14', 'lockfileVersion': 3,
                    'packages': {'': {'version': '0.1.14', 'devDependencies': {'playwright': '1.2.3'}},
                                 'node_modules/playwright': {'version': '1.2.3', 'resolved': 'https://example/playwright', 'integrity': 'sha512-original'}}}))
            (root / 'benchmarks').mkdir()
            (root / 'benchmarks/requirements-py311.txt').write_text('numpy==2.2.6\n')
            before = runner.dependency_fingerprints(root)
            for package in ('workspace-app', 'desktop'):
                path = root / package / 'package-lock.json'
                lock = json.loads(path.read_text())
                lock['version'] = lock['packages']['']['version'] = '0.1.15'
                path.write_text(json.dumps(lock))
            self.assertEqual(before, runner.dependency_fingerprints(root))
            lock['packages']['node_modules/playwright']['version'] = '1.2.4'
            path.write_text(json.dumps(lock))
            self.assertNotEqual(before, runner.dependency_fingerprints(root))
            (root / 'benchmarks/requirements-py311.txt').write_text('numpy==2.3.0\n')
            self.assertNotEqual(before['benchmarks/requirements-py311.txt'],
                                runner.dependency_fingerprints(root)['benchmarks/requirements-py311.txt'])

    def test_missing_failed_dirty_changed_or_unclean_evidence_is_not_comparable(self):
        for mutate in [lambda r: r.pop('dependency_policy'), lambda r: r.update(dependency_policy='legacy'), lambda r: r.update(status='failed'), lambda r: r['samples'].pop(),
                       lambda r: r['samples'][0]['cursor'].clear(), lambda r: r['samples'][0]['exact'].clear(),
                       lambda r: r['source_end'].update(tree='c' * 40), lambda r: r.update(cleanup=None),
                       lambda r: (r['source_start'].update(dirty='M file'), r['source_end'].update(dirty='M file'))]:
            value = receipt(); mutate(value)
            with self.assertRaises(ValueError): runner.compare(receipt('baseline'), value)

    def test_mismatched_environment_harness_fixture_and_dependencies_refuse(self):
        for key in ('environment', 'harness', 'fixture', 'dependencies', 'payload_sha256'):
            value = receipt(); value[key] = 'different'
            with self.assertRaises(ValueError): runner.compare(receipt('baseline'), value)

    def test_large_regression_fails_existing_relative_policy(self):
        value = receipt()
        for row in value['samples']:
            row['trace'] = {'first_visible_ms': 40, 'first_raf_ms': 45, 'complete_ms': 60}
            row['total_ms'] = 60
            row['observer']['ready_at'] = 76
        result = runner.compare(receipt('baseline'), value)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['policy'], {'relative': .25, 'absolute_ms': 5.})
        self.assertEqual(runner.compare(receipt('baseline'), receipt())['status'], 'passed')

    def test_ordinary_and_diagnostic_modes_cannot_be_compared(self):
        ordinary, diagnostic = receipt('baseline'), receipt()
        ordinary['environment']['browser']['timing_mode'] = 'ordinary'
        diagnostic['environment']['browser']['timing_mode'] = 'diagnostic'
        with self.assertRaisesRegex(ValueError, 'Incomparable geometry environment'):
            runner.compare(ordinary, diagnostic)

    def test_single_slow_sample_cannot_hide_behind_unchanged_medians(self):
        changed = receipt()
        changed['samples'][2]['total_ms'] = 130
        changed['samples'][2]['observer']['ready_at'] = 146
        changed['samples'][2]['trace'] = {'first_visible_ms': 120, 'first_raf_ms': 125, 'complete_ms': 130}
        self.assertEqual(runner.compare(receipt('baseline'), changed)['status'], 'review_required')

    def test_first_frame_regression_is_gated_even_when_other_endpoints_match(self):
        baseline = receipt('baseline')
        for row in baseline['samples']:
            row['trace']['complete_ms'] = row['total_ms'] = 100
            row['observer']['ready_at'] = 116
        changed = role_receipt(copy.deepcopy(baseline), 'candidate')
        changed['samples'][1]['trace']['first_raf_ms'] = 60
        self.assertEqual(runner.compare(baseline, changed)['status'], 'review_required')

    def test_missing_or_fallback_foreground_evidence_fails(self):
        for evidence in (None, {}, {'requested': 1, 'entry_calls': 0, 'default_entry_calls': 1}):
            changed = receipt(); changed['samples'][0]['authority']['foreground_extraction'] = evidence
            with self.assertRaisesRegex(ValueError, 'foreground extraction'):
                runner.compare(receipt('baseline'), changed)

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

class PairedSamplingTests(unittest.TestCase):
    def test_missing_mixed_reordered_or_forged_pair_refuses(self):
        mutations = [
            lambda r: r.pop('pair'), lambda r: r.update(pair_role='baseline'),
            lambda r: r['pair'].update(id='2' * 32),
            lambda r: r['pair'].update(protocol='other'),
            lambda r: r['pair']['completed'].pop(),
            lambda r: r['pair'].update(order=list(reversed(r['pair']['order']))),
            lambda r: r['pair']['sources']['candidate'].update(commit='c' * 40),
            lambda r: r['pair'].update(browser_version='other'),
            lambda r: r['pair']['browser_instances'].update(candidate=100),
            lambda r: r['samples'][0].update(browser_instance=100),
            lambda r: r['samples'][1].update(sample_index=0),
            lambda r: r['samples'][1].update(sample_index=True),
            lambda r: r['samples'][1].update(execution_index=1),
            lambda r: r['samples'][1].update(source_role='baseline'),
            lambda r: r['samples'][1].update(pair_id='2' * 32),
            lambda r: r['samples'][1].update(protocol='serial'),
            lambda r: r['samples'][0].update(sample_class='warmup_omitted'),
        ]
        for mutate in mutations:
            candidate = receipt(); mutate(candidate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                runner.compare(receipt('baseline'), candidate)

    def test_both_forged_pair_receipts_cannot_hide_reordered_or_wrong_source_samples(self):
        for defect in ('order', 'binding', 'browser', 'sample'):
            before, after = receipt('baseline'), receipt()
            if defect == 'order':
                before['pair']['completed'][0]['sample'] = 2
            if defect == 'binding':
                before['pair']['sources']['candidate']['files_sha256'] = 'f' * 64
            if defect == 'browser':
                before['pair']['browser_version'] = 'different-browser'
            after['pair'] = copy.deepcopy(before['pair'])
            if defect == 'sample': after['samples'][2] = copy.deepcopy(after['samples'][1])
            with self.subTest(defect=defect), self.assertRaises(ValueError): runner.compare(before, after)

    def test_missing_cancelled_or_timed_out_browser_children_fail_and_terminate_owned_group(self):
        for failure in (InterruptedError('cancelled'), subprocess.TimeoutExpired(['node'], 1),
                        subprocess.CalledProcessError(9, ['node'])):
            child = Mock(pid=12345)
            if isinstance(failure, subprocess.CalledProcessError): child.wait.side_effect = [9, 9, 9]
            else: child.wait.side_effect = [failure, 0, 0]
            with patch.object(runner.subprocess, 'Popen', return_value=child) as start, \
                    patch.object(runner.psutil, 'Process', side_effect=runner.psutil.NoSuchProcess(12345)), \
                    patch.object(runner.os, 'killpg', side_effect=[None, ProcessLookupError(), ProcessLookupError()]) as kill:
                with self.subTest(failure=failure), self.assertRaises(type(failure)):
                    runner.run_browser(['node', 'owned'], None, timeout=1)
                self.assertTrue(start.call_args.kwargs['start_new_session'])
                self.assertEqual(kill.call_args_list[0].args, (12345, signal.SIGTERM))

    def test_matching_external_browser_override_cannot_qualify(self):
        before, after = receipt('baseline'), receipt()
        for value in (before, after): value['environment']['browser']['browser_launch']['executable_override'] = True
        with self.assertRaisesRegex(ValueError, 'pinned Playwright browser'):
            runner.compare(before, after)

    def test_matching_diagnostic_receipts_still_cannot_qualify(self):
        before, after = receipt('baseline'), receipt()
        for value in (before, after): value['environment']['browser']['timing_mode'] = 'diagnostic'
        with self.assertRaisesRegex(ValueError, 'Diagnostic geometry timing'):
            runner.compare(before, after)

    def test_malformed_process_identity_still_closes_known_owned_group(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / 'browser-process.json'; identity.write_text('{partial')
            node = Mock(pid=12345); node.wait.return_value = 0
            with patch.object(runner.psutil, 'Process', side_effect=runner.psutil.NoSuchProcess(12345)), \
                    patch.object(runner.os, 'killpg', side_effect=[None, ProcessLookupError(), ProcessLookupError()]) as kill:
                with self.assertRaisesRegex(RuntimeError, 'identity could not be verified'):
                    runner.terminate_browser_groups(node, identity)
                self.assertEqual(kill.call_args_list[0].args, (12345, signal.SIGTERM))

    def test_detached_browser_surviving_node_exit_is_forcibly_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / 'browser-process.json'
            identity.write_text(json.dumps(dict(pid=23456, args=['owned-browser', '--owned-profile=unique'])))
            node = Mock(pid=12345); node.wait.return_value = 0
            browser = Mock(); browser.cmdline.return_value = ['owned-browser', '--owned-profile=unique']
            def lookup(pid):
                if pid == 12345: raise runner.psutil.NoSuchProcess(pid)
                return browser
            probes = {12345: 0, 23456: 0}; signals = []
            def kill(group, signum):
                if signum: signals.append((group, signum)); return
                probes[group] += 1
                if group == 12345 or probes[group] > 1: raise ProcessLookupError()
            with patch.object(runner.psutil, 'Process', side_effect=lookup), \
                    patch.object(runner.os, 'getpgid', return_value=23456), \
                    patch.object(runner.os, 'killpg', side_effect=kill):
                runner.terminate_browser_groups(node, identity)
            self.assertIn((23456, signal.SIGTERM), signals)
            self.assertIn((23456, signal.SIGKILL), signals)
            self.assertNotIn((12345, signal.SIGKILL), signals)

    def test_second_source_startup_failure_finalizes_both_and_never_runs_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); states = {}
            def new(source, output):
                output.mkdir(); state = dict(source=source, output=output, receipt=receipt(), server=None)
                states[source.name] = state; return state
            with patch.object(runner, 'new_source', side_effect=new), \
                    patch.object(runner, 'start_source', side_effect=[None, RuntimeError('server unavailable')]), \
                    patch.object(runner, 'finish_source', side_effect=lambda state, error: dict(status='failed')) as finish, \
                    patch.object(runner, 'run_browser') as browser:
                result = runner.run_pair(Path('baseline'), Path('candidate'), root / 'pair')
                self.assertEqual(result['status'], 'failed'); self.assertEqual(finish.call_count, 2)
                self.assertIn('server unavailable', result['error']); browser.assert_not_called()

if __name__ == '__main__': unittest.main()
