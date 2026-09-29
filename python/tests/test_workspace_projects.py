import json
from pathlib import Path
import tempfile
import unittest
import uuid

from workspace_projects import list_projects, MANIFEST_LIMIT


class ProjectDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
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

    def test_current_first_display_name_preferred_and_no_connection_contents_returned(self):
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
                         ['Current project', 'Alpha', 'Beta'])
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


if __name__ == '__main__':
    unittest.main()
