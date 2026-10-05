"""Public guard CLI on owned disposable repositories; no application/database startup."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / 'tools/architecture_guard.py'
CATALOG = 'docs/architecture/adopted-port-checks.json'

class ArchitectureGuardTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='disco-architecture-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Guard fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('AGENTS.md', '[Architecture](ARCHITECTURE.md)\n')
        self.write('ARCHITECTURE.md', '[Contract](docs/contract.md)\n')
        self.write('docs/contract.md', '# Contract\n\n## Recovery\n')
        self.write('python/policy.py', 'from flask import request\n')
        self.write('python/tests/test_policy.py', 'import unittest\nclass Policy(unittest.TestCase):\n def test_contract(self): self.assertTrue(True)\n')
        self.catalog = {'format':'disco-adopted-port-checks','version':1,
            'discovery':[{'from':'AGENTS.md','to':'ARCHITECTURE.md'},{'from':'ARCHITECTURE.md','to':'docs/contract.md'}],
            'shared_paths':['AGENTS.md','ARCHITECTURE.md','docs/contract.md',CATALOG],
            'contracts':[{'id':'recovery','contract':{'path':'docs/contract.md','heading':'Recovery'},
                'affected_paths':['python/**'],
                'rules':[{'language':'python','file':'python/policy.py','allow':['flask']}],
                'tests':{'python':['python/tests/test_policy.py'],'javascript':[]}}]}
        self.write_catalog()
        self.initial = self.commit()

    def write(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2)+'\n' if isinstance(value,dict) else value)

    def write_catalog(self):
        self.write(CATALOG,self.catalog)

    def git(self,*args):
        return subprocess.check_output(['git','-c','core.hooksPath=/dev/null',*args],cwd=self.root,text=True).strip()

    def commit(self):
        self.git('add','-A'); self.git('commit','-qm','Owned guard fixture')
        return self.git('rev-parse','HEAD')

    def cli(self,*args,success=True):
        result = subprocess.run([sys.executable,str(GUARD),'--root',str(self.root),*args],capture_output=True,text=True)
        self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
        return json.loads(result.stdout)

    def test_missing_contract_reference_is_a_failure(self):
        (self.root/'docs/contract.md').unlink()
        result=self.cli('check','--language','metadata',success=False)
        self.assertIn('docs/contract.md',result['error'])

    def test_python_ownership_rejects_nested_alias_import_and_dynamic_loader(self):
        for source in ['def f():\n import workspace_service as service\n',
                       'from workspace_service import WorkspaceService as Reader\n',
                       '__import__(name)\n']:
            self.write('python/policy.py',source)
            result=self.cli('check','--language','python',success=False)
            self.assertIn('python/policy.py',result['error'])

    def test_allowed_python_import_and_ordinary_import_text_pass(self):
        self.write('python/policy.py','from flask import request as req\n# import workspace_service\ntext="__import__(name)"\n')
        result=self.cli('check','--language','python')
        self.assertEqual(result['checked'],['metadata','python'])

    def test_plan_requires_explicit_valid_ancestor_and_maps_renames_and_deleted_paths(self):
        self.cli('plan',success=False)
        self.cli('plan','--base','missing-ref',success=False)
        self.git('mv','python/policy.py','python/renamed policy.py')
        self.catalog['contracts'][0]['rules'][0]['file']='python/renamed policy.py'
        self.write_catalog();self.commit()
        result=self.cli('plan','--base',self.initial)
        self.assertIn('python/policy.py',result['changed_paths'])
        self.assertIn('python/renamed policy.py',result['changed_paths'])
        self.assertEqual(result['affected_contracts'],['recovery'])
        self.assertEqual(result['tests']['python'],['python/tests/test_policy.py'])

    def test_unrelated_docs_skip_behavior_but_contract_and_explicit_all_select_it(self):
        self.write('docs/unrelated.md','# unrelated\n');self.commit()
        result=self.cli('plan','--base',self.initial)
        self.assertEqual(result['affected_contracts'],[])
        self.assertFalse(result['source_changed'])
        self.assertEqual(self.cli('plan','--all')['affected_contracts'],['recovery'])
        self.write('docs/contract.md','# Contract\n## Recovery\nUpdated explanation\n');self.commit()
        self.assertEqual(self.cli('plan','--base',self.initial)['affected_contracts'],['recovery'])

    def test_mapped_command_runs_behavior_and_propagates_failure(self):
        passed=self.cli('test','--all','--language','python')
        self.assertEqual(passed['runs'][0]['exit_code'],0)
        self.write('python/tests/test_policy.py','import unittest\nclass Policy(unittest.TestCase):\n def test_contract(self): self.assertEqual("wrong", "expected")\n')
        self.commit()
        failed=self.cli('test','--base',self.initial,'--language','python',success=False)
        self.assertEqual(failed['affected_contracts'],['recovery'])
        self.assertEqual(failed['runs'][0]['exit_code'],1)
        self.assertIn('wrong',failed['runs'][0]['output'])

    def test_mapped_python_suite_can_import_existing_sibling_test_fixtures(self):
        self.write('python/tests/fixture_support.py','VALUE=71\n')
        self.write('python/tests/test_policy.py','import unittest\nfrom fixture_support import VALUE\nclass Policy(unittest.TestCase):\n def test_contract(self): self.assertEqual(VALUE,71)\n')
        self.commit()
        self.assertEqual(self.cli('test','--all','--language','python')['runs'][0]['exit_code'],0)

    def test_missing_test_heading_discovery_and_escaping_paths_fail_closed(self):
        cases=[('python/tests/test_policy.py',None),('docs/contract.md','# Contract\n'),
               ('AGENTS.md','No discovery link\n')]
        for path,replacement in cases:
            original=(self.root/path).read_text()
            if replacement is None:(self.root/path).unlink()
            else:self.write(path,replacement)
            self.cli('check','--language','metadata',success=False)
            self.write(path,original)
        self.catalog['contracts'][0]['contract']['path']='../outside.md'
        self.write_catalog()
        self.assertIn('escapes',self.cli('check','--language','metadata',success=False)['error'])

    def test_unknown_catalog_fields_rule_kinds_and_duplicate_ids_fail(self):
        original=json.loads(json.dumps(self.catalog))
        for mutate in [lambda c:c.update(unknown=True),
                       lambda c:c['contracts'][0]['rules'][0].update(language='unknown'),
                       lambda c:c['contracts'].append(c['contracts'][0])]:
            self.catalog=json.loads(json.dumps(original));mutate(self.catalog);self.write_catalog()
            self.cli('check','--language','metadata',success=False)

    def test_dirty_unknown_zero_and_nonancestor_bases_never_produce_empty_green_plan(self):
        for base in ['missing','0'*40]:self.cli('plan','--base',base,success=False)
        self.write('python/uncommitted.py','# changed\n')
        self.assertIn('clean',self.cli('plan','--base',self.initial,success=False)['error'])
        self.assertTrue(self.cli('plan','--all')['dirty'])
        self.commit();head=self.git('rev-parse','HEAD')
        self.git('checkout','-q','--detach',self.initial)
        self.cli('plan','--base',head,success=False)

    def test_deletion_newline_paths_and_test_deduplication(self):
        self.write('python/old helper.py','# helper\n');before=self.commit()
        (self.root/'python/old helper.py').unlink()
        self.write('python/new\nhelper.py','# moved\n')
        duplicate=json.loads(json.dumps(self.catalog['contracts'][0]));duplicate['id']='also-recovery'
        self.catalog['contracts'].append(duplicate);self.write_catalog();self.commit()
        result=self.cli('plan','--base',before)
        self.assertIn('python/old helper.py',result['changed_paths'])
        self.assertIn('python/new\nhelper.py',result['changed_paths'])
        self.assertEqual(result['tests']['python'],['python/tests/test_policy.py'])

    def test_receipt_records_exact_source_and_github_job_selection(self):
        self.write('docs/contract.md','# Contract\n## Recovery\nClarified\n');self.commit()
        output=self.root/'.git/result.json';github=self.root/'.git/github-output'
        result=self.cli('plan','--base',self.initial,'--output',str(output),'--github-output',str(github))
        self.assertEqual(json.loads(output.read_text()),result)
        self.assertEqual(github.read_text(),'source_changed=false\njavascript_required=false\npython_required=true\ndesktop_required=false\n')
        self.assertEqual(len(result['source_sha256']['docs/contract.md']),64)

    def test_module_policy_version_is_explicit_and_nested_test_paths_remain_mapped(self):
        for version in (2, 3):
            with self.subTest(version=version):
                self.catalog['version'] = version
                self.write_catalog()
                self.assertIn(f'version {version} requires module policy', self.cli('check', '--language', 'metadata', success=False)['error'])
        self.catalog['version'] = 1
        self.catalog['javascript_module_policy'] = {}
        self.write_catalog()
        self.assertIn('version 1 forbids', self.cli('check', '--language', 'metadata', success=False)['error'])
        del self.catalog['javascript_module_policy']
        path = 'workspace-app/src/presentation/internal/helper.test.js'
        self.write(path, 'export {};')
        self.catalog['contracts'][0]['tests']['javascript'] = [path]
        self.catalog['contracts'][0]['affected_paths'].append('workspace-app/**')
        self.write_catalog()
        base = self.commit()
        self.write(path, '// changed nested contract\nexport {};')
        self.commit()
        result = self.cli('plan', '--base', base)
        self.assertEqual(result['tests']['javascript'], [path])
        self.assertTrue(result['javascript_required'])

    def test_unknown_versions_and_python_policy_are_not_implicitly_adopted(self):
        for version in (0, 4, 99):
            with self.subTest(version=version):
                self.catalog['version'] = version
                self.write_catalog()
                self.assertIn('Unsupported adopted-port', self.cli('check', '--language', 'metadata', success=False)['error'])
        for version in (1, 2, 3):
            with self.subTest(python_policy_version=version):
                self.catalog['version'] = version
                self.catalog['python_module_policy'] = {}
                self.write_catalog()
                self.assertIn('Invalid catalog fields', self.cli('check', '--language', 'metadata', success=False)['error'])

    def desktop_contract(self):
        self.write('desktop/tests/lifecycle.test.cjs',
            "const test=require('node:test'),assert=require('node:assert/strict');\n"
            "test('desktop contract',()=>{assert.equal(process.cwd(),__dirname.replace(/[/\\\\]desktop[/\\\\]tests$/,''));assert.ok(!process.execArgv.includes('--import'));});\n")
        entry=self.catalog['contracts'][0]
        entry['affected_paths'].append('desktop/**')
        entry['tests']['desktop']=['desktop/tests/lifecycle.test.cjs']
        self.write_catalog()

    @unittest.skipUnless(shutil.which('node'), 'Desktop CJS runner requires Node')
    def test_desktop_runner_uses_root_without_react_and_propagates_behavior_failure(self):
        self.desktop_contract()
        duplicate=json.loads(json.dumps(self.catalog['contracts'][0]));duplicate['id']='second-owner'
        self.catalog['contracts'].append(duplicate);self.write_catalog()
        passed=self.cli('test','--all','--language','desktop')
        self.assertEqual(passed['runs'][0]['command'],['node','--test','desktop/tests/lifecycle.test.cjs'])
        self.assertEqual(passed['runs'][0]['cwd'],str(self.root.resolve()))
        self.assertEqual(passed['runs'][0]['exit_code'],0)
        self.write('desktop/tests/lifecycle.test.cjs',"require('node:test')('receipt fault',()=>require('node:assert/strict').equal('unconfirmed','clean'));\n")
        self.commit()
        failed=self.cli('test','--base',self.initial,'--language','desktop',success=False)
        self.assertEqual(failed['runs'][0]['exit_code'],1)
        self.assertIn('unconfirmed',failed['runs'][0]['output'])

    def test_desktop_mapping_tracks_docs_renames_and_deleted_paths(self):
        self.desktop_contract();base=self.commit()
        self.write('docs/unrelated.md','# note\n');self.commit()
        self.assertFalse(self.cli('plan','--base',base)['desktop_required'])
        self.write('docs/contract.md','# Contract\n## Recovery\nClarified\n');self.commit()
        doc=self.cli('plan','--base',base)
        self.assertTrue(doc['desktop_required']);self.assertFalse(doc['source_changed'])
        base=self.git('rev-parse','HEAD')
        self.git('mv','desktop/tests/lifecycle.test.cjs','desktop/tests/renamed.test.cjs')
        self.catalog['contracts'][0]['tests']['desktop']=['desktop/tests/renamed.test.cjs']
        self.write_catalog();self.commit()
        result=self.cli('plan','--base',base)
        self.assertTrue(result['desktop_required'])
        self.assertIn('desktop/tests/lifecycle.test.cjs',result['changed_paths'])
        self.assertIn('desktop/tests/renamed.test.cjs',result['changed_paths'])

    def test_desktop_and_renderer_paths_cannot_be_misclassified(self):
        self.desktop_contract()
        self.write('workspace-app/src/view.test.js','export {};\n')
        tests=self.catalog['contracts'][0]['tests']
        tests['desktop']=['workspace-app/src/view.test.js'];self.write_catalog()
        self.assertIn('Invalid desktop test path',self.cli('check','--language','metadata',success=False)['error'])
        tests['desktop']=[];tests['javascript']=['desktop/tests/lifecycle.test.cjs'];self.write_catalog()
        self.assertIn('Invalid JavaScript test path',self.cli('check','--language','metadata',success=False)['error'])
        tests['javascript']=[];tests['unknown']=[];self.write_catalog()
        self.assertIn('Invalid catalog fields',self.cli('check','--language','metadata',success=False)['error'])

    def test_close_tests_are_narrowly_accepted_and_keep_mapped_execution(self):
        self.desktop_contract()
        name = 'desktop/close/tests/example.test.cjs'
        self.write(name, "require('node:test')('public seam', () => require('node:assert/strict').equal(1, 1));\n")
        self.catalog['contracts'][0]['tests']['desktop'] = [name]
        self.write_catalog()
        self.cli('check', '--language', 'metadata')
        if shutil.which('node'):
            result = self.cli('test', '--all', '--language', 'desktop')
            self.assertEqual(result['runs'][0]['command'], ['node', '--test', name])
            self.assertEqual(result['runs'][0]['exit_code'], 0)
        for invalid in ['desktop/close/owner.cjs', 'desktop/other/tests/example.test.cjs',
                        'desktop/close/tests/nested/example.test.cjs',
                        'desktop/close/testsuite/example.test.cjs']:
            self.write(invalid, '// invalid mapped location\n')
            self.catalog['contracts'][0]['tests']['desktop'] = [invalid]
            self.write_catalog()
            self.assertIn('Invalid desktop test path', self.cli('check', '--language', 'metadata', success=False)['error'])
        self.catalog['contracts'][0]['tests']['desktop'] = ['desktop/close/tests/../../../python/tests/test_policy.py']
        self.write_catalog()
        self.assertIn('escapes', self.cli('check', '--language', 'metadata', success=False)['error'])

    def test_state_owner_test_roots_preserve_narrow_mapping_and_execution(self):
        self.desktop_contract()
        for owner in ('drafts', 'startup'):
            with self.subTest(owner=owner):
                name = f'desktop/{owner}/tests/public.test.cjs'
                self.write(name, "require('node:test')('state contract', () => require('node:assert/strict').equal(1, 1));\n")
                self.catalog['contracts'][0]['tests']['desktop'] = [name]
                self.write_catalog()
                self.cli('check', '--language', 'metadata')
                if shutil.which('node'):
                    result = self.cli('test', '--all', '--language', 'desktop')
                    self.assertEqual(result['runs'][0]['command'], ['node', '--test', name])
                    self.assertEqual(result['runs'][0]['exit_code'], 0)
                for invalid in [f'desktop/{owner}/owner.cjs', f'desktop/{owner}/tests/nested/a.test.cjs',
                                f'desktop/{owner}/testsuite/a.test.cjs', 'desktop/other/tests/a.test.cjs']:
                    self.write(invalid, '// rejected location\n')
                    self.catalog['contracts'][0]['tests']['desktop'] = [invalid]
                    self.write_catalog()
                    self.assertIn('Invalid desktop test path', self.cli('check', '--language', 'metadata', success=False)['error'])
                self.catalog['contracts'][0]['tests']['desktop'] = [f'desktop/{owner}/tests/../../../python/tests/test_policy.py']
                self.write_catalog()
                self.assertIn('escapes', self.cli('check', '--language', 'metadata', success=False)['error'])
                with tempfile.TemporaryDirectory(prefix='disco-outside-test-') as outside:
                    target = Path(outside) / 'escape.test.cjs'
                    target.write_text('// outside repository\n')
                    link = self.root / f'desktop/{owner}/tests/escape.test.cjs'
                    link.symlink_to(target)
                    self.catalog['contracts'][0]['tests']['desktop'] = [str(link.relative_to(self.root))]
                    self.write_catalog()
                    self.assertIn('escapes', self.cli('check', '--language', 'metadata', success=False)['error'])

if __name__ == '__main__': unittest.main()
