import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from workspace_projects import list_projects, MANIFEST_LIMIT


class ProjectDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        isolated_index = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(self.root / '.user-state/project-index.json')})
        isolated_index.start()
        self.addCleanup(isolated_index.stop)
        self.current = self.make_project('current', 'Current project')

    def make_project(self, folder, name, identity=None, display_name=None):
        path = self.root / folder
        path.mkdir(parents=True)
        identity = identity or str(uuid.uuid4())
        project = {'format': 'recording-project', 'version': 1, 'project_uuid': identity,
                   'name': name, 'catalog_ref': 'catalog.json'}
        if display_name is not None:
            project['display_name'] = display_name
        (path / 'project.json').write_text(json.dumps(project))
        (path / 'catalog.json').write_text(json.dumps({
            'format': 'recording-catalog-reference', 'version': 1, 'project_uuid': identity,
            'connection': {'password': 'must never leave registry'}, 'database': 'fixture'}))
        return path

    def test_stable_order_display_name_preferred_and_no_connection_contents_returned(self):
        other = self.make_project('other', 'Internal name', display_name='Spike Response Model')
        before = (self.current / 'project.json').stat().st_mtime_ns
        result = list_projects(self.current)
        self.assertEqual(result['projects'][0]['path'], str(self.current.resolve()))
        self.assertEqual(result['projects'][1]['name'], 'Spike Response Model')
        self.assertEqual(result['projects'][1]['path'], str(other.resolve()))
        self.assertTrue(result['projects'][0]['current'])
        self.assertFalse(result['projects'][1]['current'])
        self.assertTrue(all(row['available'] for row in result['projects']))
        self.assertEqual(result['current_project_uuid'], result['projects'][0]['uuid'])
        self.assertNotIn('password', json.dumps(result))
        self.assertNotIn('must never leave registry', json.dumps(result))
        self.assertEqual(before, (self.current / 'project.json').stat().st_mtime_ns)

    def test_native_copies_remain_selectable_by_folder(self):
        from workspace_projects import list_managed_projects
        identity=json.loads((self.current/'project.json').read_text())['project_uuid']
        other=self.make_project('copy','Current project',identity=identity)
        for path in (self.current,other):
            catalog=json.loads((path/'catalog.json').read_text())
            catalog['managed_database']={'kind':'native-mysql'}
            (path/'catalog.json').write_text(json.dumps(catalog))
        result=list_projects(self.current)
        self.assertEqual(len(result['projects']),2)
        self.assertEqual([p['current'] for p in result['projects']],[False,True])
        self.assertEqual(len(list_managed_projects(self.root)['projects']),2)

    def test_switching_current_project_never_promotes_it(self):
        from workspace_projects import list_managed_projects
        other = self.make_project('alpha', 'Alpha')
        third = self.make_project('zeta', 'Zeta')
        expected = [str(other.resolve()), str(self.current.resolve()), str(third.resolve())]
        for current in (self.current, other, third):
            result = list_projects(current)
            self.assertEqual([row['path'] for row in result['projects']], expected)
            self.assertEqual(next(row['path'] for row in result['projects'] if row['current']), str(current.resolve()))
            self.assertEqual([row['path'] for row in list_managed_projects(self.root, current)['projects']], expected)

    def test_drag_order_survives_switches_and_last_project_updates(self):
        from workspace_startup_registry import remember_project, remember_project_order
        other = self.make_project('alpha', 'Alpha')
        paths = [str(self.current.resolve()), str(other.resolve())]
        remember_project_order(self.root, paths)
        remember_project(self.root, json.loads((other / 'project.json').read_text())['project_uuid'])
        for current in (self.current, other):
            self.assertEqual([row['path'] for row in list_projects(current)['projects']], paths)
        third = self.make_project('new', 'A new project')
        self.assertEqual([row['path'] for row in list_projects(other)['projects']], paths + [str(third.resolve())])

    def test_order_route_accepts_only_a_complete_validated_folder_list(self):
        from flask import Flask, jsonify
        from workspace_launcher import register_project_routes
        app = Flask(__name__)
        app.register_error_handler(ValueError, lambda error: (jsonify(error=str(error)), 400))
        register_project_routes(app, retinanalysis_dir=self.root, project_dir=self.current)
        other = self.make_project('alpha', 'Alpha')
        client = app.test_client()
        paths = [str(self.current.resolve()), str(other.resolve())]
        result = client.post('/api/projects/order', json={'paths': paths})
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual([row['path'] for row in result.get_json()['projects']], paths)
        from workspace_startup_registry import project_index_path
        before = project_index_path().read_text()
        for invalid in [paths[:1], [paths[0], paths[0]], paths + ['/outside'], 'bad', [1], None]:
            self.assertEqual(client.post('/api/projects/order', json={'paths': invalid}).status_code, 400)
            self.assertEqual(project_index_path().read_text(), before)

    def test_only_valid_immediate_siblings_are_discovered(self):
        self.make_project('container/nested', 'Nested project')
        (self.root / 'empty').mkdir()
        mismatched = self.make_project('mismatch', 'Mismatched project')
        catalog = json.loads((mismatched / 'catalog.json').read_text())
        catalog['project_uuid'] = str(uuid.uuid4())
        (mismatched / 'catalog.json').write_text(json.dumps(catalog))
        malformed = self.make_project('bad', 'Malformed project')
        (malformed / 'project.json').write_text('{not json')
        unsupported = self.make_project('future', 'Future project')
        project = json.loads((unsupported / 'project.json').read_text())
        project['version'] = 99
        (unsupported / 'project.json').write_text(json.dumps(project))
        self.assertEqual(len(list_projects(self.current)['projects']), 1)

    def test_symlink_directories_and_manifest_links_do_not_escape_discovery(self):
        outside_temp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_temp.cleanup)
        outside = Path(outside_temp.name)
        (outside / 'project.json').write_text((self.current / 'project.json').read_text())
        (outside / 'catalog.json').write_text((self.current / 'catalog.json').read_text())
        (self.root / 'linked-directory').symlink_to(outside, target_is_directory=True)
        linked = self.make_project('linked-file', 'Linked manifest')
        (linked / 'catalog.json').unlink()
        (linked / 'catalog.json').symlink_to(outside / 'catalog.json')
        self.assertEqual(len(list_projects(self.current)['projects']), 1)

    def test_non_adjacent_catalog_reference_is_rejected(self):
        other = self.make_project('escape', 'Escaping reference')
        project = json.loads((other / 'project.json').read_text())
        project['catalog_ref'] = '../current/catalog.json'
        (other / 'project.json').write_text(json.dumps(project))
        self.assertEqual(len(list_projects(self.current)['projects']), 1)

    def test_current_stays_visible_when_its_catalog_becomes_unavailable(self):
        (self.current / 'catalog.json').unlink()
        result = list_projects(self.current)
        self.assertEqual(len(result['projects']), 1)
        self.assertFalse(result['projects'][0]['available'])
        self.assertTrue(result['projects'][0]['current'])
        self.assertIn('unavailable_reason', result['projects'][0])

    def test_ambiguous_duplicate_identities_are_not_selectable(self):
        current_uuid = json.loads((self.current / 'project.json').read_text())['project_uuid']
        self.make_project('copy-current', 'Copy of current', current_uuid)
        duplicate = str(uuid.uuid4())
        self.make_project('ambiguous-a', 'A', duplicate)
        self.make_project('ambiguous-b', 'B', duplicate)
        self.assertEqual(len(list_projects(self.current)['projects']), 1)

    def test_display_name_sort_is_deterministic_and_invalid_identity_fails_closed(self):
        self.make_project('z', 'Alpha')
        self.make_project('a', 'Beta')
        invalid = self.make_project('invalid-id', 'Bad identity', 'not-a-uuid')
        self.assertEqual([row['name'] for row in list_projects(self.current)['projects']],
                         ['Alpha', 'Beta', 'Current project'])
        with self.assertRaises(ValueError):
            list_projects(invalid)

    def test_boolean_versions_and_oversized_manifests_are_rejected(self):
        boolean = self.make_project('bool-version', 'Boolean version')
        project = json.loads((boolean / 'project.json').read_text())
        project['version'] = True
        (boolean / 'project.json').write_text(json.dumps(project))
        oversized = self.make_project('oversized', 'Oversized')
        (oversized / 'catalog.json').write_text(' ' * (MANIFEST_LIMIT + 1))
        self.assertEqual(len(list_projects(self.current)['projects']), 1)

    def test_remembered_external_root_survives_preferred_root_changes_without_scanning_neighbors(self):
        from workspace_projects import list_managed_projects
        from workspace_startup_registry import remember_project_path
        outside = self.make_project('outside/selected', 'External study')
        self.make_project('outside/not-selected', 'Unremembered neighbor')
        saved = remember_project_path(outside.resolve(), set_last=True)
        self.assertEqual(saved['last_project_path'], str(outside.resolve()))
        before = (outside / 'project.json').read_bytes()
        for preferred in [self.root / 'empty-preferred', self.root / 'another-preferred']:
            result = list_managed_projects(preferred)
            self.assertFalse(preferred.exists())
            self.assertEqual([project['path'] for project in result['projects']], [str(outside.resolve())])
            self.assertEqual(result['last_project_path'], str(outside.resolve()))
            self.assertEqual(result['last_project_uuid'], saved['projects'][0]['project_uuid'])
        result = list_projects(self.current)
        self.assertEqual({project['name'] for project in result['projects']}, {'Current project', 'External study'})
        self.assertEqual((outside / 'project.json').read_bytes(), before)
        self.assertNotIn('password', json.dumps(saved))
        self.assertFalse((outside.parent / '.rieke-os.json').exists())

    def test_missing_corrupt_or_repurposed_remembered_folder_remains_visible_unavailable(self):
        from workspace_projects import list_managed_projects
        from workspace_startup_registry import remember_project_path
        outside = self.make_project('outside/selected', 'External study')
        saved = remember_project_path(outside.resolve())['projects'][0]
        manifest = (outside / 'project.json').read_text()
        for content in ['not json', json.dumps({**json.loads(manifest), 'project_uuid': str(uuid.uuid4())})]:
            (outside / 'project.json').write_text(content)
            project = list_managed_projects(self.root / 'preferred')['projects'][0]
            self.assertFalse(project['available'])
            self.assertEqual(project['uuid'], saved['project_uuid'])
            self.assertEqual(project['name'], 'External study')
        (outside / 'project.json').unlink()
        (outside / 'catalog.json').unlink()
        outside.rmdir()
        project = list_managed_projects(self.root / 'preferred')['projects'][0]
        self.assertFalse(project['available'])
        self.assertIn('reconnect', project['unavailable_reason'])

    def test_native_external_copies_keep_path_identity_recent_and_global_order(self):
        from workspace_projects import create_project_at, list_managed_projects
        from workspace_startup_registry import remember_project_path, remember_project_paths_order
        first = create_project_at(str(self.root / 'elsewhere/first'), 'Same study')
        second = self.root / 'other/copy'
        import shutil
        second.parent.mkdir()
        shutil.copytree(first['path'], second)
        remember_project_path(first['path'], set_last=True)
        remember_project_path(second.resolve(), set_last=True)
        paths = [str(second.resolve()), first['path']]
        remember_project_paths_order(paths)
        inventory = list_managed_projects(self.root / 'unrelated')
        self.assertEqual([project['path'] for project in inventory['projects']], paths)
        self.assertEqual({project['uuid'] for project in inventory['projects']}, {first['uuid']})
        self.assertEqual(inventory['last_project_path'], str(second.resolve()))
        self.assertEqual(inventory['last_project_uuid'], first['uuid'])
        self.assertEqual([project['path'] for project in list_projects(Path(first['path']))['projects']], paths)
        self.assertFalse((self.root / 'elsewhere/.project-create.lock').exists())
        self.assertFalse((self.root / 'elsewhere/.rieke-os.json').exists())

    def test_relocation_updates_only_local_reference_and_current_recent_path(self):
        from workspace_projects import list_managed_projects
        from workspace_startup_registry import remember_project_path, remember_project_paths_order, read_project_index
        outside = self.make_project('outside/selected', 'External study')
        remember_project_path(outside.resolve(), set_last=True)
        remember_project_paths_order([str(outside.resolve())])
        moved = self.root / 'moved'
        previous = outside.resolve()
        outside.rename(moved)
        remember_project_path(moved.resolve(), previous_directory=previous)
        index = read_project_index()
        self.assertEqual([project['path'] for project in index['projects']], [str(moved.resolve())])
        self.assertEqual(index['last_project_path'], str(moved.resolve()))
        self.assertEqual(index['project_order'], [str(moved.resolve())])
        self.assertEqual(len(list_managed_projects(self.root)['projects']), 2)

    def test_prepared_packages_are_not_live_selectable_or_remembered_projects(self):
        from workspace_projects import list_managed_projects
        from workspace_startup_registry import remember_project_path, project_index_path
        package = self.make_project('received', 'Prepared study')
        (package / 'transfer.json').write_text('{}')
        self.assertEqual(len(list_managed_projects(self.root)['projects']), 1)
        self.assertEqual(len(list_projects(self.current)['projects']), 1)
        with self.assertRaisesRegex(ValueError, 'restored'):
            remember_project_path(package.resolve())
        self.assertFalse(project_index_path().exists())


if __name__ == '__main__':
    unittest.main()
