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
        # These commits model two fixed versions independently of the app's
        # current release; copying that version made a real bump break the gate tests.
        release = json.loads((cls.repo/'rieke-release.json').read_text())
        release['version'] = '0.1.6'
        (cls.repo/'rieke-release.json').write_text(json.dumps(release))
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
                'suite':bench.suite_identity(self.repo, self.commit), 'fixture':{'version':reg['fixture_version'], 'sha256':bench.sha((ROOT/'tools/metadata_qualification/native-truth.json').read_bytes())},
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

    def test_renamed_suite_verifies_own_history_but_cannot_compare_or_gate_as_current(self):
        with tempfile.TemporaryDirectory(prefix='benchmark-comparison-test-') as temporary:
            repo = Path(temporary)/'repo'
            shutil.copytree(self.repo, repo)
            left = self.receipt()
            runner = repo/'tools/benchmark.py'
            runner.write_bytes(runner.read_bytes().replace(b"NAV_TESTS = ['workspace-navigation/workspaceNavigation'", b"NAV_TESTS = ['navigation/workspaceNavigation'"))
            self.assertNotEqual(runner.read_bytes(), (self.repo/'tools/benchmark.py').read_bytes())
            original = repo/'workspace-app/src/workspace-navigation/workspaceNavigation.test.js'
            moved = repo/'workspace-app/src/navigation/workspaceNavigation.test.js'
            moved.parent.mkdir();original.rename(moved)
            bench.git('add', '.', root=repo)
            bench.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Move test', root=repo)
            revision = bench.git('rev-parse', 'HEAD', root=repo)
            right = copy.deepcopy(left)
            right['source_start'] = bench.committed_source(revision, repo)
            right['source_end'] = copy.deepcopy(right['source_start'])
            right['suite'] = bench.suite_identity(repo, revision)
            self.assertEqual(bench.provenance_errors(left, self.commit, repo), [])
            self.assertEqual(bench.provenance_errors(right, revision, repo), [])
            comparison = bench.compare(left, right, root=repo)
            self.assertFalse(comparison['comparable']);self.assertEqual(comparison['changes'], [])
            self.assertIn('Noncomparable suite', comparison['reasons'])
            with self.assertRaisesRegex(ValueError, 'Stale/changed benchmark harness'):
                bench.gate(left, expected_commit=self.commit, expected_version='0.1.6', root=repo)
            for change in (lambda suite: suite['files'].pop('tools/benchmark.py'),
                           lambda suite: suite['files'].update({'tools/benchmark.py': '0'*64})):
                tampered = copy.deepcopy(right);change(tampered['suite'])
                self.assertIn('Suite differs from committed benchmark source', bench.provenance_errors(tampered, revision, repo))

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


class SuitePathTests(unittest.TestCase):
    # Independent expected recipe: do not derive expected keys from the parser.
    STATIC = [
        'tools/benchmark.py', 'benchmarks/requirements-py311.txt',
        'benchmarks/registry.json', 'benchmarks/receipt.schema.json', 'benchmarks/database.py',
        'workspace-app/src/benchmarkNavigation.mjs', 'workspace-app/isolatedViteCache.js',
        'tools/metadata_qualification/core_adapter.py', 'tools/metadata_qualification/truth.py',
        'tools/metadata_qualification/native-truth.json', 'tools/metadata_qualification/native-truth.seal.json',
        'python/tests/test_workspace_api.py', 'python/tests/test_workspace_curation.py',
        'python/tests/test_workspace_matlab.py',
    ]
    NAV = ['workspace-navigation/workspaceNavigation', 'inspectionNavigation', 'search-activation/pageReadCache',
           'traceReadContext', 'search-activation/navigationReadStrictMode', 'inspectorNavigationLifecycle']
    DB = ['test_workspace_sqlite', 'test_workspace_recipes', 'test_workspace_import_identities',
          'test_workspace_epoch_page_performance']
    SUPPORT = 'workspace-app/src/test-support/'
    LEGACY = [
        ('d6f30cb33260b0084497752da3c0715f679548e3', '1a6cf6e7b458e53b420060ef2c1ca6fd995414b027e986ccef3cf634ff1b4c15'),
        ('d0321f14b3eb46ebfe3c546e7b4e8b3159b6fe31', '7f869968d21470947c1eff71039da07700e90b226d8297c37b29003f77730a86'),
        ('1bf51d076c9083f0f34c5a319de424ac4cf8fc34', 'e55f10ae86eea89ea2a47ffd494b66ff5ede1c0e0404adcfcfaf6895431cc3ef'),
        ('802d181acdb5a02288e3704650835a7a33cee170', '45e45f94f40f7272a67a5588b405fc47ada401a9ab61329293c208e51bceff60'),
    ]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='benchmark-path-test-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.raw = (ROOT/'tools/benchmark.py').read_bytes()
        self.files = {name: ('fixture ' + name).encode() for name in self.expected_paths()}
        self.files.update({'tools/benchmark.py': self.raw,
                           self.SUPPORT+'reactTestEnvironment.js': b'preload',
                           self.SUPPORT+'old helper.js': b'old helper'})
        for name, raw in self.files.items():
            self.write(name, raw)
        self.git('init', '-q')
        self.first = self.commit()

    def expected_paths(self, nav=None):
        return [*self.STATIC, *['workspace-app/src/'+name+'.test.js' for name in (nav or self.NAV)],
                *['python/tests/'+name+'.py' for name in self.DB]]

    def write(self, name, raw):
        target = self.repo/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def git(self, *args):
        return bench.git(*args, root=self.repo)

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Source fixture')
        return self.git('rev-parse', 'HEAD')

    def identity(self, files):
        digests = {name: bench.sha(raw) for name, raw in files.items()}
        return {'files': digests, 'sha256': bench.sha(bench.canonical(digests))}

    def test_four_reviewed_legacy_blobs_preserve_full_original_recipes(self):
        for index, (revision, expected_hash) in enumerate(self.LEGACY):
            with self.subTest(revision=revision):
                raw = bench.committed_bytes(revision, 'tools/benchmark.py')
                self.assertEqual(bench.sha(raw), expected_hash)
                expected = self.expected_paths(nav=['workspaceNavigation', 'inspectionNavigation', 'pageReadCache',
                    'traceReadContext', 'navigationReadStrictMode', 'inspectorNavigationLifecycle'])
                if index == 0:
                    expected.remove('benchmarks/requirements-py311.txt')
                # Independent original algorithm, reading names from this revision.
                names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', '-r', '-z', '--name-only', revision, '--', self.SUPPORT]).split(b'\0')
                expected.extend(name.decode() for name in names if name)
                files = {name: bench.committed_bytes(revision, name) for name in expected}
                self.assertEqual(bench.suite_identity(ROOT, revision), self.identity(files))
                with self.assertRaisesRegex(ValueError, 'Unsupported legacy'):
                    bench._suite_recipe(raw + b'\n# unknown legacy bytes\n')

    def test_revision_owns_renamed_test_and_support_inventory_independent_of_globals(self):
        old = 'workspace-app/src/workspace-navigation/workspaceNavigation.test.js'
        new = 'workspace-app/src/navigation-fixture/workspaceNavigation.test.js'
        later = dict(self.files)
        later[new] = later.pop(old)
        del later[self.SUPPORT+'old helper.js']
        later[self.SUPPORT+'new helper.js'] = b'new helper'
        later[self.SUPPORT+'reactTestEnvironment.js'] = b'changed preload'
        later['tools/benchmark.py'] = self.raw.replace(b"NAV_TESTS = ['workspace-navigation/workspaceNavigation'", b"NAV_TESTS = ['navigation-fixture/workspaceNavigation'")
        self.assertNotEqual(later['tools/benchmark.py'], self.raw)
        (self.repo/old).unlink()
        (self.repo/(self.SUPPORT+'old helper.js')).unlink()
        for name, raw in later.items():
            self.write(name, raw)
        second = self.commit()
        with patch.object(bench, 'NAV_TESTS', ['wrong-current-global']), patch.object(bench, 'DB_TESTS', ['test_wrong_global']):
            self.assertEqual(bench.suite_identity(self.repo, self.first), self.identity(self.files))
            self.assertEqual(bench.suite_identity(self.repo, second), self.identity(later))
            self.assertEqual(bench.suite_identity(self.repo), self.identity(later))
            command = bench.frontend_command(root=self.repo, correctness=True)
            expected = [new, *['workspace-app/src/'+name+'.test.js' for name in self.NAV[1:]]]
            self.assertEqual(command[3:6], ['--test', '--test-reporter=tap', '--test-concurrency=1'])
            self.assertEqual(command[6:], [str(self.repo/name) for name in expected])
            self.assertTrue(set(expected) <= set(bench.suite_identity(self.repo)['files']))
        self.assertNotEqual(self.identity(self.files), self.identity(later))
        self.assertFalse((self.repo/old).exists())

    def test_strict_literals_paths_versions_and_bindings_never_execute_source(self):
        sentinel = self.repo/'must-not-exist'
        faults = [
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', b'SUITE_PATHS_VERSION = True'),
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', b'SUITE_PATHS_VERSION = 2'),
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', b'SUITE_PATHS_VERSION: int = 1'),
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', b'SUITE_PATHS_VERSION = other = 1'),
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', b'SUITE_PATHS_VERSION, other = (1, 1)'),
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', b'# no version marker'),
            self.raw.replace(b'SUITE_SUPPORT_ROOT =', b'OTHER_SUPPORT_ROOT ='),
            self.raw + b"\nNAV_TESTS += ['extra']\n",
            self.raw + b"\nNAV_TESTS = ['extra']\n",
            self.raw + b"\nNAV_TESTS.append('extra')\n",
            self.raw.replace(b"NAV_TESTS = ['workspace-navigation/workspaceNavigation'", b"NAV_TESTS = [str('workspaceNavigation')"),
            self.raw + b"\nNAV_TESTS[0] = 'other'\n",
            self.raw + b"\nif True:\n    NAV_TESTS = ['extra']\n",
            self.raw + b"\ntry:\n    pass\nexcept Exception as NAV_TESTS:\n    pass\n",
            self.raw + b"\nmatch []:\n    case [*NAV_TESTS]:\n        pass\n",
            self.raw.replace(b"NAV_TESTS = ['workspace-navigation/workspaceNavigation'", b"NAV_TESTS = ['inspectionNavigation'"),
            self.raw.replace(b"DB_TESTS = ['test_workspace_sqlite'", b"DB_TESTS = ['test_workspace_sqlite.py'"),
            self.raw.replace(b"'benchmarks/requirements-py311.txt',", b''),
            b'not python \xff',
            self.raw.replace(b'SUITE_PATHS_VERSION = 1', ("SUITE_PATHS_VERSION = __import__('pathlib').Path("+repr(str(sentinel))+").write_text('executed')").encode()),
        ]
        for invalid in ('../escape', '/absolute', 'a//b', 'a/./b', 'a/../b', 'a\\b', 'test.js', 'test.test', 'a*', 'a?', 'a[0]', 'a\x00', 'a\n'):
            faults.append(self.raw.replace(b"NAV_TESTS = ['workspace-navigation/workspaceNavigation'", ('NAV_TESTS = ['+repr(invalid)).encode()))
        with patch.object(bench.subprocess, 'Popen') as launch:
            for raw in faults:
                self.assertNotEqual(raw, self.raw, 'deliberate source mutation must change bytes')
                with self.subTest(raw=raw[-100:]), self.assertRaises(ValueError):
                    bench._suite_recipe(raw)
            launch.assert_not_called()
        self.assertFalse(sentinel.exists())

    def test_missing_paths_no_alias_fallback_and_no_worker_launch(self):
        missing = 'workspace-app/src/workspace-navigation/workspaceNavigation.test.js'
        (self.repo/missing).unlink()
        self.write('workspace-app/src/nested/workspaceNavigation.test.js', b'not an alias')
        with patch.object(bench.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'Cannot read suite file'):
                bench.frontend_command(root=self.repo, correctness=True)
            with self.assertRaises(ValueError):
                bench.suite_identity(self.repo)
            launch.assert_not_called()
        second = self.commit()
        with self.assertRaisesRegex(ValueError, 'Missing/unsupported committed suite file'):
            bench.suite_identity(self.repo, second)
        with self.assertRaisesRegex(ValueError, 'cannot be resolved'):
            bench.suite_identity(self.repo, 'f'*40)
        (self.repo/'tools/benchmark.py').unlink()
        third = self.commit()
        with self.assertRaises(ValueError):
            bench.suite_identity(self.repo, third)

    def test_regular_file_policy_for_working_and_committed_inputs(self):
        for name in ('workspace-app/src/workspace-navigation/workspaceNavigation.test.js', self.SUPPORT+'old helper.js'):
            target = self.repo/name
            target.unlink();target.symlink_to(self.repo/(self.SUPPORT+'reactTestEnvironment.js'))
            with self.assertRaisesRegex(ValueError, 'symlink'):
                bench.suite_identity(self.repo)
            revision = self.commit()
            with self.assertRaisesRegex(ValueError, 'unsupported|Unsupported'):
                bench.suite_identity(self.repo, revision)
            target.unlink();self.write(name, self.files[name]);self.commit()
        target = self.repo/(self.SUPPORT+'linked-directory')
        target.symlink_to(self.repo/'python', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            bench.suite_identity(self.repo)
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            bench.suite_identity(self.repo, revision)

    def test_support_enumeration_errors_cannot_silently_omit_files(self):
        with patch.object(bench.os, 'scandir', side_effect=PermissionError('fixture denied')):
            with self.assertRaisesRegex(ValueError, 'Cannot enumerate suite support files'):
                bench.suite_identity(self.repo)

    def test_fixed_preload_cannot_be_omitted(self):
        (self.repo/(self.SUPPORT+'reactTestEnvironment.js')).unlink()
        with self.assertRaisesRegex(ValueError, 'Missing fixed suite preload'):
            bench.suite_identity(self.repo)
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, 'Missing fixed suite preload'):
            bench.suite_identity(self.repo, revision)


class BenchmarkEnvironmentTests(unittest.TestCase):
    def test_run_commands_use_one_source_recipe_not_loaded_test_globals(self):
        commands = []
        def worker(command, log):
            commands.append(command)
            log.write_text('# tests 2\n# skipped 0\n# fail 0\n# cancelled 0\n# todo 0\n')
            if log.name in ('database.log', 'frontend.log'):
                Path(command[-1]).write_text(json.dumps({'fixture_cleaned': True, 'cases': []}))
            elif log.name == 'database-tests.log':
                Path(command[4]).write_text(json.dumps({'tests': 2, 'skipped': 0}))
            return 1
        with tempfile.TemporaryDirectory() as temporary, patch.object(bench, 'execute', side_effect=worker), patch.object(bench, 'environment', return_value={}), patch.object(bench, 'NAV_TESTS', ['wrong']), patch.object(bench, 'DB_TESTS', ['test_wrong']):
            receipt = bench.run(Path(temporary)/'run')
        self.assertNotIn('error', receipt)
        self.assertEqual(commands[-1][5:], SuitePathTests.DB)
        self.assertEqual(commands[-2][6:], [str(ROOT/('workspace-app/src/'+name+'.test.js')) for name in SuitePathTests.NAV])

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
