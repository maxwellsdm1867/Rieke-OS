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
from desktop_build_runtime import patch_parser, exclude_optional_features, OPTIONAL_PID_ATTACH, copy_matlab_application, MATLAB_EXPORT_HELPERS, refresh_native_license_inventory
from desktop_runtime_manifest import inventory


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

    def test_matlab_export_and_gui_source_closure_excludes_recordings_and_examples(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, output = Path(temporary) / 'source', Path(temporary) / 'application'
            names = ['epicTreeGUI.m', 'src/loadEpicTreeData.m', 'src/buildTreeFromEpicData.m',
                     'src/tree/epicTreeTools.m', 'src/gui/widget.m']
            names.extend('src/tree/' + name + '.m' for name in MATLAB_EXPORT_HELPERS)
            for name in names + ['src/private-recording.h5', 'examples/sample.m', 'tests/test_gui.m']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            copy_matlab_application(root, output)
            for name in names:
                self.assertEqual((output / name).read_text(), name)
            self.assertFalse((output / 'src/private-recording.h5').exists())
            self.assertFalse((output / 'examples').exists())
            self.assertFalse((output / 'tests').exists())
            (root / 'src/tree/launchWorkspaceTree.m').unlink()
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                copy_matlab_application(root, output)

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
