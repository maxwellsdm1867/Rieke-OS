"""Local discovery index has no dependency on an application or project root."""
import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from workspace_projects import create_project, create_project_at, list_managed_projects
from workspace_startup_registry import project_index_path, read_project_index, remember_project_path, remember_project_paths_order, remember_project_result


class LocalProjectIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.index = self.base / 'profile/preferences/project-index.json'
        environment = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(self.index)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_empty_inventory_does_not_create_user_or_preferred_folders(self):
        preferred = self.base / 'preferred'
        self.assertEqual(read_project_index()['projects'], [])
        self.assertEqual(list_managed_projects(preferred)['projects'], [])
        self.assertFalse(self.index.parent.exists())
        self.assertFalse(preferred.exists())

    def test_created_registration_and_last_open_are_separate_without_parent_writes(self):
        first = create_project_at(str(self.base / 'research/one'), 'Independent study')
        second = create_project_at(str(self.base / 'research/two'), 'Independent study')
        remember_project_path(first['path'], first['uuid'], set_last=True)
        registered = remember_project_path(second['path'], second['uuid'])
        self.assertEqual(registered['last_project_path'], first['path'])
        self.assertEqual(len(registered['projects']), 2)
        self.assertEqual(set(path.name for path in (self.base / 'research').iterdir()), {'one', 'two'})
        self.assertNotIn('credentials', self.index.read_text())

    def test_existing_exact_folder_does_not_require_listing_or_writing_its_parent(self):
        parent = self.base / 'external-parent'
        selected = parent / 'selected-project'
        selected.mkdir(parents=True)
        original = Path.iterdir
        def prohibit_parent_inventory(path):
            if path == parent:
                raise PermissionError('The project parent is not an application workspace')
            return original(path)
        with patch.object(Path, 'iterdir', prohibit_parent_inventory):
            project = create_project_at(str(selected), 'Selected folder')
        self.assertEqual(project['path'], str(selected))
        self.assertEqual(set(path.name for path in parent.iterdir()), {'selected-project'})
        self.assertTrue((selected / 'project.json').is_file())

    def test_atomic_concurrent_registration_preserves_both_project_references(self):
        projects = [create_project_at(str(self.base / f'research/{index}'), f'Study {index}') for index in range(2)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda project: remember_project_path(project['path']), projects))
        self.assertEqual({project['path'] for project in read_project_index()['projects']}, {project['path'] for project in projects})
        self.assertFalse(list(self.index.parent.glob('.project-index-*')))

    def test_managed_and_exact_creation_of_same_folder_share_one_lock(self):
        from workspace_storage import initialize_layout
        preferred = self.base / 'preferred'
        selected = preferred / 'study'
        first_entered, finish_first = threading.Event(), threading.Event()
        second_started, second_finished = threading.Event(), threading.Event()
        def paused_layout(*args):
            if not first_entered.is_set():
                first_entered.set()
                if not finish_first.wait(5):
                    raise RuntimeError('Test did not release project creation')
            return initialize_layout(*args)
        def exact_attempt():
            second_started.set()
            try:
                return create_project_at(str(selected), 'Exact study')
            finally:
                second_finished.set()
        with patch('workspace_storage.initialize_layout', side_effect=paused_layout), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(create_project, preferred, 'Managed study', directory='study')
            try:
                self.assertTrue(first_entered.wait(5))
                second = pool.submit(exact_attempt)
                self.assertTrue(second_started.wait(5))
                self.assertFalse(second_finished.wait(.15), 'Exact route bypassed the managed route target lock')
            finally:
                finish_first.set()
            created = first.result(5)
            with self.assertRaisesRegex(ValueError, 'already contains files'):
                second.result(5)
        self.assertEqual(json.loads((selected / 'project.json').read_text())['project_uuid'], created['uuid'])

    def test_invalid_index_or_duplicate_order_preserves_prior_file(self):
        project = create_project_at(str(self.base / 'research/one'), 'Study')
        remember_project_path(project['path'])
        before = self.index.read_bytes()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            remember_project_paths_order([project['path'], project['path']])
        self.assertEqual(self.index.read_bytes(), before)
        for changes in ({'version': 2}, {'version': True}, {'last_project_path': '/not-registered'},
                        {'project_order': ['../relative']}, {'projects': [{'path': '/somewhere', 'password': 'no'}]}):
            invalid = {**json.loads(before), **changes}
            self.index.write_text(json.dumps(invalid))
            with self.assertRaises((ValueError, TypeError)):
                remember_project_path(project['path'])
            self.assertEqual(json.loads(self.index.read_text()), invalid)

    def test_completed_operation_survives_corrupt_profile_without_overwriting_evidence(self):
        project = create_project_at(str(self.base / 'research/one'), 'Completed study')
        self.index.write_text('corrupt profile evidence')
        before_project = (Path(project['path']) / 'project.json').read_bytes()
        completed = {'project_uuid': project['uuid'], 'directory': project['path'], 'verified': True,
                     'url': 'http://127.0.0.1:8123/'}
        preserved = remember_project_result(project['path'], completed, set_last=True)
        self.assertEqual({key: preserved[key] for key in completed}, completed)
        self.assertIn(project['path'], preserved['registry_warning'])
        self.assertNotIn('registry_warning', completed)
        self.assertEqual(self.index.read_text(), 'corrupt profile evidence')
        self.assertEqual((Path(project['path']) / 'project.json').read_bytes(), before_project)

    def test_completed_operation_reports_profile_write_failure_and_success_stays_unchanged(self):
        project = create_project_at(str(self.base / 'research/one'), 'Completed study')
        completed = {'directory': project['path'], 'moved': True}
        with patch('workspace_startup_registry.remember_project_path', side_effect=OSError('Disk full')):
            preserved = remember_project_result(project['path'], completed, previous_directory=self.base / 'old')
        self.assertTrue(preserved['moved'])
        self.assertIn('Disk full', preserved['registry_warning'])
        self.assertIs(remember_project_result(project['path'], completed), completed)

    def test_index_and_project_leaf_symlinks_are_rejected_without_following(self):
        project = create_project_at(str(self.base / 'research/one'), 'Study')
        alias = self.base / 'alias'
        alias.symlink_to(project['path'], target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'regular project'):
            remember_project_path(alias)
        outside = self.base / 'outside-index'
        outside.write_text('keep this file')
        self.index.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            read_project_index()
        self.assertEqual(outside.read_text(), 'keep this file')

    def test_desktop_profile_and_system_alias_parent_resolve_consistently(self):
        desktop = self.base / 'desktop-user'
        with patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': '', 'RIEKE_DESKTOP_USER_STATE': str(desktop)}):
            self.assertEqual(project_index_path(), desktop / 'preferences/project-index.json')
        actual = self.base / 'actual-profile'
        actual.mkdir()
        alias = self.base / 'profile-alias'
        alias.symlink_to(actual, target_is_directory=True)
        with patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(alias / 'project-index.json')}):
            self.assertEqual(project_index_path(), actual / 'project-index.json')
            remember_project_paths_order([])
            self.assertTrue((actual / 'project-index.json').is_file())


if __name__ == '__main__':
    unittest.main()
