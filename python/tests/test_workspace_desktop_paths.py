import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workspace_desktop_paths import require_external_data_path
from workspace_projects import create_project, create_project_at
from workspace_export_folder import prepare_export_root


class DesktopPathTests(unittest.TestCase):
    def test_bundle_paths_and_redirected_parents_are_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch).resolve()
            bundle = home / 'Rieke OS.app'
            resources = bundle / 'Contents/Resources'
            runtime = resources / 'runtime'
            runtime.mkdir(parents=True)
            alias = home / 'redirect'; alias.symlink_to(resources, target_is_directory=True)
            with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1', 'RIEKE_DESKTOP_RUNTIME': str(runtime)}):
                for target in (resources / 'project', bundle / 'new-project', alias / 'project', bundle):
                    with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'outside the application bundle'):
                        create_project_at(str(target), 'Scientific project')
                with self.assertRaises(ValueError):
                    create_project(resources, 'Scientific project')
                with self.assertRaises(ValueError):
                    prepare_export_root(resources)
                with self.assertRaises(ValueError):
                    require_external_data_path(home)
                self.assertEqual(require_external_data_path(home / 'projects'), home / 'projects')
            self.assertEqual(sorted(str(path.relative_to(bundle)) for path in bundle.rglob('*')),
                             ['Contents', 'Contents/Resources', 'Contents/Resources/runtime'])

    def test_missing_desktop_runtime_ownership_blocks_writes(self):
        with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'ownership is unavailable'):
                require_external_data_path('/fixture')

    def test_source_mode_retains_external_source_path_behavior(self):
        with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '0', 'RIEKE_DESKTOP_RUNTIME': '/fixture/Rieke OS.app/Contents/Resources/runtime'}):
            self.assertEqual(require_external_data_path('/fixture'), Path('/fixture'))
