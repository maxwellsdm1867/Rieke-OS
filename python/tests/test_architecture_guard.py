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
        for version in (0, 6, 99):
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
        for owner in ('drafts', 'startup', 'integrity', 'updates'):
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

class PythonPackagePolicyTests(unittest.TestCase):
    """v4 through the public guard CLI; owned source/Git and stdlib tests only."""
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='disco-python-policy-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.write('AGENTS.md', '[Contract](docs/contract.md)')
        self.write('docs/contract.md', '# Recovery\n')
        self.write('python/disco/__init__.py', '"""Inert ancestor."""\n')
        self.write('python/disco/recovery/__init__.py', 'from .implementation import callback\n__all__ = ("callback",)\n')
        self.write('python/disco/recovery/implementation.py', 'def callback(value):\n return value\n')
        self.write('python/disco/recovery/tests/__init__.py', '')
        self.write('python/disco/recovery/tests/test_policy.py',
                   'import unittest\nfrom disco.recovery import callback\nfrom fixture_support import VALUE\n'
                   'class Public(unittest.TestCase):\n def test_public(self): self.assertEqual(callback(VALUE), 71)\n')
        self.write('python/tests/fixture_support.py', 'VALUE = 71\n')
        self.write('python/tests/test_central.py', 'import unittest\nclass Central(unittest.TestCase):\n def test_central(self): self.assertTrue(True)\n')
        self.write('python/consumer.py', 'from disco.recovery import callback\nanswer = callback(1)\n')
        self.write('workspace-app/src/public.js', 'export const value = 1;')
        self.write('workspace-app/src/public.test.js', 'import {value} from "./public.js";')
        self.write('workspace-app/src/test-support/support.js', 'export {};')
        self.write('workspace-app/package.json', '{}')
        self.write('workspace-app/package-lock.json', '{}')
        self.write('workspace-app/vite.config.js', 'export {};')
        for name in ('runTests.mjs', 'architectureImports.mjs'):
            self.write('workspace-app/' + name, (ROOT / 'workspace-app' / name).read_text())
        import hashlib
        self.catalog = {'format': 'disco-adopted-port-checks', 'version': 4,
            'discovery': [{'from': 'AGENTS.md', 'to': 'docs/contract.md'}], 'shared_paths': ['docs/**'],
            'contracts': [{'id': 'recovery', 'contract': {'path': 'docs/contract.md', 'heading': 'Recovery'},
                'affected_paths': ['python/disco/recovery/**'],
                'rules': [{'language': 'python', 'file': 'python/disco/recovery/__init__.py', 'allow': ['disco.recovery.implementation']},
                          {'language': 'python', 'file': 'python/disco/recovery/implementation.py', 'allow': []}],
                'tests': {'python': ['python/disco/recovery/tests/test_policy.py', 'python/tests/test_central.py'], 'javascript': []}},
                {'id': 'js', 'contract': {'path': 'docs/contract.md', 'heading': 'Recovery'}, 'affected_paths': ['workspace-app/**'],
                 'rules': [{'language': 'javascript', 'file': 'workspace-app/src/public.js', 'allow': []}],
                 'tests': {'python': [], 'javascript': ['workspace-app/src/public.test.js']}}],
            'javascript_module_policy': {'source_root': 'workspace-app/src', 'test_support_roots': ['workspace-app/src/test-support'],
                'test_tool_files': [], 'package_manifest': 'workspace-app/package.json', 'package_lock': 'workspace-app/package-lock.json',
                'resolver_config': {'path': 'workspace-app/vite.config.js', 'sha256': hashlib.sha256(b'export {};').hexdigest()},
                'dom_override_test_files': [], 'modules': [{'contract_id': 'js', 'root': 'workspace-app/src',
                    'public_entries': [{'path': 'workspace-app/src/public.js', 'exports': ['value']}], 'private_test_edges': []}],
                'additional_sources': [], 'tool_external_imports': [], 'virtual_import_edges': []},
            'python_module_policy': {'source_root': 'python',
                'test_roots': ['python/tests', 'python/disco/recovery/tests'], 'fixture_pythonpath': ['python/tests'],
                'reviewed_loader_sites': [], 'modules': [{'contract_id': 'recovery', 'root': 'python/disco/recovery',
                    'public_module': 'disco.recovery', 'public_entry': 'python/disco/recovery/__init__.py',
                    'public_exports': [{'name': 'callback', 'from': 'python/disco/recovery/implementation.py'}], 'private_test_edges': []}]}}
        self.write('tools/architecture_guard.py', GUARD.read_text())
        self.write('tools/architecture_module_policy.py', (ROOT / 'tools/architecture_module_policy.py').read_text())
        self.git('init', '-q'); self.git('config', 'user.name', 'Guard fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        self.write(CATALOG, json.dumps(self.catalog))
        self.git('add', '-A'); self.git('commit', '-qm', 'baseline')

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=self.root, text=True).strip()

    def cli(self, *args, success=True):
        self.write(CATALOG, json.dumps(self.catalog))
        run = subprocess.run([sys.executable, '-B', str(GUARD), '--root', str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(run.returncode == 0, success, run.stdout + run.stderr)
        return json.loads(run.stdout)

    def check(self, success=True, language='python'):
        return self.cli('check', '--language', language, success=success)

    def fault(self, text):
        self.write('python/consumer.py', text)
        return self.check(False)['error']

    def bind_loader(self, name, embedded=False):
        import ast
        import hashlib
        text = (self.root / name).read_text()
        if embedded:
            node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign))
            sites = [{'selector': 'assignment:PROBE', 'kind': 'embedded-python', 'ast_sha256': hashlib.sha256(node.value.value.encode()).hexdigest()}]
        else:
            node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call))
            sites = [{'selector': 'call:import_module:1', 'kind': 'ast-call',
                      'ast_sha256': hashlib.sha256(ast.dump(node, annotate_fields=True, include_attributes=False).encode()).hexdigest()}]
        self.catalog['python_module_policy']['reviewed_loader_sites'] = [
            {'file': name, 'file_sha256': hashlib.sha256(text.encode()).hexdigest(), 'sites': sites, 'reason': 'Reviewed inert fixture; never executed'}]

    def test_public_import_alias_and_module_attribute_pass(self):
        for source in ('from disco.recovery import callback\ncallback(1)',
                       'from disco.recovery import callback as cb\ncb(1)',
                       'import disco.recovery as recovery\nrecovery.callback(1)',
                       'import disco.recovery as recovery\nalias = recovery\nalias.callback(1)',
                       'def use():\n from disco.recovery import callback\n return callback(1)'):
            self.write('python/consumer.py', source)
            self.assertEqual(self.check()['checked'], ['metadata', 'python'])
        result = self.check()
        self.assertIn('python/consumer.py', result['source_sha256'])
        self.assertIn('python/tests/fixture_support.py', result['source_sha256'])

    def test_private_alias_star_and_reflective_edges_fail_without_prefix_escape(self):
        for source in ('import disco.recovery.implementation as impl',
                       'from disco.recovery.implementation import callback',
                       'from disco.recovery import implementation',
                       'from disco import recovery', 'from disco.recovery import *',
                       'import disco.recovery as r\nr.implementation.callback(1)',
                       'import disco.recovery as r\nalias = r\nalias.implementation.callback(1)',
                       'import disco.recovery as r\nalias = r\nalias = object()',
                       'import disco.recovery as r\ngetattr(r, "implementation")',
                       'import disco.recovery as r\nforward(r)',
                       'import disco.recovery as r\nr = object()',
                       'import disco.recovery',
                       'from disco.recovery import callback as cb\ncb.__globals__',
                       'from disco.recovery import callback as cb\ngetattr(cb, "__globals__")'):
            with self.subTest(source=source): self.fault(source)
        self.catalog['contracts'][0]['rules'].append({'language': 'python', 'file': 'python/consumer.py', 'allow': ['disco']})
        self.assertIn('private Python', self.fault('import disco.recovery.implementation'))

    def test_downstream_shims_fail_but_module_level_test_imports_and_unrelated_helpers_pass(self):
        self.write('python/tests/helper.py', 'from disco.recovery import callback as cb\nalias = cb\ndef ordinary(): return 1\n')
        self.write('python/tests/test_central.py', 'from helper import ordinary\n')
        self.check()
        for source in ('from helper import cb', 'from helper import alias', 'import helper as h\nh.cb(1)', 'import helper as h\nalias = h\nalias.cb(1)', 'from helper import *'):
            with self.subTest(source=source):
                self.write('python/tests/test_central.py', source)
                self.assertIn('re-export shim', self.check(False)['error'])
        self.write('python/tests/test_central.py', 'from helper import ordinary')
        self.write('python/tests/helper.py', 'from disco.recovery import callback\n__all__ = ["callback"]')
        self.assertIn('re-export declaration', self.check(False)['error'])

    def test_downstream_module_binding_shims_cannot_expose_public_package(self):
        self.write('python/tests/helper.py', 'import disco.recovery as recovery\ndef ordinary(): return 1')
        for source in ('from helper import recovery\nrecovery.callback(1)',
                       'import helper\nhelper.recovery.callback(1)',
                       'import helper as h\nalias = h\nalias.recovery.callback(1)',
                       '__import__("helper", fromlist=["recovery"])',
                       'import helper\nhelper.__dict__["recovery"].callback(1)',
                       'import helper\nhelper.unknown.callback(1)'):
            with self.subTest(source=source):
                self.write('python/tests/test_central.py', source); self.check(False)
        self.write('python/tests/test_central.py', 'from helper import ordinary')
        self.check()

    def test_public_surface_and_inert_ancestor_faults_fail(self):
        name = 'python/disco/recovery/__init__.py'; original = (self.root / name).read_text()
        for source in ('from .implementation import callback', original + '\nextra = 1',
                       'from .implementation import *\n__all__ = ("callback",)',
                       'from .implementation import callback as renamed\n__all__ = ("renamed",)',
                       original.replace('("callback",)', '("other",)')):
            with self.subTest(source=source):
                self.write(name, source); self.check(False)
        self.write(name, original)
        self.write('python/disco/__init__.py', 'from . import recovery')
        self.assertIn('inert initializer', self.check(False, 'metadata')['error'])

    def test_new_production_and_test_roots_and_production_to_test_imports_fail(self):
        self.write('python/disco/recovery/new.py', '')
        self.assertIn('ownership allow rule', self.check(False, 'metadata')['error'])
        (self.root / 'python/disco/recovery/new.py').unlink()
        self.assertIn('production cannot import', self.fault('from fixture_support import VALUE'))
        self.write('python/consumer.py', '')
        self.write('python/test_outside.py', '')
        self.assertIn('Unclassified Python test', self.check(False, 'metadata')['error'])
        (self.root / 'python/test_outside.py').unlink()
        self.write('python/disco/recovery/tests/test_unmapped.py', '')
        self.assertIn('Unmapped owner-local', self.check(False, 'metadata')['error'])

    def test_private_tests_need_exact_used_exceptions(self):
        test = 'python/disco/recovery/tests/test_policy.py'; private = 'python/disco/recovery/implementation.py'
        self.write(test, 'from disco.recovery.implementation import callback')
        self.assertIn('private Python', self.check(False)['error'])
        module = self.catalog['python_module_policy']['modules'][0]
        module['private_test_edges'] = [{'from': test, 'to': private}]
        self.check()
        self.write(test, 'from disco.recovery import callback')
        self.assertIn('Unused Python private test', self.check(False)['error'])

    def test_unrelated_computed_loaders_and_aliases_fail_without_adopted_import(self):
        for source in ('import importlib\nimportlib.import_module(name)',
                       'from importlib import import_module as load\nload(name)',
                       'import importlib as library\nload = library.import_module\nload(name)',
                       'load = __import__\nload(name)',
                       'import importlib\nforward(importlib.import_module)',
                       'from importlib import import_module as load\nload = unknown\nload(name)',
                       'exec(source)', 'import runpy\nrunpy.run_path(path)'):
            with self.subTest(source=source):
                self.write('python/tests/test_central.py', source)
                self.assertIn('Python loader', self.check(False)['error'])
        self.write('python/tests/test_central.py', 'context = __import__("contextvars")\ntext = "__import__(name)"')
        self.check()
        self.write('python/tests/test_central.py', 'import importlib\nimportlib.import_module("disco.recovery.implementation")')
        self.assertIn('dynamic access', self.check(False)['error'])
        self.write('python/tests/test_central.py', '__import__("disco", fromlist=["recovery"])')
        self.assertIn('dynamic access', self.check(False)['error'])

    def test_exact_loader_bindings_reject_changed_removed_and_unused_sites(self):
        name = 'python/tests/test_central.py'
        original = 'import importlib\nimportlib.import_module(name)\n'
        self.write(name, original); self.bind_loader(name); self.check()
        self.write(name, original + '# changed\n')
        self.assertIn('source changed', self.check(False, 'metadata')['error'])
        self.write(name, '# removed\n')
        import hashlib
        self.catalog['python_module_policy']['reviewed_loader_sites'][0]['file_sha256'] = hashlib.sha256(b'# removed\n').hexdigest()
        self.assertIn('unused Python loader', self.check(False)['error'])
        self.write(name, original); self.bind_loader(name)
        self.catalog['python_module_policy']['reviewed_loader_sites'][0]['sites'][0]['ast_sha256'] = '0' * 64
        self.assertIn('Python loader', self.check(False)['error'])

    def test_embedded_probe_string_is_bound_even_when_assignment_is_removed(self):
        name = 'python/workspace_bootstrap.py'
        self.write(name, 'PROBE = "import external_parser"\n'); self.bind_loader(name, embedded=True); self.check()
        self.write(name, 'RENAMED = "import external_parser"\n')
        import hashlib
        self.catalog['python_module_policy']['reviewed_loader_sites'][0]['file_sha256'] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.assertIn('unused Python loader', self.check(False)['error'])

    def test_v4_requires_both_policies_and_rejects_malformed_duplicate_roots(self):
        original = json.loads(json.dumps(self.catalog))
        for key in ('python_module_policy', 'javascript_module_policy'):
            self.catalog = json.loads(json.dumps(original)); del self.catalog[key]
            self.assertIn('requires', self.check(False, 'metadata')['error'])
        for value in (None, [], 'invalid'):
            self.catalog = json.loads(json.dumps(original)); self.catalog['python_module_policy'] = value
            self.check(False, 'metadata')
        for mutation in (lambda p: p.update(extra=True), lambda p: p['modules'].append(p['modules'][0]),
                         lambda p: p['test_roots'].append('python/tests'),
                         lambda p: p['modules'][0]['public_exports'].append(p['modules'][0]['public_exports'][0])):
            self.catalog = json.loads(json.dumps(original)); mutation(self.catalog['python_module_policy'])
            self.check(False, 'metadata')

    def test_mapped_local_tests_run_once_with_central_fixture_pythonpath_and_failures(self):
        result = self.cli('test', '--all', '--language', 'python')
        command = result['runs'][0]['command']
        self.assertEqual(command.count('disco.recovery.tests.test_policy'), 1)
        self.assertIn('python.tests.test_central', command)
        self.assertIn('Ran 2 tests', result['runs'][0]['output'])
        self.write('python/tests/fixture_support.py', 'VALUE = 72')
        self.assertEqual(self.cli('test', '--all', '--language', 'python', success=False)['status'], 'failed')

    def test_local_discovery_lexical_scopes_and_loader_forwarding(self):
        env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(self.root / 'python'), str(self.root / 'python/tests')])}
        run = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'python/disco/recovery/tests', '-t', 'python', '-p', 'test_*.py', '-v'],
                             cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('Ran 1 test', run.stderr)
        self.write('python/tests/helper.py', 'from disco.recovery import callback\ndef ordinary(callback): return callback(1)\n')
        self.write('python/tests/test_central.py', 'from helper import ordinary')
        self.check()
        self.write('python/tests/test_central.py', 'import helper\nforward(helper)')
        self.assertIn('opaque', self.check(False)['error'])
        self.write('python/tests/test_central.py', 'from helper import ordinary')
        self.write('python/disco/recovery/implementation.py', 'values = [callback for callback in []]')
        self.assertIn('Missing Python implementation export', self.check(False)['error'])
        self.write('python/disco/recovery/implementation.py', 'from .implementation import callback')
        self.catalog['contracts'][0]['rules'][1]['allow'] = ['disco.recovery.implementation']
        self.assertIn('Missing Python implementation export', self.check(False)['error'])

    def test_reviewed_relative_loader_and_definition_scope_faults(self):
        name = 'python/tests/test_central.py'
        for source in (
            "__import__('implementation', {'__package__':'disco.recovery'}, {}, ['callback'], 1)",
            "__import__('implementation', fromlist=['callback'], level=1)",
            "__import__('contextvars', fromlist=names)",
            "from importlib import import_module as load\ndef f(load=load(name)): pass",
            "from importlib import import_module as load\nclass C:\n load=None\n def f(self): load(name)",
            "import disco.recovery as recovery\ndef f(recovery=recovery.implementation): pass",
            "import disco.recovery as recovery\n@recovery.implementation.decorate\ndef f(recovery): pass",
            "import disco.recovery as recovery\nclass C(recovery.implementation.Base):\n recovery=None",
            "import disco.recovery as recovery\nitems=[recovery for recovery in recovery.implementation.items]",
        ):
            with self.subTest(source=source):
                self.write(name, source); self.check(False)
        self.write(name, "__import__('contextvars', fromlist=['ContextVar'], level=0)")
        self.check()
        self.write('python/disco/recovery/implementation.py', 'callback: object')
        self.assertIn('Missing Python implementation export', self.check(False)['error'])

    def test_v4_duplicate_declarations_fail_but_cross_contract_reuse_passes(self):
        tests = self.catalog['contracts'][0]['tests']['python']
        tests.append(tests[0])
        self.assertIn('Duplicate test path', self.check(False, 'metadata')['error'])
        tests.pop()
        self.catalog['contracts'][1]['tests']['python'] = [tests[0]]
        self.check()

    def test_new_outside_consumer_selects_policy_and_symlink_test_target_fails(self):
        self.cli('check', '--language', 'metadata')
        base = self.git('rev-parse', 'HEAD')
        self.write('python/new_consumer.py', 'from disco.recovery import callback')
        self.git('add', '-A'); self.git('commit', '-qm', 'consumer')
        result = self.cli('plan', '--base', base)
        self.assertIn('recovery', result['affected_contracts'])
        self.assertIn('python/new_consumer.py', result['source_sha256'])
        target = self.root / 'python/disco/recovery/tests/test_policy.py'; target.unlink()
        target.symlink_to(self.root / 'python/tests/test_central.py')
        self.assertIn('symlink', self.check(False, 'metadata')['error'])


class PythonNamedEntryPolicyTests(unittest.TestCase):
    """v5 named leaves via the existing CLI; no product imports or fixtures."""
    write = PythonPackagePolicyTests.write
    git = PythonPackagePolicyTests.git
    cli = PythonPackagePolicyTests.cli
    check = PythonPackagePolicyTests.check
    fault = PythonPackagePolicyTests.fault

    def setUp(self):
        PythonPackagePolicyTests.setUp(self)
        self.catalog['version'] = 5
        self.write('python/disco/backup/__init__.py', '"""Inert backup namespace."""\n')
        self.write('python/disco/backup/snapshot.py',
                   'import pathlib\nLIMIT = 4\ndef save(value): return value\n'
                   'def _existing(value): return value\nclass Snapshot:\n @staticmethod\n def empty(): return 0\n')
        self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\n')
        self.write('python/disco/backup/private.py', 'def secret(): return 9\n')
        self.write('python/disco/backup/tests/__init__.py', '')
        self.write('python/disco/backup/tests/test_snapshot.py',
                   'import unittest\nfrom disco.backup.snapshot import save\n'
                   'class Public(unittest.TestCase):\n def test_public(self): self.assertEqual(save(73), 73)\n')
        self.module = {'contract_id': 'backup', 'root': 'python/disco/backup',
                       'public_entries': [
                           {'path': 'python/disco/backup/snapshot.py', 'module': 'disco.backup.snapshot',
                            'exports': ['LIMIT', 'save', '_existing', 'Snapshot', 'pathlib']},
                           {'path': 'python/disco/backup/clock.py', 'module': 'disco.backup.clock',
                            'exports': ['LIMIT', 'tick']}], 'private_test_edges': []}
        self.catalog['python_module_policy']['modules'].append(self.module)
        self.catalog['python_module_policy']['test_roots'].append('python/disco/backup/tests')
        self.contract = {'id': 'backup', 'contract': {'path': 'docs/contract.md', 'heading': 'Recovery'},
                         'affected_paths': ['python/disco/backup/**'],
                         'rules': [{'language': 'python', 'file': 'python/disco/backup/' + leaf,
                                    'allow': ['pathlib'] if leaf == 'snapshot.py' else []}
                                   for leaf in ('__init__.py', 'snapshot.py', 'clock.py', 'private.py')],
                         'tests': {'python': ['python/disco/backup/tests/test_snapshot.py'], 'javascript': []}}
        self.catalog['contracts'].append(self.contract)

    def test_legacy_private_test_edge_does_not_allow_public_shim(self):
        path = 'python/disco/recovery/implementation.py'
        self.write(path, (self.root / path).read_text() + '\nfrom disco.recovery import callback as forwarded\n')
        self.catalog['contracts'][0]['rules'][1]['allow'].append('disco.recovery')
        test_path = 'python/disco/recovery/tests/test_policy.py'
        self.catalog['python_module_policy']['modules'][0]['private_test_edges'] = [{'from': test_path, 'to': path}]
        for version in (4, 5):
            if version == 4:
                self.catalog['version'] = 4
                named = self.catalog['python_module_policy']['modules'].pop()
                named_contract = self.catalog['contracts'].pop()
                named_test_path = self.root / 'python/disco/backup/tests/test_snapshot.py'
                named_test = named_test_path.read_text()
                named_test_path.unlink()
                self.catalog['python_module_policy']['test_roots'].remove('python/disco/backup/tests')
            else:
                self.catalog['version'] = 5
                self.catalog['python_module_policy']['modules'].append(named)
                self.catalog['contracts'].append(named_contract)
                named_test_path.write_text(named_test)
                self.catalog['python_module_policy']['test_roots'].append('python/disco/backup/tests')
            for source in ('from disco.recovery.implementation import forwarded\nforwarded(1)',
                           'import disco.recovery.implementation as impl\nimpl.forwarded(1)'):
                with self.subTest(version=version, source=source):
                    self.write(test_path, source)
                    self.assertIn('public re-export shim', self.check(False)['error'])

    def test_named_class_dunder_allows_same_owner_production_and_aliases(self):
        path = 'python/disco/backup/snapshot.py'
        original = (self.root / path).read_text()
        self.write(path, original + '\ninstance = Snapshot.__new__(Snapshot)\n')
        self.check()
        self.write(path, original)
        self.contract['rules'][2]['allow'].append('disco.backup.snapshot')
        for source in (
            'from .snapshot import Snapshot\ninstance = Snapshot.__new__(Snapshot)',
            'from .snapshot import Snapshot as Imported\nAlias = Imported\ninstance = Alias.__new__(Alias)',
            'import disco.backup.snapshot as snapshot\nAlias = snapshot.Snapshot\ninstance = Alias.__new__(Alias)',
        ):
            with self.subTest(source=source):
                self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\n' + source)
                self.check()

    def test_named_class_dunder_rejects_cross_owner_production_and_same_owner_tests(self):
        self.catalog['contracts'][0]['rules'][1]['allow'].append('disco.backup.snapshot')
        for path in ('python/disco/recovery/implementation.py',
                     'python/disco/backup/tests/test_snapshot.py'):
            original = (self.root / path).read_text()
            for expression in ('Snapshot.__new__(Snapshot)', 'Alias.__new__(Alias)'):
                with self.subTest(path=path, expression=expression):
                    self.write(path, original + '\nfrom disco.backup.snapshot import Snapshot\n'
                               'Alias = Snapshot\ninstance = ' + expression + '\n')
                    self.assertIn('reflective Python named value attribute', self.check(False)['error'])
            self.write(path, original)

    def test_named_class_dunder_uses_imported_and_reexported_origin_owner(self):
        self.write('python/disco/foreign/__init__.py', '"""Inert foreign owner."""\n')
        self.write('python/disco/foreign/model.py', 'class ForeignSnapshot: pass\n')
        self.write('python/disco/foreign/tests/__init__.py', '')
        self.catalog['python_module_policy']['test_roots'].append('python/disco/foreign/tests')
        self.catalog['python_module_policy']['modules'].append({
            'contract_id': 'foreign', 'root': 'python/disco/foreign', 'private_test_edges': [],
            'public_entries': [{'path': 'python/disco/foreign/model.py',
                                'module': 'disco.foreign.model', 'exports': ['ForeignSnapshot']}]})
        self.catalog['contracts'].append({
            'id': 'foreign', 'contract': {'path': 'docs/contract.md', 'heading': 'Recovery'},
            'affected_paths': ['python/disco/foreign/**'],
            'rules': [{'language': 'python', 'file': 'python/disco/foreign/' + leaf, 'allow': []}
                      for leaf in ('__init__.py', 'model.py')],
            'tests': {'python': ['python/tests/test_central.py'], 'javascript': []}})
        path = 'python/disco/backup/snapshot.py'
        self.write(path, (self.root / path).read_text() +
                   '\nfrom disco.foreign.model import ForeignSnapshot\n')
        self.module['public_entries'][0]['exports'].append('ForeignSnapshot')
        self.contract['rules'][1]['allow'].append('disco.foreign.model')
        self.contract['rules'][2]['allow'].extend(['disco.foreign.model', 'disco.backup.snapshot'])
        for origin in ('disco.foreign.model', 'disco.backup.snapshot'):
            with self.subTest(origin=origin):
                self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\n'
                           f'from {origin} import ForeignSnapshot\nAlias = ForeignSnapshot\n'
                           'instance = Alias.__new__(Alias)\n')
                self.assertIn('reflective Python named value attribute', self.check(False)['error'])

    def test_named_class_dunder_exception_keeps_legacy_callable_rejection(self):
        self.contract['rules'][2]['allow'].append('disco.recovery')
        self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\n'
                   'from disco.recovery import callback\nAlias = callback\nname = Alias.__name__\n')
        self.assertIn('reflective Python public callable attribute', self.check(False)['error'])

    def thread_local_fixture(self):
        path = 'python/disco/backup/snapshot.py'
        self.write(path, (self.root / path).read_text() + '\nimport threading\n_LOCAL_STATE = threading.local()\n')
        self.contract['rules'][1]['allow'].append('threading')
        self.module['public_entries'][0]['exports'].append('_LOCAL_STATE')
        return path

    def test_named_getattr_allows_same_owner_thread_local_and_alias(self):
        path = self.thread_local_fixture()
        self.write(path, (self.root / path).read_text() +
                   '\nlocked = getattr(_LOCAL_STATE, "locked", False)\n'
                   'Alias = _LOCAL_STATE\nprevious = getattr(Alias, "locked", False)\n')
        self.check()
        self.contract['rules'][2]['allow'].append('disco.backup.snapshot')
        self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\n'
                   'from .snapshot import _LOCAL_STATE as state\nlocked = getattr(state, "locked", False)\n')
        self.check()

    def test_named_getattr_rejects_external_owner_and_same_owner_tests(self):
        self.thread_local_fixture()
        self.catalog['contracts'][0]['rules'][1]['allow'].append('disco.backup.snapshot')
        for path in ('python/consumer.py', 'python/disco/recovery/implementation.py',
                     'python/disco/backup/tests/test_snapshot.py'):
            original = (self.root / path).read_text()
            with self.subTest(path=path):
                self.write(path, original + '\nfrom disco.backup.snapshot import _LOCAL_STATE as state\n'
                           'locked = getattr(state, "locked", False)\n')
                self.assertIn('reflective Python public callable access', self.check(False)['error'])
            self.write(path, original)

    def test_named_getattr_rejects_foreign_reexported_thread_local(self):
        self.thread_local_fixture()
        self.write('python/disco/foreign/__init__.py', '"""Inert foreign owner."""\n')
        self.write('python/disco/foreign/model.py', 'from disco.backup.snapshot import _LOCAL_STATE\n')
        self.write('python/disco/foreign/consumer.py',
                   'from .model import _LOCAL_STATE as state\nlocked = getattr(state, "locked", False)\n')
        self.write('python/disco/foreign/tests/__init__.py', '')
        self.catalog['python_module_policy']['test_roots'].append('python/disco/foreign/tests')
        self.catalog['python_module_policy']['modules'].append({
            'contract_id': 'foreign', 'root': 'python/disco/foreign', 'private_test_edges': [],
            'public_entries': [{'path': 'python/disco/foreign/model.py',
                                'module': 'disco.foreign.model', 'exports': ['_LOCAL_STATE']}]})
        self.catalog['contracts'].append({
            'id': 'foreign', 'contract': {'path': 'docs/contract.md', 'heading': 'Recovery'},
            'affected_paths': ['python/disco/foreign/**'],
            'rules': [{'language': 'python', 'file': 'python/disco/foreign/' + leaf, 'allow': allow}
                      for leaf, allow in [('__init__.py', []), ('model.py', ['disco.backup.snapshot']),
                                          ('consumer.py', ['disco.foreign.model'])]],
            'tests': {'python': ['python/tests/test_central.py'], 'javascript': []}})
        self.assertIn('reflective Python public callable access', self.check(False)['error'])

    def test_named_getattr_keeps_mutation_default_and_legacy_reflection_rejected(self):
        path = self.thread_local_fixture()
        original = (self.root / path).read_text()
        self.contract['rules'][1]['allow'].append('disco.recovery')
        for operation in ('setattr(_LOCAL_STATE, "locked", True)', 'delattr(_LOCAL_STATE, "locked")',
                          'vars(_LOCAL_STATE)', 'getattr(object(), "locked", _LOCAL_STATE)',
                          'getattr(callback, "__name__")'):
            with self.subTest(operation=operation):
                self.write(path, original + '\nfrom disco.recovery import callback\n' + operation + '\n')
                self.assertIn('reflective Python public callable access', self.check(False)['error'])

    def add_reviewed_use(self, path, category, select):
        import ast
        import hashlib
        previous = sys.path[:]
        try:
            sys.path.insert(0, str(ROOT / 'tools'))
            from architecture_guard import PythonModulePolicy as policy_class
        finally:
            sys.path[:] = previous
        policy = policy_class(self.root.resolve(), self.catalog)
        node = next(n for n in ast.walk(policy.trees[path]) if select(n))
        context = policy.use_context(path, node, category)
        self.assertIsNotNone(context)
        record = {'file': path, 'file_sha256': hashlib.sha256((self.root / path).read_bytes()).hexdigest(),
                  'reason': 'Owned inert regression for one explicitly reviewed existing source use.',
                  'sites': [{'selector': policy.use_selectors[id(node)][1],
                             'ast_sha256': hashlib.sha256(ast.dump(node, annotate_fields=True, include_attributes=False).encode()).hexdigest(),
                             'category': category, **context}]}
        self.catalog['python_module_policy'].setdefault('reviewed_use_sites', []).append(record)
        return record

    def reviewed_constructor_fixture(self):
        import ast
        path = 'python/disco/backup/tests/test_snapshot.py'
        self.write(path, 'from disco.backup.snapshot import Snapshot\nvalue = Snapshot.__new__(Snapshot)\n')
        return path, self.add_reviewed_use(path, 'test-constructor-capture',
                                         lambda n: isinstance(n, ast.Attribute) and n.attr == '__new__')

    def test_reviewed_use_admits_exact_site_but_not_copied_or_private_use(self):
        import hashlib
        path, record = self.reviewed_constructor_fixture()
        self.check()
        self.write('python/tests/test_central.py', (self.root / path).read_text())
        self.assertIn('reflective Python named value attribute', self.check(False)['error'])
        self.write('python/tests/test_central.py', '')
        self.write(path, (self.root / path).read_text() + 'from disco.backup.private import secret\n')
        record['file_sha256'] = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
        self.assertIn('forbidden private Python dependency', self.check(False)['error'])

    def test_reviewed_use_binds_source_ast_target_origin_and_owner_bytes(self):
        import copy
        import hashlib
        path, record = self.reviewed_constructor_fixture()
        original = copy.deepcopy(record)
        source = (self.root / path).read_text()
        self.write(path, source + '# changed source\n')
        self.assertIn('Reviewed Python use source changed', self.check(False)['error'])
        self.write(path, source.replace('__new__', '__init__'))
        record['file_sha256'] = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
        self.assertIn('Changed category, provenance or target', self.check(False)['error'])
        self.write(path, source)
        for field, replacement in (('targets', ['disco.backup.clock.tick']), ('origins', [['named', 'disco.backup.clock', 'Snapshot']]),
                                   ('owners', []), ('ast_sha256', '0' * 64)):
            with self.subTest(field=field):
                record.clear(); record.update(copy.deepcopy(original))
                record['sites'][0][field] = replacement
                self.assertIn('Changed category, provenance or target', self.check(False)['error'])
        record.clear(); record.update(copy.deepcopy(original))
        owner = self.root / 'python/disco/backup/snapshot.py'
        owner.write_text(owner.read_text() + '# changed owner bytes\n')
        self.assertIn('Changed category, provenance or target', self.check(False)['error'])

    def test_reviewed_use_rejects_alias_provenance_rebinding(self):
        import hashlib
        path, record = self.reviewed_constructor_fixture()
        self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\nclass Clock: pass\n')
        self.module['public_entries'][1]['exports'].append('Clock')
        self.write(path, 'from disco.backup.clock import Clock as Snapshot\nvalue = Snapshot.__new__(Snapshot)\n')
        record['file_sha256'] = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
        self.assertIn('Changed category, provenance or target', self.check(False)['error'])

    def test_reviewed_use_rejects_duplicate_missing_category_and_production_test_record(self):
        import copy
        import hashlib
        path, record = self.reviewed_constructor_fixture()
        records = self.catalog['python_module_policy']['reviewed_use_sites']
        records.append(copy.deepcopy(record))
        self.assertIn('duplicate reviewed Python use file', self.check(False)['error'])
        records.pop()
        site = copy.deepcopy(record['sites'][0])
        record['sites'].append(copy.deepcopy(site))
        self.assertIn('duplicate reviewed Python use site', self.check(False)['error'])
        record['sites'].pop()
        record['sites'][0]['selector'] = 'Attribute:9999'
        self.assertIn('Missing or duplicate reviewed Python use site', self.check(False)['error'])
        record['sites'][0] = copy.deepcopy(site)
        record['sites'][0]['category'] = 'production-method-capture'
        self.assertIn('Changed category, provenance or target', self.check(False)['error'])
        record['sites'][0] = copy.deepcopy(site)
        self.write('python/consumer.py', (self.root / path).read_text())
        record['file'] = 'python/consumer.py'
        record['file_sha256'] = hashlib.sha256((self.root / 'python/consumer.py').read_bytes()).hexdigest()
        self.assertIn('Changed category, provenance or target', self.check(False)['error'])

    def test_reviewed_use_rejects_unused_record_and_keeps_legacy_reflection_denied(self):
        import ast
        path = 'python/disco/backup/tests/test_snapshot.py'
        self.write(path, 'from disco.backup.snapshot import Snapshot\nvalue = Snapshot.empty()\n')
        self.add_reviewed_use(path, 'test-oracle-call', lambda n: isinstance(n, ast.Attribute))
        self.assertIn('Unused reviewed Python use site', self.check(False)['error'])
        self.catalog['python_module_policy']['reviewed_use_sites'] = []
        self.write(path, 'from disco.recovery import callback\nvalue = callback.__name__\n')
        self.assertIn('reflective Python public callable attribute', self.check(False)['error'])

    def test_reviewed_use_binds_finite_computed_mock_targets(self):
        import ast
        path = 'python/disco/backup/tests/test_snapshot.py'
        self.write(path, 'from unittest.mock import patch\nfor name in ("save", "_existing"):\n'
                   ' with patch("disco.backup.snapshot." + name): pass\n')
        record = self.add_reviewed_use(path, 'test-computed-mock-target',
                                      lambda n: isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'patch')
        self.assertEqual(record['sites'][0]['targets'], ['disco.backup.snapshot._existing', 'disco.backup.snapshot.save'])
        self.check()
        record['sites'][0]['targets'] = ['disco.backup.snapshot.secret']
        self.assertIn('Changed category, provenance or target', self.check(False)['error'])

    def test_named_import_forms_classes_constants_and_leaf_identity(self):
        sources = [
            'import disco.backup.snapshot as snapshot\nanswer = snapshot.save(snapshot.LIMIT)',
            'from disco.backup import snapshot as snapshot\nanswer = snapshot._existing(1)',
            'from disco.backup.snapshot import Snapshot, LIMIT\nanswer = Snapshot.empty() + LIMIT',
            'import disco.backup.snapshot\nanswer = disco.backup.snapshot.save(1)',
            'from disco.backup.snapshot import pathlib\nanswer = pathlib.Path("owned")',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.write('python/consumer.py', source); self.check()
        # Import execution only in this inert fixture: prove no facade/module copy.
        self.write('python/disco/backup/tests/test_snapshot.py',
                   'import unittest\nimport disco.backup.snapshot as direct\n'
                   'from disco.backup import snapshot as parent\n'
                   'class Identity(unittest.TestCase):\n def test_identity(self): self.assertIs(direct.save, parent.save)\n')
        result = self.cli('test', '--all', '--language', 'python')
        self.assertEqual(result['status'], 'passed')

    def test_entry_specific_exports_and_default_private_edges(self):
        for source in (
            'from disco.backup.clock import save',
            'import disco.backup.clock as clock\nclock.save(1)',
            'from disco.backup import private',
            'import disco.backup.private as private',
            'from disco.backup.snapshot import *',
            'from disco.backup import *',
            'import disco.backup as backup\nbackup.private.secret()',
            'from disco.backup.snapshot import Snapshot\nSnapshot.__dict__',
            'from disco.backup.snapshot import save\nsave.__globals__',
            'import disco.backup.snapshot as s\nforward(s)',
            'import disco.backup.snapshot as s\ngetattr(s,"save")',
        ):
            with self.subTest(source=source): self.fault(source)

    def test_v4_rejects_new_shape_and_v5_does_not_loosen_legacy_entry(self):
        self.catalog['version'] = 4
        self.assertIn('catalog fields', self.check(False, 'metadata')['error'])
        self.catalog['version'] = 5
        for source in ('from disco import recovery', 'import disco.recovery',
                       'from disco.recovery import implementation',
                       'from disco.recovery import callback\ncallback.__globals__',
                       'import disco.recovery as r\nforward(r)'):
            with self.subTest(source=source): self.fault(source)
        self.write('python/consumer.py', 'from disco.recovery import callback\ncallback(1)')
        self.check()

    def test_namespace_initializers_and_exact_entry_declarations(self):
        for path in ('python/disco/__init__.py', 'python/disco/backup/__init__.py'):
            original = (self.root / path).read_text()
            for source in ('import flask', 'VALUE = 1', 'from . import snapshot'):
                self.write(path, source)
                self.assertIn('inert initializer', self.check(False, 'metadata')['error'])
            self.write(path, original)
        entry = self.module['public_entries'][0]
        for key, value in [('module', 'disco.backup.wrong'), ('path', 'python/disco/backup/__init__.py'),
                           ('exports', ['save', 'save']), ('exports', ['*']), ('exports', ['__dict__'])]:
            original = entry[key]; entry[key] = value
            self.check(False, 'metadata'); entry[key] = original
        self.module['public_entries'].append(dict(entry)); self.check(False, 'metadata')
        self.module['public_entries'].pop()
        self.write('python/disco/backup/snapshot.py', 'save: object')
        self.assertIn('Missing Python named export', self.check(False)['error'])

    def test_named_shims_private_exports_and_dynamic_loaders_fail(self):
        self.write('python/helper.py', 'from disco.backup.snapshot import save\n')
        for source in ('from helper import save', 'import helper\nhelper.save(1)',
                       'from importlib import import_module\nimport_module("disco.backup.snapshot")',
                       '__import__("disco.backup", fromlist=["snapshot"])',
                       'from importlib import import_module as load\nload(".snapshot", "disco.backup")'):
            with self.subTest(source=source): self.fault(source)
        self.write('python/consumer.py', '')
        self.write('python/disco/backup/snapshot.py',
                   (self.root / 'python/disco/backup/snapshot.py').read_text() + '\nfrom . import private as hidden\n')
        self.contract['rules'][1]['allow'].append('disco.backup')
        self.module['public_entries'][0]['exports'].append('hidden')
        self.assertIn('exposes private module', self.check(False)['error'])

    def test_same_owner_private_use_and_classified_test_fixture_imports(self):
        path = 'python/disco/backup/snapshot.py'
        self.write(path, (self.root / path).read_text() + '\nfrom .private import secret\ndef use_private(): return secret()\n')
        self.contract['rules'][1]['allow'].append('disco.backup.private')
        self.check()
        self.module['public_entries'][0]['exports'].append('secret')
        self.assertIn('exposes private module', self.check(False)['error'])
        self.module['public_entries'][0]['exports'].remove('secret')
        self.write('python/disco/backup/tests/helper.py', 'VALUE = 71\n')
        self.write('python/tests/test_central.py', 'from disco.backup.tests.helper import VALUE\n')
        self.check()
        self.write('python/consumer.py', 'from disco.backup.tests.helper import VALUE\n')
        self.assertIn('production cannot import', self.check(False)['error'])

    def test_private_constant_and_alias_cannot_be_declared_public_indirectly(self):
        self.write('python/disco/backup/private.py', 'VALUE = 91\n')
        original = (self.root / 'python/disco/backup/snapshot.py').read_text()
        self.contract['rules'][1]['allow'].append('disco.backup.private')
        self.module['public_entries'][0]['exports'].append('leak')
        for source in ('from .private import VALUE as leak',
                       'from .private import VALUE\nleak = VALUE',
                       'from . import private\nleak = private.VALUE'):
            self.write('python/disco/backup/snapshot.py', original + '\n' + source + '\n')
            if source.startswith('from . import'): self.contract['rules'][1]['allow'].append('disco.backup')
            self.assertIn('exposes private module', self.check(False)['error'])

    def test_named_mode_cannot_expand_private_test_exception(self):
        test = 'python/disco/backup/tests/test_snapshot.py'
        self.write(test, 'from disco.backup.private import secret\n')
        self.assertIn('private Python', self.check(False)['error'])
        self.module['private_test_edges'] = [{'from': test, 'to': 'python/disco/backup/private.py'}]
        self.check()
        self.write(test, 'from disco.backup.snapshot import save\n')
        self.assertIn('Unused Python private test', self.check(False)['error'])

    def test_new_consumer_maps_both_owners_and_runs_local_public_tests(self):
        self.cli('check', '--language', 'metadata')
        self.git('add', '-A'); self.git('commit', '-qm', 'named baseline')
        base = self.git('rev-parse', 'HEAD')
        self.write('python/new_consumer.py', 'from disco.backup.snapshot import save\n')
        self.git('add', '-A'); self.git('commit', '-qm', 'new named consumer')
        result = self.cli('plan', '--base', base)
        self.assertIn('backup', result['affected_contracts'])
        self.assertIn('recovery', result['affected_contracts'])
        self.assertIn('python/disco/backup/tests/test_snapshot.py', result['tests']['python'])
        self.assertIn('python/new_consumer.py', result['source_sha256'])
        self.assertEqual(self.cli('test', '--base', base, '--language', 'python')['status'], 'passed')

    def test_named_test_patches_preserve_module_and_declared_values(self):
        sources = [
            'from unittest.mock import patch\nimport disco.backup.snapshot as s\nwith patch.object(s,"LIMIT",9): pass',
            'from unittest.mock import patch as p\nfrom disco.backup import snapshot as s\nwith p.object(s,"_existing",return_value=9): pass',
            'import unittest.mock as mock\nimport disco.backup.snapshot as s\nwith mock.patch.object(s.pathlib.Path,"home"): pass',
            'from unittest.mock import patch\nwith patch("disco.backup.snapshot.LIMIT",9): pass',
            'from unittest.mock import patch\nwith patch("disco.backup.snapshot.pathlib.Path.home"): pass',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.write('python/tests/test_central.py', source); self.check()
        self.write('python/disco/backup/tests/test_snapshot.py',
                   'import unittest\nfrom unittest.mock import patch\nimport disco.backup.snapshot as snapshot\n'
                   'class Identity(unittest.TestCase):\n def test_patch(self):\n'
                   '  with patch.object(snapshot,"_existing",return_value=91): self.assertEqual(snapshot._existing(0),91)\n'
                   '  self.assertEqual(snapshot._existing(0),0)\n')
        self.write('python/tests/test_central.py', '')
        self.assertEqual(self.cli('test', '--all', '--language', 'python')['status'], 'passed')

    def test_named_module_patch_exception_is_not_general_reflection(self):
        prefix = 'from unittest.mock import patch\nimport disco.backup.snapshot as s\n'
        for tail in ('patch.object(s,"unknown",9)', 'patch.object(s,name,9)',
                     'patch.object(s,"__dict__",{})', 'patch = object()\npatch.object(s,"LIMIT",9)',
                     'def use(patch):\n patch.object(s,"LIMIT",9)',
                     'def fake(*args): pass\nfake(s,"LIMIT",9)',
                     'forward(s)', 'getattr(s,"LIMIT")', 'vars(s)',
                     'patch("disco.backup.private.secret",9)',
                     'patch("disco.backup.snapshot.unknown",9)',
                     'patch("disco.backup.snapshot.Snapshot.__dict__",{})',
                     'patch(target,9)'):
            with self.subTest(tail=tail):
                self.write('python/tests/test_central.py', prefix + tail); self.check(False)
        self.write('python/tests/test_central.py', '')
        for source in (prefix + 'patch.object(s,"LIMIT",9)',
                       prefix + 'patch("disco.backup.snapshot.LIMIT",9)'):
            with self.subTest(production=source): self.fault(source)

    def test_string_patch_checks_every_owned_module_attribute(self):
        path = 'python/disco/backup/snapshot.py'
        self.write(path, (self.root / path).read_text() + '\nfrom . import clock\n')
        self.module['public_entries'][0]['exports'].append('clock')
        self.contract['rules'][1]['allow'].append('disco.backup')
        self.write('python/disco/backup/clock.py', 'LIMIT = 8\ndef tick(): return 1\nhidden = 12\n')
        for target in ('clock.LIMIT', 'Snapshot.empty', 'pathlib.Path.home'):
            self.write('python/tests/test_central.py',
                       f'from unittest.mock import patch\npatch("disco.backup.snapshot.{target}", 9)\n')
            self.check()
        self.write('python/tests/test_central.py',
                   'from unittest.mock import patch\npatch("disco.backup.snapshot.clock.hidden", 9)\n')
        self.check(False)

    def test_mock_attribute_mutations_cannot_spoof_patch_identity(self):
        prefix = ('from unittest.mock import patch\nimport unittest.mock as mock\n'
                  'import disco.backup.snapshot as s\ndef fake(*args): pass\n')
        for mutation in ('patch.object = fake', 'mock.patch = fake',
                         'del patch.object', 'del mock.patch',
                         'setattr(patch, "object", fake)', 'delattr(mock, "patch")',
                         'from builtins import setattr as change\nchange(mock, "patch", fake)',
                         'change = setattr\nchange(mock, "patch", fake)',
                         'alias = patch\nalias.object = fake',
                         'mock.__dict__["patch"] = fake',
                         'del patch.__dict__["object"]'):
            with self.subTest(mutation=mutation):
                self.write('python/tests/test_central.py', prefix + mutation + '\npatch.object(s,"LIMIT",9)\n')
                self.check(False)

    def test_finite_witness_iteration_reads_exact_leaf_files(self):
        prefix = 'from pathlib import Path\nimport disco.backup.snapshot as snapshot\nimport disco.backup.clock as clock\n'
        for source in (
            prefix + 'witness = [Path(module.__file__) for module in (snapshot,clock)]',
            prefix + 'witness = tuple(Path(module.__file__) for module in [snapshot,clock])',
            prefix + 'for module in (snapshot,clock):\n witness = Path(module.__file__)',
            prefix + 'witness = Path(snapshot.__file__)',
        ):
            with self.subTest(source=source):
                self.write('python/consumer.py', source); self.check()
        self.write('python/disco/backup/tests/test_snapshot.py',
                   'import unittest\nfrom pathlib import Path\nimport disco.backup.snapshot as snapshot\n'
                   'class Leaf(unittest.TestCase):\n def test_file(self): self.assertEqual(Path(snapshot.__file__).name,"snapshot.py")\n')
        self.assertEqual(self.cli('test', '--all', '--language', 'python')['status'], 'passed')

    def test_witness_iteration_does_not_expose_private_or_opaque_modules(self):
        prefix = 'import disco.backup.snapshot as snapshot\n'
        for tail in (
            'files = [module.__dict__ for module in (snapshot,)]',
            'files = [module.unknown for module in (snapshot,)]',
            'files = [forward(module) for module in (snapshot,)]',
            'modules = (snapshot,)\nfiles = [m.__file__ for m in modules]',
            'modules = [snapshot]\nmodules.append(other)',
            'snapshot.__file__ = "wrong.py"',
            'for module in (snapshot,):\n module = other\n path = module.__file__',
            'for module in (snapshot,):\n def leak(): return module',
            'files = [getattr(module,"LIMIT") for module in (snapshot,)]',
        ):
            with self.subTest(tail=tail): self.fault(prefix + tail)

    def test_named_value_reflection_and_private_loader_remain_rejected(self):
        for source in (
            'from disco.backup.snapshot import save\ngetattr(save,"__globals__")',
            'from disco.backup.snapshot import Snapshot\nSnapshot.empty.__globals__',
            'from disco.backup.snapshot import Snapshot\nvars(Snapshot)',
            'from importlib import import_module as load\nload("disco.backup.snapshot")',
            'import disco.backup.snapshot as s\ns.__dict__["private"]',
        ):
            with self.subTest(source=source): self.fault(source)


if __name__ == '__main__': unittest.main()
