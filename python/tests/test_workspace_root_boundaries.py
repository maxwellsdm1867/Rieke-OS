"""Root rejection must happen before any workspace/project files are written."""
import tempfile
import unittest
from pathlib import Path

from workspace_installation import initialize_workspace, select_workspace, MANIFEST
from workspace_launcher import create_launcher
from workspace_projects import create_project, list_managed_projects


class RootBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.app = self.base / 'Application with spaces'
        self.app.mkdir()
        self.root = select_workspace(self.base / 'Research ü workspace', self.app)
        self.project = Path(create_project(self.root, 'Original study', code_root=self.app)['path'])

    def test_nested_project_storage_rejected_without_writes(self):
        preference = self.app / '.rieke-runtime/workspace-selection.json'
        original = preference.read_bytes()
        for candidate in (self.project, self.project / 'imports' / 'Accidental root'):
            before = set(self.project.rglob('*'))
            for action in (lambda: select_workspace(candidate, self.app),
                           lambda: initialize_workspace(candidate, self.app),
                           lambda: create_project(candidate, 'Nested study', code_root=self.app)):
                with self.assertRaisesRegex(ValueError, 'parent workspace'):
                    action()
                self.assertEqual(set(self.project.rglob('*')), before)
                self.assertEqual(preference.read_bytes(), original)

    def test_nested_workspace_and_symlink_alias_cannot_bypass_boundary(self):
        candidate = self.root / 'Nested root'
        with self.assertRaisesRegex(ValueError, 'existing workspace'):
            select_workspace(candidate, self.app)
        self.assertFalse(candidate.exists())
        alias = self.base / 'project alias'
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'parent workspace'):
            select_workspace(alias / 'imports' / 'Root', self.app)
        self.assertFalse((self.project / 'imports' / 'Root').exists())

    def test_http_rejected_selection_keeps_original_root_and_projects(self):
        app = create_launcher(self.root, self.app, application_dir=self.app)
        client = app.test_client()
        response = client.post('/api/workspace', headers={'X-Workspace-Request':'1'},
                               json={'directory':str(self.project / 'exports' / 'Wrong root')})
        self.assertEqual(response.status_code, 400, response.json)
        self.assertIn('parent workspace', response.json['error'])
        inventory = client.get('/api/projects').json
        self.assertEqual(inventory['managed_root'], str(self.root))
        self.assertEqual(len(inventory['projects']), 1)
        self.assertFalse((self.project / 'exports' / 'Wrong root').exists())

    def test_sibling_workspace_is_separate_and_existing_files_preserved(self):
        second = self.base / 'Second workspace'
        second.mkdir()
        note = second / 'notes.txt'
        note.write_text('Preserve this file')
        select_workspace(second, self.app)
        self.assertEqual(list_managed_projects(second)['projects'], [])
        self.assertEqual(len(list_managed_projects(self.root)['projects']), 1)
        self.assertEqual(note.read_text(), 'Preserve this file')
        self.assertTrue((second / MANIFEST).is_file())

    def test_explicit_project_folder_under_workspace_preserves_root_and_cannot_nest_in_project(self):
        from workspace_projects import create_project_at
        preference = self.app / '.rieke-runtime/workspace-selection.json'
        original = preference.read_bytes()
        chosen = self.root / 'Organization' / 'Exact study folder'
        created = create_project_at(str(chosen), 'Exact study', code_root=self.app)
        self.assertEqual(Path(created['path']), chosen)
        self.assertEqual(preference.read_bytes(), original)
        self.assertFalse((chosen.parent / MANIFEST).exists())
        rejected = chosen / 'imports' / 'Nested project'
        with self.assertRaisesRegex(ValueError, 'parent workspace'):
            create_project_at(str(rejected), 'Nested project', code_root=self.app)
        self.assertFalse(rejected.exists())

    def test_missing_saved_root_not_recreated_and_explicit_override_works(self):
        from workspace_bootstrap import runtime_paths
        moved = self.root.with_name('Moved workspace')
        self.root.rename(moved)
        with self.assertRaisesRegex(ValueError, 'Saved workspace is unavailable'):
            runtime_paths(self.app, environ={})
        self.assertFalse(self.root.exists())
        alternate = initialize_workspace(self.base / 'Alternate workspace', self.app)
        settings = runtime_paths(self.app, environ={'RECORDING_WORKSPACE_ROOT':str(alternate)})
        self.assertEqual(settings['managed_root'], str(alternate))
        self.assertFalse(self.root.exists())


if __name__ == '__main__':
    unittest.main()
