"""Workspace launch contracts, without Docker or installing dependencies."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import workspace_bootstrap as boot
from workspace_installation import initialize_workspace, discover_workspace, read_workspace, MANIFEST, LAUNCHER


class WorkspaceInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / "app with 'quotes'"
        self.app.mkdir()
        self.workspace = self.base / 'Research workspace'

    def test_initialize_and_discover_from_project_subdirectory(self):
        initialize_workspace(self.workspace, self.app)
        child = self.workspace / 'project' / 'exports'
        child.mkdir(parents=True)
        self.assertEqual(discover_workspace(child), self.workspace)
        self.assertIsNone(discover_workspace(self.app))
        self.assertEqual(set(p.name for p in self.workspace.iterdir()), {MANIFEST, LAUNCHER, 'project'})

    def test_launcher_uses_own_location_from_unrelated_working_directory(self):
        (self.app / 'rieke.py').write_text('import sys, json; print(json.dumps(sys.argv[1:]))')
        initialize_workspace(self.workspace, self.app)
        result = subprocess.run([sys.executable, str(self.workspace / LAUNCHER), '--port', '8900'],
                                cwd=self.base, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), ['launch', '--workspace', str(self.workspace), '--port', '8900'])

    def test_managed_workspace_launcher_uses_stable_manager_across_release_changes(self):
        import os
        import workspace_updates as updates
        installation = self.base / 'installation'
        release = installation / 'releases/0.1.0'
        release.mkdir(parents=True)
        (installation / 'installation.json').write_text(json.dumps({'format': 'rieke-installation', 'version': 1, 'repository': updates.REPOSITORY}))
        (release / 'rieke-release.json').write_text(json.dumps({'format': 'rieke-application-release', 'version': '0.1.0', 'repository': updates.REPOSITORY, 'updater_protocol': 1}))
        (release / '.release-ready.json').write_text('{"version":"0.1.0"}')
        (installation / 'manager.py').write_text('import sys, json; print(json.dumps(sys.argv[1:]))')
        with patch.dict(os.environ, RIEKE_INSTALLATION_ROOT=str(installation)):
            initialize_workspace(self.workspace, release)
        import shutil
        shutil.rmtree(release)  # Workspace entry point has no dependency on this old version's path.
        result = subprocess.run([sys.executable, str(self.workspace / LAUNCHER), '--port', '8900'],
                                cwd=self.base, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), ['--installation', str(installation), 'launch', '--',
                                                  '--workspace', str(self.workspace), '--port', '8900'])

    def test_reject_overwrite_code_overlap_project_and_symlink(self):
        initialize_workspace(self.workspace, self.app)
        original = (self.workspace / LAUNCHER).read_bytes()
        with self.assertRaises(ValueError): initialize_workspace(self.workspace, self.app)
        self.assertEqual((self.workspace / LAUNCHER).read_bytes(), original)
        for folder in (self.app / 'data', self.base):
            with self.assertRaises(ValueError): initialize_workspace(folder, self.app)
        project = self.base / 'project'; project.mkdir(); (project / 'project.json').touch()
        with self.assertRaises(ValueError): initialize_workspace(project, self.app)
        link = self.base / 'link'; link.symlink_to(self.workspace)
        with self.assertRaises(ValueError): initialize_workspace(link, self.app)

    def test_invalid_manifest_fails_instead_of_selecting_default_storage(self):
        self.workspace.mkdir()
        (self.workspace / MANIFEST).write_text('{"format":"other", "version":1}')
        with self.assertRaises(ValueError): discover_workspace(self.workspace)
        (self.workspace / MANIFEST).unlink()
        (self.workspace / MANIFEST).symlink_to(self.base / 'missing')
        with self.assertRaises(ValueError): read_workspace(self.workspace)

    def test_cli_passes_explicit_workspace_and_port_without_changing_global_environment(self):
        initialize_workspace(self.workspace, self.app)
        with patch.object(boot, 'run') as run:
            self.assertEqual(boot.main(['launch', '--workspace', str(self.workspace), '--port', '8910']), 0)
        self.assertEqual(run.call_args.kwargs['env']['RECORDING_WORKSPACE_ROOT'], str(self.workspace))
        self.assertEqual(run.call_args.kwargs['env']['RIEKE_LAUNCHER_PORT'], '8910')
        with patch.object(boot, 'run') as run:
            self.assertEqual(boot.main(['launch', '--port', '0']), 1)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

class WorkspaceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.app=self.base/'application';self.app.mkdir()
        isolated_index=patch.dict(os.environ,{'RIEKE_PROJECT_INDEX':str(self.base/'user-state/project-index.json')})
        isolated_index.start();self.addCleanup(isolated_index.stop)
        self.root=self.base/'Research data'

    def test_select_initializes_preserves_files_and_reuses_existing_workspace(self):
        from workspace_installation import select_workspace
        self.root.mkdir();(self.root/'notes.txt').write_text('preserve')
        selected=select_workspace(self.root,self.app)
        before=(selected/LAUNCHER).read_bytes()
        self.assertEqual(select_workspace(self.root,self.app),selected)
        self.assertEqual((selected/LAUNCHER).read_bytes(),before)
        self.assertEqual((selected/'notes.txt').read_text(),'preserve')
        self.assertEqual(boot.runtime_paths(self.app,environ={})['managed_root'],str(selected))
        explicit=self.base/'explicit'
        self.assertEqual(boot.runtime_paths(self.app,environ={'RECORDING_WORKSPACE_ROOT':str(explicit)})['managed_root'],str(explicit))

    def test_managed_workspace_preference_survives_application_release_change(self):
        import os
        from workspace_installation import select_workspace
        installation=self.base/'managed-app';installation.mkdir()
        with patch.dict(os.environ,{'RIEKE_INSTALLATION_ROOT':str(installation)}):
            selected=select_workspace(self.root,self.app)
        saved=json.loads((installation/'preferences/workspace-selection.json').read_text())
        self.assertEqual(saved['managed_root'],str(selected))
        next_release=self.base/'new-release';next_release.mkdir()
        self.assertEqual(boot.runtime_paths(next_release,environ={'RIEKE_INSTALLATION_ROOT':str(installation)})['managed_root'],str(selected))

    def test_project_path_invalid_manifest_and_symlink_fail_without_preference(self):
        from workspace_installation import select_workspace
        self.root.mkdir();(self.root/'project.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'parent'):select_workspace(self.root,self.app)
        (self.root/'project.json').unlink();(self.root/MANIFEST).write_text('{invalid')
        with self.assertRaises(ValueError):select_workspace(self.root,self.app)
        self.assertFalse((self.app/'.rieke-runtime/workspace-selection.json').exists())
        link=self.base/'linked';link.symlink_to(self.root)
        with self.assertRaises(ValueError):select_workspace(link,self.app)
        with self.assertRaises(ValueError):select_workspace('relative',self.app)

    def test_launcher_selection_discovers_existing_projects_and_creation_uses_selected_root(self):
        from workspace_launcher import create_launcher
        from workspace_projects import create_project
        old=self.base/'old';new=self.base/'new'
        existing=create_project(new,'Existing study',code_root=self.app)
        manifests={name:(Path(existing['path'])/name).read_bytes() for name in ('project.json','catalog.json')}
        app=create_launcher(old,self.app,application_dir=self.app)
        client=app.test_client();headers={'X-Workspace-Request':'1'}
        response=client.post('/api/workspace',json={'directory':str(new)},headers=headers)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['projects'][0]['uuid'],existing['uuid'])
        self.assertEqual(client.get('/api/projects').json['managed_root'],str(new.resolve()))
        created=client.post('/api/projects',json={'name':'New study'},headers=headers)
        self.assertEqual(created.status_code,201,created.json)
        self.assertEqual(Path(created.json['project']['path']).parent,new.resolve())
        for name,data in manifests.items():self.assertEqual((Path(existing['path'])/name).read_bytes(),data)
        self.assertFalse(old.exists())
        self.assertEqual(client.post('/api/workspace',json={'directory':str(self.app)},headers=headers).status_code,400)
        self.assertEqual(client.get('/api/projects').json['managed_root'],str(new.resolve()))
