"""Packaging preflight rejects machine-bound resources without executing them."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('desktop_runtime_audit', Path(__file__).resolve().parents[2] / 'tools/desktop_runtime_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class RuntimeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'app'
        self.root.mkdir()
        self.write('python/workspace-source.json', {'commit': 'a' * 40, 'python': '3.11.13'})
        self.write('rieke-release.json', {'version': '0.1.0', 'repository': 'maxwellsdm1867/Rieke-OS'})
        self.write('workspace-app/package.json', {'version': '0.1.0'})
        self.write('.rieke-runtime/runtime.json', {'python': '.rieke-runtime/python/bin/python',
                   'retinanalysis': '.rieke-runtime/retinanalysis', 'retinanalysis_commit': 'a' * 40})
        self.file('.rieke-runtime/python/bin/python', 'raise RuntimeError("must not execute")')
        self.file('.rieke-runtime/retinanalysis/.git', 'source marker')

    def write(self, name, value):
        self.file(name, json.dumps(value))

    def file(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def inspect(self):
        with patch.object(audit.subprocess, 'check_output', return_value='a' * 40) as git:
            result = audit.audit_source_runtime(self.root)
        self.assertEqual(git.call_args.args[0][:1], ['git'])
        self.assertFalse(result['project_code_executed'])
        self.assertFalse(result['production_ready'])
        return result

    def test_known_safe_static_layout_never_claims_production_qualification(self):
        self.assertEqual(self.inspect()['status'], 'no_known_static_blockers')

    def test_external_python_and_editable_import_paths_are_blockers(self):
        external = Path(self.temp.name) / 'outside-python'
        external.write_text('not executed')
        python = self.root / '.rieke-runtime/python/bin/python'
        python.unlink()
        python.symlink_to(external)
        self.file('.rieke-runtime/python/lib/site-packages/parser.pth', '/build/user/parser/src\n')
        self.file('.rieke-runtime/python/pyvenv.cfg', 'home = /build/python/bin\n')
        codes = {item['code'] for item in self.inspect()['blockers']}
        self.assertTrue({'external_runtime_path', 'external_runtime_symlink', 'absolute_python_import_path', 'absolute_venv_home'} <= codes)

    def test_relative_internal_links_are_allowed_but_relative_import_escape_is_not(self):
        target = self.file('.rieke-runtime/python/bin/python-real', 'bundled')
        python = self.root / '.rieke-runtime/python/bin/python'
        python.unlink()
        python.symlink_to(target.name)
        self.assertEqual(self.inspect()['status'], 'no_known_static_blockers')
        self.file('.rieke-runtime/python/lib/site-packages/escape.pth', '../../../../../external\n')
        self.assertIn('external_python_import_path', {item['code'] for item in self.inspect()['blockers']})

    def test_source_pin_and_generated_parser_config_fail_independently(self):
        self.write('.rieke-runtime/runtime.json', {'python': '.rieke-runtime/python/bin/python',
                   'retinanalysis': '.rieke-runtime/retinanalysis', 'retinanalysis_commit': 'b' * 40})
        self.file('.rieke-runtime/retinanalysis/src/retinanalysis/config/config.ini', '[DEFAULT]\ndata=/build/data\n')
        codes = {item['code'] for item in self.inspect()['blockers']}
        self.assertTrue({'parser_receipt_mismatch', 'parser_config_build_paths'} <= codes)

    def test_missing_or_malformed_metadata_does_not_produce_a_pass(self):
        self.file('.rieke-runtime/runtime.json', '[]')
        (self.root / 'rieke-release.json').unlink()
        result = self.inspect()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('metadata_unavailable', {item['code'] for item in result['blockers']})

    def test_external_runtime_directory_is_not_traversed(self):
        import shutil
        runtime = self.root / '.rieke-runtime'
        shutil.rmtree(runtime)
        external = Path(self.temp.name) / 'outside-runtime'
        external.mkdir()
        (external / 'secret.pth').write_text('/external/private\n')
        runtime.symlink_to(external)
        with patch.object(audit.subprocess, 'check_output') as git:
            result = audit.audit_source_runtime(self.root)
        git.assert_not_called()
        self.assertEqual(result['examined']['pth_files'], 0)
        self.assertIn('unsafe_or_missing_runtime', {item['code'] for item in result['blockers']})


if __name__ == '__main__':
    unittest.main()
