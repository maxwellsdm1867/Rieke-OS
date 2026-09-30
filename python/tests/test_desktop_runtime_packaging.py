"""Desktop resource fidelity and user-state contracts, using temporary fixtures."""
import configparser
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import workspace_bootstrap as boot

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from desktop_build_runtime import patch_parser, exclude_optional_features, OPTIONAL_PID_ATTACH, refresh_native_license_inventory, copy_application
from desktop_runtime_manifest import inventory
from desktop_application_profile import audit_application, load_profile, validate_source_closure, validate_release_source


class DesktopPackagingTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, dict(os.environ))
        environment.start()
        self.addCleanup(environment.stop)

    def test_parser_patch_preserves_algorithms_and_config_semantics(self):
        source = ROOT / '.rieke-runtime/retinanalysis/src/retinanalysis/config/settings.py'
        if not source.exists():
            self.skipTest('Pinned parser source not provisioned')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = boot.prepare_desktop_parser_config(root / 'state')
            staged = root / 'parser/src/retinanalysis/config'
            staged.mkdir(parents=True)
            (staged / 'settings.py').write_bytes(source.read_bytes())
            # The mutation must touch only settings.py and remove generated config.
            algorithms = root / 'parser/src/retinanalysis/utils/parse_data.py'
            algorithms.parent.mkdir()
            original = (source.parents[1] / 'utils/parse_data.py').read_bytes()
            algorithms.write_bytes(original)
            receipt = patch_parser(root / 'parser')
            self.assertNotEqual(receipt['original_sha256'], receipt['patched_sha256'])
            self.assertEqual(algorithms.read_bytes(), original)
            def load(path, name):
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
            # Execute settings in isolation to avoid eager public package/database imports.
            import types
            stub = types.ModuleType('retinanalysis')
            with patch.dict(sys.modules, {'retinanalysis': stub}), \
                    patch.dict(os.environ, {'RIEKE_PARSER_CONFIG': str(config)}), \
                    patch('importlib.resources.files', return_value=config.parent.parent):
                # Source uses packaged path. Redirect it to the same fixture config.
                source_copy = root / 'source_settings.py'
                source_copy.write_text(source.read_text().replace(
                    'config_path = ir.files(retinanalysis) / os.path.join("config", "config.ini")',
                    'config_path = ' + repr(str(config))))
                before = load(source_copy, 'source_settings')
                after = load(staged / 'settings.py', 'wheel_settings')
                self.assertEqual(before.mea_config, after.mea_config)
                for key in ('DATA_DIR', 'RAW_DIR', 'H5_DIR', 'META_DIR', 'TAGS_DIR', 'QUERY_DIR', 'USER'):
                    self.assertEqual(getattr(before, key), getattr(after, key))
                os.environ['RIEKE_PARSER_CONFIG'] = 'relative/config.ini'
                with self.assertRaisesRegex(ValueError, 'absolute'):
                    load(staged / 'settings.py', 'bad_settings')

    def test_parser_config_never_modifies_package_and_preserves_user_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / 'app/runtime'
            runtime.mkdir(parents=True)
            with patch.dict(os.environ, {'RIEKE_DESKTOP_RUNTIME': str(runtime)}):
                target = boot.prepare_desktop_parser_config(root / 'state')
                target.write_text('[DEFAULT]\nuser = scientist\n')
                boot.prepare_desktop_parser_config(root / 'state')
                self.assertIn('scientist', target.read_text())
                self.assertEqual(list(runtime.iterdir()), [])
                with self.assertRaisesRegex(ValueError, 'separate'):
                    boot.prepare_desktop_parser_config(runtime / 'state')

    def test_inventory_rejects_external_and_broken_links_and_hashes_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / 'runtime'
            runtime.mkdir()
            resource = runtime / 'bytes'
            resource.write_bytes(b'first')
            first = inventory(runtime)
            resource.write_bytes(b'after')
            self.assertNotEqual(first, inventory(runtime))
            link = runtime / 'link'
            link.symlink_to('../external')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                inventory(runtime)
            link.unlink()
            link.symlink_to('missing')
            with self.assertRaisesRegex(ValueError, 'broken'):
                inventory(runtime)

    def test_production_omits_only_optional_pid_debugger_helper_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper = root / OPTIONAL_PID_ATTACH
            helper.parent.mkdir(parents=True)
            helper.write_bytes(b'pinned optional debugger helper')
            retained = helper.parent / 'attach_pydevd.py'
            retained.write_bytes(b'normal pinned debugger logic')
            inventory_path = root / 'dependency-inventory.json'
            inventory_path.write_text('{"python_distributions": [{"name":"debugpy","version":"1.8.22"}]}')
            features = exclude_optional_features(root)
            self.assertFalse(helper.exists())
            self.assertEqual(retained.read_bytes(), b'normal pinned debugger logic')
            self.assertEqual(features[0]['path'], OPTIONAL_PID_ATTACH)
            self.assertEqual(len(features[0]['original_sha256']), 64)
            value = json.loads(inventory_path.read_text())
            self.assertEqual(value['python_distributions'][0]['version'], '1.8.22')
            self.assertEqual(value['excluded_optional_features'], features)

    def test_data_export_application_allowlist_excludes_gui_and_legacy_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, runtime = Path(temporary) / 'source', Path(temporary) / 'runtime'
            output = runtime / 'application'
            (root / 'python').mkdir(parents=True)
            profile = load_profile()
            for name in profile['python_modules']:
                (root / 'python' / name).write_text('# reviewed module\n')
            for name in ('export_mat.py', 'import_ugm.py', 'workspace_matlab_routes.py', 'unreviewed.py'):
                (root / 'python' / name).write_text('# excluded or unknown\n')
            for name in ('epicTreeGUI.m', 'install.m', 'src/gui/widget.m', 'examples/sample.m'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            for name in ('workspace-source.json', 'workspace-mysql-runtime.json'):
                (root / 'python' / name).write_text('{}')
            (root / 'rieke-release.json').write_text('{}')
            (root / 'workspace-app/dist').mkdir(parents=True)
            (root / 'workspace-app/package.json').write_text('{}')
            (root / 'workspace-app/dist/index.html').write_text('Rieke OS')
            # Refresh must also remove MATLAB resources left by an older build.
            (output / 'src/gui').mkdir(parents=True)
            (output / 'src/gui/old.m').write_text('old GUI resource')
            copy_application(root, runtime)
            scope = audit_application(output, profile)
            self.assertEqual(scope['python_modules'], len(profile['python_modules']))
            self.assertTrue((output / 'python/workspace_matlab.py').is_file())
            self.assertTrue((output / 'python/field_mapper.py').is_file())
            self.assertFalse((output / 'python/export_mat.py').exists())
            self.assertFalse((output / 'python/import_ugm.py').exists())
            self.assertFalse((output / 'python/unreviewed.py').exists())
            self.assertEqual(list(output.rglob('*.m')), [])
            self.assertTrue((root / 'epicTreeGUI.m').is_file())
            self.assertEqual((output / 'workspace-app/dist/index.html').read_text(), 'Rieke OS')
            unknown = output / 'python/unreviewed.py'
            unknown.write_text('# unexpected module')
            with self.assertRaisesRegex(ValueError, 'allowlist'):
                audit_application(output)
            unknown.unlink()
            # Numeric export may remain; interactive launchers must fail audit.
            (output / 'launch_epictree.m').write_text('interactive launcher')
            with self.assertRaisesRegex(ValueError, 'interactive resources'):
                audit_application(output)

    def test_allowlist_rejects_excluded_imports_missing_sources_and_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'python').mkdir()
            profile = {'python_modules': ['workspace_matlab.py'],
                       'source_exclusions': [{'pattern': 'python/export_mat.py'}]}
            source = root / 'python/workspace_matlab.py'
            source.write_text('from export_mat import export\n')
            with self.assertRaisesRegex(ValueError, 'import closure excludes export_mat'):
                validate_source_closure(root, profile)
            source.write_text('import scipy.io\n')
            validate_source_closure(root, profile)
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing or redirected'):
                validate_source_closure(root, profile)
            outside = root / 'outside.py'
            outside.write_text('import scipy.io\n')
            source.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'redirected'):
                validate_source_closure(root, profile)

    def test_release_source_rejects_gui_companions_and_legacy_cli_tests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'desktop').mkdir()
            (root / 'desktop/application-profile.json').write_text(json.dumps(load_profile()))
            safe = ['desktop/application-profile.json', 'python/workspace_matlab.py',
                    'python/field_mapper.py', 'python/tests/test_workspace_export_boundaries.py',
                    'python/tests/test_workspace_matlab.py', 'workspace-app/src/App.jsx',
                    'tools/desktop_build_runtime.py']
            self.assertEqual(validate_release_source(root, safe)['tracked_paths_checked'], len(safe))
            for path in ('src/loadEpicTreeData.m', 'src/tree/README.md', 'src/README_DISPLAY_SPLITTER.md',
                         'tests/baselines/README.md', 'tests/baselines/numbers.mat',
                         'tests/test_gui.m', 'examples/data/sample.mat', 'python/tests/test_export.py',
                         'python/import_ugm.py', 'python/workspace_matlab_routes.py', 'other/reintroduced_gui.m'):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'excluded paths'):
                    validate_release_source(root, safe + [path])
            for path in ('../src/file.m', '/external.py', 'src\\\\file.m'):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Unsafe tracked'):
                    validate_release_source(root, safe + [path])
            with self.assertRaisesRegex(ValueError, 'profile is absent'):
                validate_release_source(root, safe[1:])

    def test_native_notice_sources_are_version_and_hash_pinned_with_shared_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, output = Path(temporary) / 'source', Path(temporary) / 'runtime'
            (root / 'desktop').mkdir(parents=True)
            output.mkdir()
            data = b'Pinned native license notice\n'
            source = {'package': 'mysql-server', 'applies_to': ['mysql-server', 'mysql-client', 'mysql-common'],
                      'version': '8.4.2', 'file': 'mysql-LICENSE.txt',
                      'url': 'https://raw.githubusercontent.com/mysql/mysql-server/mysql-8.4.2/LICENSE',
                      'sha256': hashlib.sha256(data).hexdigest()}
            (root / 'desktop/native-license-sources.json').write_text(json.dumps(
                {'format': 'rieke-native-license-sources', 'version': 1, 'sources': [source]}))
            (output / 'dependency-inventory.json').write_text(json.dumps(
                {'native_packages': [{'name': name, 'version': '8.4.2'} for name in source['applies_to']],
                 'native_license_files': []}))
            with patch('desktop_build_runtime.urlopen', return_value=io.BytesIO(data)):
                refresh_native_license_inventory(output, root)
            result = json.loads((output / 'dependency-inventory.json').read_text())
            self.assertEqual(set(result['native_license_coverage']), set(source['applies_to']))
            self.assertTrue(all(result['native_license_coverage'].values()))
            self.assertEqual((output / 'licenses/native/mysql-server/mysql-LICENSE.txt').read_bytes(), data)
            (root / 'desktop/build/license-cache/mysql-LICENSE.txt').write_bytes(b'corrupted cached notice')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                refresh_native_license_inventory(output, root)


if __name__ == '__main__':
    unittest.main()
