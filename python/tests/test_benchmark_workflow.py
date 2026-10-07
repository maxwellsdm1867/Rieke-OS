"""Independent workflow receipt checks. No server, browser or large fixture."""
import unittest
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools import benchmark_workflow as bench


class WorkflowContractTests(unittest.TestCase):
    def span(self, identifier, owner, start, end, parent=None, clock='browser'):
        row = dict(id=identifier, module=owner, name=identifier,
                   start_ms=start, end_ms=end, clock=clock)
        if parent is not None:
            row['parent_id'] = parent
        return row

    def action(self, trace=False):
        rows = []
        for index, phase in enumerate(('ordinary', 'ordinary', 'profile')):
            row = dict(action_id=f'inspect-{index}', phase=phase, total_ms=100.0,
                       correctness={'passed': True}, requests=[], frontend_spans=[])
            if trace:
                identity = dict(epoch_uuid='requested-epoch', stream_uuid='response',
                                units='pA', start=0, end=100)
                row['trace'] = dict(expected=identity, first=dict(identity), complete=dict(identity),
                                    first_visible_ms=60.0, complete_ms=100.0)
            rows.append(row)
        return dict(id='inspect', variant='cold', samples=rows)

    def test_nested_same_owner_uses_union_and_preserves_unattributed(self):
        result = bench.summarize_spans([
            self.span('outer', 'render', 10, 90),
            self.span('inner', 'render', 20, 50, 'outer'),
            self.span('leaf', 'decode', 30, 40, 'inner'),
        ], 100)
        self.assertEqual(result['covered_ms'], 80)
        self.assertEqual(result['unattributed_ms'], 20)
        self.assertEqual(result['modules']['render']['self_ms'], 70)
        self.assertEqual(result['modules']['decode']['self_ms'], 10)
        self.assertEqual(result['modules']['render']['calls'], 2)

    def test_disjoint_stages_preserve_gap(self):
        result = bench.summarize_spans([
            self.span('one', 'admission', 0, 20), self.span('two', 'render', 40, 70),
        ], 100)
        self.assertEqual(result['covered_ms'], 50)
        self.assertEqual(result['unattributed_ms'], 50)

    def test_crossing_different_owners_are_explicitly_nonadditive(self):
        result = bench.summarize_spans([
            self.span('one', 'network', 0, 60), self.span('two', 'render', 40, 90),
        ], 100)
        self.assertEqual(result['covered_ms'], 90)
        self.assertEqual(result['unattributed_ms'], 10)
        self.assertEqual(result['cross_owner_overlap_ms'], 20)
        self.assertFalse(result['additive'])

    def test_crossing_same_owner_is_unioned(self):
        result = bench.summarize_spans([
            self.span('one', 'network', 0, 60), self.span('two', 'network', 40, 90),
        ], 100)
        self.assertEqual(result['modules']['network']['self_ms'], 90)
        self.assertEqual(result['cross_owner_overlap_ms'], 0)
        self.assertTrue(result['additive'])

    def test_invalid_span_relationships_refused(self):
        cases = [
            [self.span('a', 'x', 0, 40), self.span('b', 'y', 30, 60, 'a')],
            [self.span('a', 'x', 0, 40, 'missing')],
            [self.span('a', 'x', 0, 40, 'b'), self.span('b', 'y', 0, 40, 'a')],
            [self.span('a', 'x', 0, 40), self.span('a', 'y', 50, 60)],
            [self.span('a', 'x', 0, 40, clock='server')],
            [self.span('a', 'x', -1, 40)], [self.span('a', 'x', 0, 101)],
            [self.span('a', 'x', 40, 20)],
        ]
        for spans in cases:
            with self.subTest(spans=spans), self.assertRaises(ValueError):
                bench.summarize_spans(spans, 100)

    def test_invalid_numeric_span_values_refused(self):
        for value in (True, float('nan'), float('inf'), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bench.summarize_spans([self.span('a', 'x', 0, value)], 100)

    def test_valid_action_keeps_profile_separate(self):
        action = self.action()
        action['samples'][-1]['total_ms'] = 1000
        result = bench.validate_action(action, {'id': 'inspect', 'trace': False}, 2)
        self.assertEqual(result['total_ms'], 100)

    def test_wrong_sample_counts_phases_and_correctness_refused(self):
        changes = [lambda a: a['samples'].pop(0),
                   lambda a: a['samples'][0].update(phase='unknown'),
                   lambda a: a['samples'][0]['correctness'].update(passed=False),
                   lambda a: a['samples'][0].update(action_id='inspect-1')]
        for change in changes:
            action = self.action()
            change(action)
            with self.subTest(change=change), self.assertRaises(ValueError):
                bench.validate_action(action, {'id': 'inspect', 'trace': False}, 2)

    def test_invalid_action_duration_refused(self):
        for value in (True, float('nan'), float('inf'), -1, 0):
            action = self.action()
            action['samples'][0]['total_ms'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                bench.validate_action(action, {'id': 'inspect', 'trace': False}, 2)

    def test_trace_requires_requested_identity_at_both_endpoints(self):
        bench.validate_action(self.action(True), {'id': 'inspect', 'trace': True}, 2)
        for endpoint in ('first', 'complete'):
            for field in ('epoch_uuid', 'stream_uuid', 'units', 'start', 'end'):
                action = self.action(True)
                action['samples'][0]['trace'][endpoint][field] = 'stale-or-wrong'
                with self.subTest(endpoint=endpoint, field=field), self.assertRaises(ValueError):
                    bench.validate_action(action, {'id': 'inspect', 'trace': True}, 2)

    def test_trace_missing_inverted_or_out_of_action_endpoints_refused(self):
        for change in (lambda t: t.pop('first'), lambda t: t.update(first_visible_ms=110),
                       lambda t: t.update(first_visible_ms=-1),
                       lambda t: t.update(complete_ms=50),
                       lambda t: t.update(complete_ms=101)):
            action = self.action(True)
            change(action['samples'][0]['trace'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                bench.validate_action(action, {'id': 'inspect', 'trace': True}, 2)

    def browser_result(self):
        return dict(format='disco-workflow-browser-v1', status='passed', epochs=1_000_000, profile=True, module_timing=False,
                    actions=[self.action()], failures=[], gaps=[],
                    cleanup={'browser_closed': True, 'vite_closed': True, 'server_closed': True})

    def test_browser_rejects_missing_actions_failed_oracles_wrong_scale_and_cleanup(self):
        cfg = {'cases': [{'id': 'inspect', 'trace': False}]}
        bench.validate_browser(self.browser_result(), cfg, 1_000_000, 2)
        changes = [lambda r: r.update(actions=[]), lambda r: r.update(epochs=999_999),
                   lambda r: r.update(status='running'), lambda r: r.update(gaps=['missing variant']), lambda r: r.update(failures=['bad result']),
                   lambda r: r['cleanup'].update(browser_closed=False),
                   lambda r: r['cleanup'].update(vite_closed=False),
                   lambda r: r['actions'][0]['samples'][0]['correctness'].update(passed=False)]
        for change in changes:
            result = self.browser_result()
            change(result)
            with self.subTest(change=change), self.assertRaises(ValueError):
                bench.validate_browser(result, cfg, 1_000_000, 2)

    def test_required_variant_cannot_be_silently_omitted(self):
        with self.assertRaises(ValueError):
            bench.validate_browser(self.browser_result(),
                                   {'cases': [{'id': 'inspect', 'variants': ['cold', 'warm']}]},
                                   1_000_000, 2)

    def test_unknown_variant_cannot_join_qualified_coverage(self):
        result = self.browser_result()
        extra = self.action()
        extra['variant'] = 'unregistered'
        for sample in extra['samples']:
            sample['action_id'] += '-extra'
        result['actions'].append(extra)
        with self.assertRaises(ValueError):
            bench.validate_browser(result, {'cases': [{'id': 'inspect', 'variants': ['cold']}]},
                                   1_000_000, 2)

    def test_requests_require_nonempty_unique_correlation_and_success(self):
        valid = {'action_id': 'inspect-0', 'request_id': 'request-1', 'status': 200}
        for requests in ([dict(valid, action_id='wrong')], [dict(valid, request_id='')],
                         [dict(valid), dict(valid)], [dict(valid, status=500)],
                         [dict(valid, status=True)]):
            action = self.action()
            action['samples'][0]['requests'] = requests
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                bench.validate_action(action, {'id': 'inspect'}, 2)

    def test_optional_module_regression_does_not_fail_ordinary_gate(self):
        baseline = {'inspect': {'total_ms': 100, 'modules': {'decode': 10}}}
        candidate = {'inspect': {'total_ms': 80, 'modules': {'decode': 30}}}
        result = bench.compare_metrics(baseline, candidate, {'relative': 0.25, 'absolute_ms': 5})
        self.assertEqual(result['review_required'], [])
        self.assertEqual(result['status'], 'passed')

    def test_trace_endpoint_regression_visible_when_total_improves(self):
        baseline = {'trace': {'total_ms': 100, 'modules': {},
                              'endpoints': {'first_visible_ms': 10, 'complete_ms': 100}}}
        candidate = {'trace': {'total_ms': 80, 'modules': {},
                               'endpoints': {'first_visible_ms': 30, 'complete_ms': 80}}}
        result = bench.compare_metrics(baseline, candidate, {'relative': .25, 'absolute_ms': 5})
        self.assertEqual(result['review_required'], ['trace/endpoint:first_visible_ms'])
        self.assertEqual(result['status'], 'review_required')

    def test_trace_endpoint_coverage_mismatch_refused(self):
        baseline = {'trace': {'total_ms': 100, 'modules': {},
                              'endpoints': {'first_visible_ms': 10, 'complete_ms': 100}}}
        for endpoints in ({}, {'complete_ms': 100}):
            candidate = {'trace': {'total_ms': 100, 'modules': {}, 'endpoints': endpoints}}
            with self.subTest(endpoints=endpoints), self.assertRaisesRegex(ValueError, 'endpoint coverage'):
                bench.compare_metrics(baseline, candidate, {'relative': .25, 'absolute_ms': 5})

    def test_trace_endpoint_medians_exclude_profile_and_appear_in_both_reports(self):
        action = self.action(True)
        action['samples'][0]['trace']['first_visible_ms'] = 20
        action['samples'][1]['trace']['first_visible_ms'] = 40
        action['samples'][-1]['total_ms'] = 1000
        action['samples'][-1]['trace'].update(first_visible_ms=500, complete_ms=1000)
        result = bench.metrics({'actions': [action]}, {},
                               {'cases': [{'id': 'inspect', 'trace': True}], 'samples': 2})
        self.assertEqual(result['inspect/cold']['endpoints'],
                         {'first_visible_ms': 30, 'complete_ms': 100})
        with tempfile.TemporaryDirectory(prefix='workflow-report-test-') as directory:
            output = Path(directory)
            bench.report({'status': 'test-fixture', 'metrics': result}, output)
            for name in ('workflow.md', 'workflow.html'):
                text = (output/name).read_text()
                self.assertIn('First correct trace', text)
                self.assertIn('Complete trace window', text)
                self.assertIn('30.00', text)

    def test_missing_action_refused_but_module_coverage_optional(self):
        baseline = {'inspect': {'total_ms': 100, 'modules': {'decode': 10}}}
        with self.assertRaises(ValueError):
            bench.compare_metrics(baseline, {}, {'relative': .25, 'absolute_ms': 5})
        candidate = {'inspect': {'total_ms': 100, 'modules': {}}}
        self.assertEqual(bench.compare_metrics(baseline, candidate,
                         {'relative': .25, 'absolute_ms': 5})['status'], 'passed')
        candidate['inspect']['total_ms'] = 150
        self.assertEqual(bench.compare_metrics(baseline, candidate,
                         {'relative': .25, 'absolute_ms': 5})['review_required'], ['inspect/total_ms'])

    def test_profile_is_optional_but_explicit_mode_is_enforced(self):
        ordinary = self.action()
        ordinary['samples'].pop()
        bench.validate_action(ordinary, {'id': 'inspect'}, 2)
        bench.validate_action(ordinary, {'id': 'inspect'}, 2, profile=False)
        with self.assertRaises(ValueError):
            bench.validate_action(ordinary, {'id': 'inspect'}, 2, profile=True)
        with self.assertRaises(ValueError):
            bench.validate_action(self.action(), {'id': 'inspect'}, 2, profile=False)
        duplicate = self.action()
        extra = copy.deepcopy(duplicate['samples'][-1]); extra['action_id'] += '-extra'
        duplicate['samples'].append(extra)
        with self.assertRaises(ValueError):
            bench.validate_action(duplicate, {'id': 'inspect'}, 2)

    def test_no_profile_browser_metrics_and_reports(self):
        raw = self.browser_result()
        raw['profile'] = False
        raw['actions'][0]['samples'].pop()
        cfg = {'cases': [{'id': 'inspect'}], 'samples': 2}
        bench.validate_browser(raw, cfg, 1_000_000, 2)
        result = bench.metrics(raw, {}, cfg)
        self.assertEqual(result['inspect/cold']['total_ms'], 100)
        self.assertIsNone(result['inspect/cold']['profile_total_ms'])
        self.assertEqual(result['inspect/cold']['modules'], {})
        with tempfile.TemporaryDirectory(prefix='workflow-no-profile-test-') as directory:
            output = Path(directory)
            bench.report({'status': 'test-fixture', 'profile': False, 'metrics': result}, output)
            self.assertIn('100.00', (output/'workflow.md').read_text())
            self.assertIn('100.00', (output/'workflow.html').read_text())
        raw['profile'] = True
        with self.assertRaises(ValueError):
            bench.validate_browser(raw, cfg, 1_000_000, 2)
        del raw['profile']
        with self.assertRaises(ValueError):
            bench.validate_browser(raw, cfg, 1_000_000, 2)


class WorkflowReceiptTests(unittest.TestCase):
    """Small synthetic evidence validates refusal, never claims a run occurred."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='workflow-receipt-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cfg = {'samples': 2, 'cases': [{'id': 'inspect', 'variants': ['cold']}],
                    'comparison': {'relative': .25, 'absolute_ms': 5}}
        self.manifest = {'runner': 'a' * 64}
        for name, value in [('config', self.cfg), ('harness', self.manifest)]:
            mock = patch.object(bench, name, return_value=value)
            mock.start(); self.addCleanup(mock.stop)
        files = {'python/owned.py': 'a' * 64}
        self.source = {'commit': 'a' * 40, 'tree': 'b' * 40, 'status': '', 'files': files,
                       'sha256': bench.query_bench.sha(bench.query_bench.canonical(files))}
        self.env = dict(python='fixture', sqlite='fixture', os='fixture', machine='fixture',
                        host='fixture', cpu_model='fixture', cpu_count=1, physical_memory=1024,
                        packages=['fixture'])

    def save(self, path, value):
        path.write_text(json.dumps(value))

    def receipt(self, name='receipt'):
        directory = self.root / name
        (directory / 'browser').mkdir(parents=True)
        (directory / 'server').mkdir()
        action = WorkflowContractTests().action()
        backend = []
        for index, sample in enumerate(action['samples']):
            request = dict(action_id=sample['action_id'], request_id=f'request-{index}', status=200)
            sample['requests'] = [request]
            if sample['phase'] == 'profile':
                sample['total_ms'] = 1000
            backend.append({**request, 'total_ms': 20, 'clock': 'server', 'phase': sample['phase'],
                            'path': '/api/epochs', 'h5_accesses': [], 'h5_access_count': 0,
                            'module_timing': False, 'module_timings': [],
                            'spans': ([dict(module='disco.metadata.reader', inclusive_ms=10,
                                           self_ms=5, calls=1)] if sample['phase'] == 'profile' else [])})
        browser_env = {'browser': 'fixture', 'node': 'fixture', 'viewport': {'width': 1, 'height': 1}}
        raw = dict(format=bench.BROWSER_FORMAT, status='passed', epochs=1_000_000, profile=True, module_timing=False,
                   actions=[action], gaps=[], failures=[],
                   cleanup={'browser_closed': True, 'vite_closed': True}, environment=browser_env)
        self.save(directory / 'browser/browser.json', raw)
        (directory / 'server/requests.jsonl').write_text('\n'.join(json.dumps(row) for row in backend)+'\n')
        self.save(directory / 'server/server.json', {'epochs': 1_000_000, 'protocol_epochs': 1_000_000})
        cleanup = dict(server_closed=True, fixture_closed=True, instrumentation_restored=True)
        self.save(directory / 'server/cleanup.json', cleanup)
        value = dict(format=bench.FORMAT, status='passed', smoke=False, profile=True, module_timing=False, config=self.cfg,
                     epochs=1_000_000, protocol_epochs=1_000_000, samples=2, fixture={'epochs': 1_000_000, 'protocol_epochs': 1_000_000}, harness_start=self.manifest, harness_end=self.manifest,
                     source_start=copy.deepcopy(self.source), source_end=copy.deepcopy(self.source),
                     environment=copy.deepcopy(self.env), browser_environment=browser_env,
                     cleanup={'browser_processes_closed': True, 'server_processes_closed': True,
                              'backend': cleanup},
                     metrics=bench.metrics(raw, {r['request_id']: r for r in backend}, self.cfg))
        path = directory / 'receipt.json'
        self.seal(path, value)
        return path, value

    def seal(self, path, value):
        value['evidence_sha256'] = {str(p.relative_to(path.parent)): bench.query_bench.sha(p.read_bytes())
                                    for folder in ('browser', 'server')
                                    for p in (path.parent / folder).iterdir() if p.is_file()}
        keys = ('source_start','source_end','harness_start','harness_end','environment','browser_environment','config','epochs','samples','protocol_epochs','profile','module_timing','fixture')
        provenance = path.parent/'provenance.json'
        self.save(provenance, {key: value[key] for key in keys})
        value['provenance_sha256'] = bench.query_bench.sha(provenance.read_bytes())
        self.save(path, value)

    def test_valid_receipt_recomputes_headline_without_profile_total(self):
        path, _ = self.receipt()
        value = bench.load_receipt(path)
        metric = value['metrics']['inspect/cold']
        self.assertEqual(metric['total_ms'], 100)
        self.assertEqual(metric['profile_total_ms'], 1000)
        self.assertEqual(metric['modules']['server:disco.metadata'], 5)
        self.assertEqual(metric['modules']['server:unattributed'], 15)

    def test_raw_profile_mode_must_match_receipt(self):
        path, value = self.receipt()
        value['profile'] = False
        self.seal(path, value)
        with self.assertRaises(ValueError):
            bench.load_receipt(path)

    def test_raw_tampering_without_resealing_refused(self):
        path, _ = self.receipt()
        (path.parent / 'server/requests.jsonl').write_text('{}\n')
        with self.assertRaises(ValueError):
            bench.load_receipt(path)

    def test_missing_backend_correlation_refused_even_when_hash_matches(self):
        path, value = self.receipt()
        (path.parent / 'server/requests.jsonl').write_text('')
        self.seal(path, value)
        with self.assertRaises(ValueError):
            bench.load_receipt(path)

    def test_profile_total_cannot_replace_ordinary_headline(self):
        path, value = self.receipt()
        value['metrics']['inspect/cold']['total_ms'] = 1000
        self.save(path, value)
        with self.assertRaises(ValueError):
            bench.load_receipt(path)

    def test_source_harness_hardware_and_cleanup_faults_refused(self):
        changes = [lambda v: v['source_end'].update(commit='c'*40),
                   lambda v: v.update(harness_end={}),
                   lambda v: v['environment'].update(cpu_count=0),
                   lambda v: v['environment'].update(physical_memory=True),
                   lambda v: v['cleanup'].update(server_processes_closed=False),
                   lambda v: v['cleanup']['backend'].update(fixture_closed=False)]
        for index, change in enumerate(changes):
            path, value = self.receipt(str(index)); change(value); self.save(path, value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                bench.load_receipt(path)

    def test_raw_cleanup_must_agree_with_summary(self):
        path, value = self.receipt()
        self.save(path.parent/'server/cleanup.json', {'server_closed': False})
        self.seal(path, value)
        with self.assertRaises(ValueError):
            bench.load_receipt(path)

    def test_raw_fixture_scale_must_agree_with_browser_and_summary(self):
        path, value = self.receipt()
        self.save(path.parent/'server/server.json', {'epochs': 1000})
        self.seal(path, value)
        with self.assertRaises(ValueError):
            bench.load_receipt(path)

    def test_compare_refuses_different_protocol_scope_with_same_project_scale(self):
        baseline, _ = self.receipt('baseline')
        candidate, value = self.receipt('candidate')
        value['protocol_epochs'] = 20_000
        value['fixture']['protocol_epochs'] = 20_000
        self.save(candidate.parent/'server/server.json', value['fixture'])
        self.seal(candidate, value)
        bench.load_receipt(candidate)
        with self.assertRaisesRegex(ValueError, 'protocol_epochs'):
            bench.compare(baseline, candidate, self.root/'comparison.json')

    def module_fixture(self, name='modules'):
        path, value = self.receipt(name)
        rawpath = path.parent/'browser/browser.json'
        raw = json.loads(rawpath.read_text()); raw['module_timing'] = True
        requestpath = path.parent/'server/requests.jsonl'
        rows = [json.loads(line) for line in requestpath.read_text().splitlines()]
        for row, elapsed in zip(rows, (2, 6, 999)):
            row['module_timing'] = True
            row['module_timings'] = [{'module': 'metadata', 'operation': 'page',
                                      'elapsed_ms': elapsed, 'outcome': 'ok'}]
        self.save(rawpath, raw)
        requestpath.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
        value['module_timing'] = True
        value['metrics'] = bench.metrics(raw, bench.load_requests(requestpath), self.cfg)
        self.seal(path, value)
        return path, value

    def test_builtin_module_calls_exclude_profile_and_do_not_change_gate(self):
        path, value = self.module_fixture()
        measured = bench.load_receipt(path)['metrics']['inspect/cold']
        self.assertEqual(measured['module_timings'], {'metadata.page': {'median_call_ms': 4, 'calls': 2}})
        baseline = {'inspect': measured}
        candidate = copy.deepcopy(baseline)
        candidate['inspect']['module_timings']['metadata.page']['median_call_ms'] = 999
        self.assertEqual(bench.compare_metrics(baseline, candidate, self.cfg['comparison'])['status'], 'passed')
        bench.report(value, path.parent)
        for name in ('workflow.md', 'workflow.html'):
            self.assertIn('metadata.page', (path.parent/name).read_text())
            self.assertIn('4.000', (path.parent/name).read_text())

    def test_builtin_module_mode_mismatch_refused(self):
        path, value = self.module_fixture()
        rawpath = path.parent/'browser/browser.json'
        raw = json.loads(rawpath.read_text()); raw['module_timing'] = False
        self.save(rawpath, raw); self.seal(path, value)
        with self.assertRaises(ValueError):
            bench.load_receipt(path)
        with self.assertRaises(ValueError):
            bench.metrics(raw, bench.load_requests(path.parent/'server/requests.jsonl'), self.cfg)

    def test_builtin_module_invalid_elapsed_or_outcome_refused(self):
        for index, change in enumerate(({'elapsed_ms': True}, {'elapsed_ms': -1},
                                        {'elapsed_ms': float('nan')}, {'elapsed_ms': float('inf')},
                                        {'outcome': 'unknown'})):
            path, _ = self.module_fixture(str(index))
            requestpath = path.parent/'server/requests.jsonl'
            rows = [json.loads(line) for line in requestpath.read_text().splitlines()]
            rows[0]['module_timings'][0].update(change)
            requestpath.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
            with self.subTest(change=change), self.assertRaises(ValueError):
                bench.load_requests(requestpath)

    def test_backend_phase_and_h5_tripwire_refused(self):
        for index, changes in enumerate(({'phase': 'other'}, {'clock': 'browser'},
                                        {'h5_access_count': 1, 'h5_accesses': [{'allowed': True}]},
                                        {'phase': 'ordinary', 'spans': [{'module': 'x', 'inclusive_ms': 10, 'self_ms': 3}]})):
            path, value = self.receipt(str(index))
            raw = path.parent/'server/requests.jsonl'
            rows = [json.loads(line) for line in raw.read_text().splitlines()]
            rows[0].update(changes)
            raw.write_text('\n'.join(json.dumps(row) for row in rows)+'\n'); self.seal(path, value)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bench.load_receipt(path)


if __name__ == '__main__':
    unittest.main()
