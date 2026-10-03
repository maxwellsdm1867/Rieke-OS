"""Fail-closed harness/report/gate regression coverage; no application service."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark', ROOT / 'tools/benchmark.py')
bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='benchmark-provenance-test-')
        cls.repo = Path(cls.temp.name)
        paths = set(bench.suite_identity()['files']) | {'rieke-release.json'}
        paths |= {'python/' + name for name in ('workspace_disk_index.py', 'workspace_typed_index.py', 'workspace_sqlite.py')}
        for name in paths:
            target = cls.repo / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        def git(*args): return bench.git(*args, root=cls.repo)
        git('init', '-q'); git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Benchmark fixture')
        cls.commit = git('rev-parse', 'HEAD')
        release = json.loads((cls.repo/'rieke-release.json').read_text()); release['version'] = '0.1.7'
        (cls.repo/'rieke-release.json').write_text(json.dumps(release))
        git('add', '.');git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Next fixture version')
        cls.next_commit = git('rev-parse', 'HEAD')

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def receipt(self):
        reg = bench.registry()
        source = bench.committed_source(self.commit, root=self.repo)
        return {'created_at':'2026-10-03T12:00:00+00:00', 'format':bench.FORMAT, 'schema_version':1, 'source_start':source,
                'source_end':copy.deepcopy(source), 'suite_version':reg['suite_version'],
                'suite':bench.suite_identity(), 'fixture':{'version':reg['fixture_version'], 'sha256':bench.sha((ROOT/'tools/metadata_qualification/native-truth.json').read_bytes())},
                'method':reg['method'], 'samples':reg['samples'], 'fixture_cleaned':True,
                'environment':{**{k:'fixture' for k in ['os','architecture','cpu','logical_cpus','memory_bytes','machine_id','python','sqlite','node','dependencies','python_packages','frontend_packages']}, 'cpu':'Fixture CPU', 'logical_cpus':4, 'memory_bytes':'17179869184'},
                'cases':[dict(id=c['id'], status='passed', **({'metrics':{m:[1,2,3,4] for m in c['metrics']}} if c['kind']=='latency' else {'tests':2, 'skipped':0,'execution_ms':10})) for c in reg['cases']],
                'release_requirements':reg['release_requirements'], 'gaps':reg['gaps'], 'wall_seconds':1}

    def test_complete_core_does_not_claim_complete_release(self):
        receipt=self.receipt(); self.assertEqual(bench.validate(receipt), [])
        result=bench.gate(receipt, expected_commit=self.commit, expected_version='0.1.6', root=self.repo)
        self.assertFalse(result['release_qualified'])
        with self.assertRaisesRegex(ValueError, 'ui.native.navigation'):
            bench.gate(receipt, expected_commit=self.commit, expected_version='0.1.6', root=self.repo, release=True)
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
            with self.assertRaises(ValueError):bench.gate(receipt, expected_commit=self.commit, expected_version='0.1.6', root=self.repo)

    def test_comparison_rejects_environment_schema_method_and_fixture_changes(self):
        for key in ['environment','fixture','suite','method']:
            left=self.receipt();right=copy.deepcopy(left);right[key]['changed']=True
            result=bench.compare(left,right,root=self.repo)
            self.assertFalse(result['comparable']);self.assertEqual(result['changes'],[])
        left=self.receipt();right=copy.deepcopy(left)
        right['source_start']['schema_versions']['schema']=2
        right['source_end']=copy.deepcopy(right['source_start'])
        self.assertFalse(bench.compare(left,right,root=self.repo)['comparable'])

    def test_comparable_versions_keep_raw_deltas_without_speed_claim(self):
        left=self.receipt();right=copy.deepcopy(left)
        right['source_start']=bench.committed_source(self.next_commit, root=self.repo)
        right['source_end']=copy.deepcopy(right['source_start'])
        right['cases'][0]['metrics']['cold_reader_ms']=[2,3,4,5]
        result=bench.compare(left,right,root=self.repo);self.assertTrue(result['comparable'])
        self.assertEqual(result['changes'][0]['delta_ms'],1)
        self.assertIn('Observed differences only',bench.report(right,result))

    def test_consistent_source_tampering_is_rejected_against_git_objects(self):
        for field, value in [('tree','e'*40), ('schema_sources',{'schema':'c'*64}),
                             ('schema_versions',{'schema':99}), ('application_version','9.9.9'),
                             ('database_compatibility',99), ('workspace_formats',[99]),
                             ('status_sha256','c'*64)]:
            receipt=self.receipt()
            for key in ('source_start','source_end'):receipt[key][field]=value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'Committed provenance'):
                bench.gate(receipt,expected_commit=self.commit,expected_version='0.1.6',root=self.repo)
            self.assertFalse(bench.compare(receipt,copy.deepcopy(receipt),root=self.repo)['comparable'])
        with self.assertRaisesRegex(ValueError,'Cannot verify committed provenance'):
            bench.gate(self.receipt(),expected_commit='f'*40,expected_version='0.1.6',root=self.repo)

    def test_matching_unknown_hardware_never_qualifies(self):
        for field,value in [('cpu','unavailable'),('cpu','unknown'),('memory_bytes','unavailable'),
                            ('memory_bytes',0),('memory_bytes',True),('logical_cpus','4')]:
            receipt=self.receipt();receipt['environment'][field]=value
            with self.subTest(field=field,value=value),self.assertRaisesRegex(ValueError,'diagnostic only'):
                bench.gate(receipt,expected_commit=self.commit,expected_version='0.1.6',root=self.repo)
            self.assertFalse(bench.compare(receipt,copy.deepcopy(receipt),root=self.repo)['comparable'])

    def test_legacy_diagnostics_upload_always_precedes_signing(self):
        import yaml
        workflow=yaml.safe_load((ROOT/'.github/workflows/workspace-release-candidate.yml').read_text())
        steps=workflow['jobs']['candidate']['steps']
        upload=next((i,s) for i,s in enumerate(steps) if s.get('with',{}).get('name')=='source-core-benchmark-diagnostics')
        signing=next(i for i,s in enumerate(steps) if s.get('name')=='Sign candidate with protected release key')
        gate=next(i for i,s in enumerate(steps) if s.get('name')=='Require complete benchmark qualification')
        self.assertEqual(upload[1]['if'],'always()')
        self.assertLess(upload[0],gate);self.assertLess(gate,signing)

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


class BenchmarkEnvironmentTests(unittest.TestCase):
    def test_dom_override_is_rejected_before_worker_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            for override in ('/untracked/external-dom.mjs', 'jsdom', ''):
                with self.subTest(override=override), patch.dict(os.environ, {'RIEKE_TEST_DOM_MODULE':override}), patch.object(bench.subprocess, 'Popen') as launch:
                    with self.assertRaisesRegex(ValueError, 'RIEKE_TEST_DOM_MODULE must be unset'):
                        bench.execute(['node', '--test'], Path(temporary)/'worker.log')
                    launch.assert_not_called()

    def test_dom_override_produces_failed_receipt_not_a_qualified_run(self):
        identity=bench.source()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'RIEKE_TEST_DOM_MODULE':'/untracked/external-dom.mjs'}), patch.object(bench, 'source', return_value=identity), patch.object(bench, 'environment', return_value={}), patch.object(bench, 'suite_identity', return_value={'sha256':'a'*64,'files':{}}), patch.object(bench.subprocess, 'Popen') as launch:
            output=Path(temporary)/'run'
            receipt=bench.run(output)
            launch.assert_not_called()
            self.assertIn('RIEKE_TEST_DOM_MODULE must be unset', receipt['error'])
            self.assertIn('Runner reported failure', receipt['validation_errors'])
            self.assertEqual(receipt['cases'], [])
            self.assertFalse(receipt['fixture_cleaned'])
            self.assertTrue((output/'benchmark.json').is_file())


if __name__=='__main__':unittest.main()
