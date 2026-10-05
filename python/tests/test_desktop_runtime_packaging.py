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
from desktop_application_profile import audit_application, load_profile, validate_source_closure, validate_release_source, copy_python_application, validate_profile


class DesktopPackagingTests(unittest.TestCase):
    def test_current_application_closure_includes_typed_requested_summary_backend(self):
        profile = load_profile()
        required = {'workspace_typed_index.py', 'workspace_typed_lifecycle.py',
                    'workspace_typed_query.py', 'workspace_explore_queries.py',
                    'workspace_cache_lifecycle.py', 'workspace_metadata_objects.py',
                    'workspace_disk_index.py', 'workspace_service.py', 'workspace_api.py',
                    'workspace_tree_pages.py'}
        self.assertTrue(required <= set(profile['python_modules']))
        # Audit every static/local and literal dynamic import in the full actual
        # application, rather than merely asserting these expected filenames.
        validate_source_closure(ROOT, profile)

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
                (root / 'python' / name).parent.mkdir(parents=True, exist_ok=True)
                # Existing parser boundaries remain source-bound even in a
                # synthetic staging tree; these bytes are scanned, never run.
                text = ((ROOT / 'python' / name).read_text() if name in
                        {'recording_workspace.py', 'workspace_bootstrap.py'} else '# reviewed module\n')
                (root / 'python' / name).write_text(text)
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
            (root / 'workspace-app/dist/index.html').write_text('Disco')
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
            self.assertEqual((output / 'workspace-app/dist/index.html').read_text(), 'Disco')
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
            profile = {'format': 'rieke-application-profile', 'version': 1, 'python_modules': ['workspace_matlab.py'],
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


class PythonPackageProfileTests(unittest.TestCase):
    """Tool-only synthetic source/staging; no scientific/parser imports or services."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source'
        self.application = Path(self.temporary.name) / 'stage'
        self.profile_path = self.root / 'desktop/application-profile.json'
        self.profile = {'format': 'rieke-application-profile', 'version': 2,
            'python_modules': ['disco/__init__.py', 'disco/recovery/__init__.py', 'disco/recovery/policy.py'],
            'source_exclusions': [], 'capabilities': {'mat_data_export': 'fixture'}}
        self.write('disco/__init__.py', '"""Fixture package."""\n')
        self.write('disco/recovery/__init__.py', 'from .policy import acknowledge\n__all__ = ("acknowledge",)\n')
        self.write('disco/recovery/policy.py', 'def acknowledge(value):\n    return {"saved": value}\n')
        self.save()

    def write(self, name, text):
        path = self.root / 'python' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def save(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(json.dumps(self.profile))

    def test_nested_copy_exact_audit_and_isolated_public_import(self):
        import subprocess
        self.write('unlisted.py', 'raise AssertionError("must not stage")')
        self.write('disco/recovery/tests/test_policy.py', 'raise AssertionError("must not stage")')
        copy_python_application(self.root, self.application, self.profile_path)
        self.assertEqual(audit_application(self.application, self.profile)['python_modules'], 3)
        self.assertEqual(sorted(p.relative_to(self.application / 'python').as_posix()
            for p in (self.application / 'python').rglob('*.py')), sorted(self.profile['python_modules']))
        # Only disposable fixture code is imported; -I ignores source PYTHONPATH.
        script = """import pathlib, sys
sys.path.insert(0, sys.argv[1])
import disco.recovery as public
assert pathlib.Path(public.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
assert public.acknowledge(True) == {'saved': True}
"""
        run = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(self.application / 'python')],
                             cwd=self.temporary.name, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        (self.application / 'python/extra.py').write_text('# extra')
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            audit_application(self.application)

    def test_v1_compatibility_and_v2_path_faults(self):
        valid = {'format': 'rieke-application-profile', 'version': 1, 'python_modules': ['flat.py']}
        self.assertEqual(validate_profile(valid), valid)
        faults = [('../escape.py', 'Unsafe'), ('/absolute.py', 'Unsafe'), ('C:drive.py', 'Unsafe'),
                  ('a\\b.py', 'Unsafe'), ('a//b.py', 'Unsafe'), ('a/./b.py', 'Unsafe'),
                  ('a/../b.py', 'Unsafe'), ('bad-name.py', 'identifier'), ('bad\x00.py', 'Unsafe'),
                  ('__init__.py', 'source root'), ('test_policy.py', 'Test source'), ('disco/tests/__init__.py', 'Test source'),
                  ('DISCO/__init__.py', 'Case-colliding'), ('disco.py', 'Ambiguous')]
        for name, message in faults:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                validate_profile({**self.profile, 'python_modules': self.profile['python_modules'] + [name]})
        for version in (True, 0, 3, '2'):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'Unrecognized'):
                validate_profile({**self.profile, 'version': version})
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            validate_profile({**self.profile, 'version': 1})
        for key, value in [('source_exclusions', [{'pattern': 'python/disco/*'}]),
                           ('source_excluded_paths', ['python/disco/recovery/policy.py']),
                           ('runtime_only_exclusions', [{'path': 'python/disco/recovery/policy.py'}])]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Excluded'):
                validate_profile({**self.profile, key: value})

    def test_direct_closure_validation_rejects_missing_parents_children_and_excluded_imports(self):
        with self.assertRaisesRegex(ValueError, 'initializer'):
            validate_source_closure(self.root, {**self.profile, 'python_modules': self.profile['python_modules'][1:]})
        self.write('disco/recovery/policy.py', 'from . import missing')
        with self.assertRaisesRegex(ValueError, 'Unresolved application package export'):
            validate_source_closure(self.root, self.profile)
        self.write('disco/recovery/hidden.py', 'VALUE = 1')
        for statement in ('from . import hidden', 'import disco.recovery.hidden',
                          'from disco.recovery.hidden import VALUE', 'from .hidden import VALUE'):
            self.write('disco/recovery/policy.py', statement)
            with self.subTest(statement=statement), self.assertRaisesRegex(ValueError, 'closure excludes'):
                validate_source_closure(self.root, self.profile)
        self.write('disco/recovery/policy.py', 'from ... import outside')
        with self.assertRaisesRegex(ValueError, 'escapes package'):
            validate_source_closure(self.root, self.profile)
        self.write('disco/recovery/policy.py', 'import retired')
        self.profile['source_exclusions'] = [{'pattern': 'python/retired.py'}]
        with self.assertRaisesRegex(ValueError, 'closure excludes retired'):
            validate_source_closure(self.root, self.profile)

    def test_package_locals_are_not_exports_and_v2_release_source_reader_remains_strict(self):
        self.write('disco/__init__.py', 'def outer():\n    value = 1\n')
        self.write('disco/recovery/policy.py', 'from disco import value\nacknowledge = None\n')
        with self.assertRaisesRegex(ValueError, 'Unresolved application package export disco.value'):
            validate_source_closure(self.root, self.profile)
        tracked = ['desktop/application-profile.json', *['python/' + n for n in self.profile['python_modules']]]
        self.assertEqual(validate_release_source(self.root, tracked)['version'], 2)
        self.profile['source_exclusions'] = [{'pattern': 'src/**'}]; self.save()
        with self.assertRaisesRegex(ValueError, 'excluded paths'):
            validate_release_source(self.root, tracked + ['src/legacy.m'])

    def test_comprehension_and_lambda_locals_do_not_become_package_exports(self):
        for initializer in ('ignored = [missing for missing in []]',
                            'ignored = {missing for missing in []}',
                            'ignored = {missing: 1 for missing in []}',
                            'ignored = (missing for missing in [])',
                            'ignored = lambda: (missing := 1)'):
            self.write('disco/recovery/__init__.py', initializer)
            self.write('disco/recovery/policy.py', 'from . import missing')
            with self.subTest(initializer=initializer), self.assertRaisesRegex(ValueError, 'Unresolved application package export'):
                validate_source_closure(self.root, self.profile)

    def test_initializer_missing_import_and_circular_reexport_cannot_justify_exports(self):
        for initializer in ('from . import missing', 'from . import missing as alias',
                            'from .policy import missing'):
            self.write('disco/recovery/__init__.py', initializer)
            self.write('disco/recovery/policy.py', 'from . import missing')
            with self.subTest(initializer=initializer), self.assertRaisesRegex(ValueError, 'Unresolved application package export'):
                validate_source_closure(self.root, self.profile)
        self.write('disco/recovery/__init__.py', 'from .policy import acknowledge')
        self.write('disco/recovery/policy.py', 'from . import acknowledge')
        with self.assertRaisesRegex(ValueError, 'Unresolved application package export'):
            validate_source_closure(self.root, self.profile)

    def test_source_and_destination_redirects_fail_before_copy(self):
        for side in ('source', 'destination'):
            with self.subTest(side=side):
                base = self.root / 'python' if side == 'source' else self.application / 'python'
                if side == 'destination': base.mkdir(parents=True)
                parent = base / 'disco'
                outside = Path(self.temporary.name) / (side + '-outside')
                if side == 'source': parent.rename(outside)
                else: outside.mkdir()
                parent.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'redirected'):
                    copy_python_application(self.root, self.application, self.profile_path)
                self.assertFalse((self.application / 'application-profile.json').exists())
                parent.unlink()
                if side == 'source': outside.rename(parent)
        target = self.application / 'application-profile.json'
        target.symlink_to(Path(self.temporary.name) / 'outside-profile')
        with self.assertRaisesRegex(ValueError, 'redirected'):
            copy_python_application(self.root, self.application, self.profile_path)

    def test_missing_or_ambiguous_source_and_audit_redirects(self):
        source = self.root / 'python/disco/recovery/policy.py'
        source.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or redirected'):
            validate_source_closure(self.root, self.profile)
        self.write('disco/recovery/policy.py', 'acknowledge = None')
        collision = self.write('disco.py', '# ambiguous')
        with self.assertRaisesRegex(ValueError, 'Ambiguous local'):
            validate_source_closure(self.root, self.profile)
        collision.unlink()
        copy_python_application(self.root, self.application, self.profile_path)
        staged = self.application / 'python/disco/recovery/policy.py'
        staged.unlink(); staged.symlink_to(source)
        with self.assertRaisesRegex(ValueError, 'redirected'):
            audit_application(self.application)

    def test_dynamic_literal_aliases_are_checked_and_unclassified_loaders_fail(self):
        self.write('disco/recovery/hidden.py', '# unlisted')
        for statement in ('import importlib as loader; loader.import_module("disco.recovery.hidden")',
                          'from importlib import import_module as load; load(".hidden", "disco.recovery")',
                          '__import__("disco.recovery.hidden")',
                          'import importlib; load = importlib.import_module; load("disco.recovery.hidden")',
                          '__import__("disco.recovery", fromlist=["hidden"])'):
            self.write('disco/recovery/policy.py', 'acknowledge = None\n' + statement)
            with self.subTest(statement=statement), self.assertRaisesRegex(ValueError, 'closure excludes'):
                validate_source_closure(self.root, self.profile)
        for statement in ('import importlib; importlib.import_module(name)',
                          'from importlib.util import spec_from_file_location as load; load(name, path)',
                          'exec(source)', 'import runpy; runpy.run_path(path)'):
            self.write('disco/recovery/policy.py', 'acknowledge = None\n' + statement)
            with self.subTest(statement=statement), self.assertRaisesRegex(ValueError, 'Unclassified'):
                validate_source_closure(self.root, self.profile)
        self.write('disco/recovery/policy.py', 'acknowledge = None\nimport importlib; importlib.import_module(".policy", package="disco.recovery")')
        self.assertEqual(validate_source_closure(self.root, self.profile)['external_loader_boundaries'], [])

    def test_deleting_or_renaming_all_bound_loader_sites_is_rejected(self):
        actual = load_profile()
        for name in actual['python_modules']:
            self.write(name, (ROOT / 'python' / name).read_text())
        for name in ('recording_workspace.py', 'workspace_bootstrap.py'):
            original = (ROOT / 'python' / name).read_text()
            for changed in ('# all loader sites removed\n', original.replace('PROBE =', 'RENAMED_PROBE =') if name == 'workspace_bootstrap.py' else '# parser loader removed\n'):
                self.write(name, changed)
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unclassified external application loader: ' + name):
                    validate_source_closure(self.root, actual)
            self.write(name, original)

    def test_existing_external_loader_boundaries_are_source_bound_not_executed(self):
        report = validate_source_closure(ROOT, load_profile())
        self.assertEqual([item['file'] for item in report['external_loader_boundaries']],
                         ['recording_workspace.py', 'workspace_bootstrap.py'])
        actual = load_profile()
        for name in actual['python_modules']:
            self.write(name, (ROOT / 'python' / name).read_text())
        boundary = self.root / 'python/recording_workspace.py'
        boundary.write_text(boundary.read_text() + '\n# changed boundary\n')
        with self.assertRaisesRegex(ValueError, 'Unclassified external application loader: recording_workspace.py'):
            validate_source_closure(self.root, actual)
        # A copied external loader spelling in an ordinary package is never approved.
        self.write('disco/recovery/policy.py', 'acknowledge = None\nimport importlib.util\nimportlib.util.spec_from_file_location("parser", path)')
        with self.assertRaisesRegex(ValueError, 'Unclassified external'):
            validate_source_closure(self.root, self.profile)


if __name__ == '__main__':
    unittest.main()
