"""Fail-closed harness/report/gate regression coverage; no application service."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark', ROOT / 'tools/benchmark.py')
bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)


class BenchmarkTests(unittest.TestCase):
    def receipt(self):
        reg = bench.registry()
        source = {'tree':'b'*40, 'status_sha256':bench.sha(b''), 'commit':'a'*40, 'dirty':False, 'application_version':'0.1.6',
                  'schema_sources':{'schema':'b'*64}, 'schema_versions':{'schema':1}, 'database_compatibility':1, 'workspace_formats':[1]}
        return {'created_at':'2026-10-03T12:00:00+00:00', 'format':bench.FORMAT, 'schema_version':1, 'source_start':source,
                'source_end':copy.deepcopy(source), 'suite_version':reg['suite_version'],
                'suite':bench.suite_identity(), 'fixture':{'version':reg['fixture_version'], 'sha256':bench.sha((ROOT/'tools/metadata_qualification/native-truth.json').read_bytes())},
                'method':reg['method'], 'samples':reg['samples'], 'fixture_cleaned':True,
                'environment':{k:'fixture' for k in ['os','architecture','cpu','logical_cpus','memory_bytes','machine_id','python','sqlite','node','dependencies','python_packages','frontend_packages']},
                'cases':[dict(id=c['id'], status='passed', **({'metrics':{m:[1,2,3,4] for m in c['metrics']}} if c['kind']=='latency' else {'tests':2, 'skipped':0,'execution_ms':10})) for c in reg['cases']],
                'release_requirements':reg['release_requirements'], 'gaps':reg['gaps'], 'wall_seconds':1}

    def test_complete_core_does_not_claim_complete_release(self):
        receipt=self.receipt(); self.assertEqual(bench.validate(receipt), [])
        result=bench.gate(receipt, expected_commit='a'*40, expected_version='0.1.6')
        self.assertFalse(result['release_qualified'])
        with self.assertRaisesRegex(ValueError, 'ui.native.navigation'):
            bench.gate(receipt, expected_commit='a'*40, expected_version='0.1.6', release=True)
        self.assertIn('release qualification: INCOMPLETE', bench.report(receipt))

    def test_missing_duplicate_failed_nan_negative_short_and_skipped_fail(self):
        for change in [lambda r:r['cases'].pop(), lambda r:r['cases'].append(r['cases'][0]),
                       lambda r:r['cases'][0].update(status='failed'),
                       lambda r:r['cases'][0]['metrics'].update(cold_reader_ms=[float('nan')]*4),
                       lambda r:r['cases'][0]['metrics'].update(cold_reader_ms=[-1]*4),
                       lambda r:r['cases'][0]['metrics'].update(cold_reader_ms=[1]*3),
                       lambda r:r['cases'][-1].update(skipped=1),
                       lambda r:r['cases'][-1].update(tests=0),
                       lambda r:r.update(fixture_cleaned=False),
                       lambda r:r.update(release_requirements=[]),
                       lambda r:r['source_start'].pop('tree'),
                       lambda r:r.update(error='Worker failed'),
                       lambda r:r['cases'][0].update(metrics=[])]:
            receipt=self.receipt();change(receipt);receipt['status']='passed'
            with self.subTest(receipt=receipt['cases'][0]):self.assertTrue(bench.validate(receipt))

    def test_stale_dirty_changed_source_and_harness_rejected(self):
        for change in [lambda r:r['source_start'].update(commit='d'*40),
                       lambda r:r['source_start'].update(dirty=True),
                       lambda r:r['source_end'].update(dirty=True),
                       lambda r:r['suite'].update(sha256='d'*64),
                       lambda r:r['source_start'].update(application_version='0.1.7')]:
            receipt=self.receipt();change(receipt)
            with self.assertRaises(ValueError):bench.gate(receipt, expected_commit='a'*40, expected_version='0.1.6')

    def test_comparison_rejects_environment_schema_method_and_fixture_changes(self):
        for key in ['environment','fixture','suite','method']:
            left=self.receipt();right=copy.deepcopy(left);right[key]['changed']=True
            result=bench.compare(left,right)
            self.assertFalse(result['comparable']);self.assertEqual(result['changes'],[])
        left=self.receipt();right=copy.deepcopy(left)
        right['source_start']['schema_versions']['schema']=2
        right['source_end']=copy.deepcopy(right['source_start'])
        self.assertFalse(bench.compare(left,right)['comparable'])

    def test_comparable_versions_keep_raw_deltas_without_speed_claim(self):
        left=self.receipt();right=copy.deepcopy(left)
        right['source_start'].update(commit='e'*40,application_version='0.1.7')
        right['source_end']=copy.deepcopy(right['source_start'])
        right['cases'][0]['metrics']['cold_reader_ms']=[2,3,4,5]
        result=bench.compare(left,right);self.assertTrue(result['comparable'])
        self.assertEqual(result['changes'][0]['delta_ms'],1)
        self.assertIn('Observed differences only',bench.report(right,result))

    def test_worker_failure_writes_incomplete_receipt_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'
            with patch.object(bench,'execute',side_effect=RuntimeError('worker failed')):
                result=bench.run(out)
            self.assertTrue(result['validation_errors'])
            self.assertFalse(result['fixture_cleaned'])
            self.assertTrue((out/'benchmark.json').exists())
            self.assertIn('worker failed',json.loads((out/'benchmark.json').read_text())['error'])
            with self.assertRaises(FileExistsError):bench.run(out)

    def test_release_rejects_missing_receipt_before_remote_mutation(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        import desktop_release
        evidence={'source_commit':'a'*40}
        with tempfile.TemporaryDirectory() as tmp, patch.object(desktop_release,'artifact_inventory',return_value={}), patch.object(desktop_release,'verify_metadata'), patch.object(desktop_release,'validate_evidence',return_value=evidence), patch.object(desktop_release,'gh_json') as remote:
            path=Path(tmp);(path/'evidence.json').write_text('{}')
            with self.assertRaises(FileNotFoundError):desktop_release.promote(path,'v0.1.6',path/'evidence.json')
            remote.assert_not_called()


if __name__=='__main__':unittest.main()
