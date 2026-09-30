import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workspace_projects import create_project, create_project_at
from workspace_project_validation import inspect_project_folder, validate_project_folder


class ProjectValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = create_project(Path(self.temp.name) / 'projects', 'Validation')
        self.root = Path(self.record['path'])

    def initialized(self):
        descriptor = json.loads((self.root / 'database/service.json').read_text())
        identity = {key: descriptor[key] for key in ('version', 'project_uuid', 'instance_uuid')}
        (self.root / 'database/native-owner.json').write_text(json.dumps({**identity, 'mysql_series': '8.4', 'clean_shutdown': True}))
        (self.root / 'database/native-credentials.json').write_text(json.dumps({**identity, 'password': 'fixture-only' * 4}))
        data = self.root / 'database/mysql'
        data.mkdir()
        for name in ('mysql.ibd', 'ibdata1'):
            (data / name).write_bytes(b'disposable presence fixture')

    def test_new_project_validation_does_not_create_or_modify_files(self):
        before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in self.root.rglob('*') if p.is_file()}
        with patch('workspace_native_mysql.ensure_native_database', side_effect=AssertionError('No server')):
            result = validate_project_folder(self.root)
        after = {str(p): (p.read_bytes(), p.stat().st_mode) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result['database_status'], 'not_initialized')
        self.assertEqual(result['project']['uuid'], self.record['uuid'])
        self.assertEqual(inspect_project_folder(self.root)['kind'], 'project')

    def prepared(self):
        import workspace_portability as transfer
        package = Path(self.temp.name) / 'received package'
        package.mkdir()
        (package / 'project.json').write_text((self.root / 'project.json').read_text())
        (package / 'database.sql').write_text('-- logical backup fixture\n')
        transfer._write(package / transfer.MANIFEST, {
            'format': transfer.FORMAT, 'version': 1, 'mode': 'complete',
            'database_format': 'mysql8-logical-v1', 'project_uuid': self.record['uuid'],
            'sources': [], 'files': transfer._files(package)})
        return package

    def test_prepared_copy_is_recognized_without_runtime_or_file_changes(self):
        package = self.prepared()
        before = {p.name: p.read_bytes() for p in package.iterdir()}
        with patch('workspace_project_database.ensure_project_database', side_effect=AssertionError('No server')):
            result = inspect_project_folder(package)
        self.assertEqual(result['kind'], 'prepared-transfer')
        self.assertEqual(result['database_status'], 'restore_required')
        self.assertEqual(result['project']['uuid'], self.record['uuid'])
        self.assertEqual(result['project']['name'], 'Validation')
        self.assertEqual(result['source_count'], 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in package.iterdir()})

    def test_corrupt_received_copy_is_not_offered_as_an_openable_project(self):
        package = self.prepared()
        (package / 'database.sql').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum|inventory'):
            inspect_project_folder(package)

    def test_received_manifest_cannot_bypass_validation_with_project_catalog(self):
        (self.root / 'transfer.json').write_text('{"format":"future","version":2}')
        with self.assertRaisesRegex(ValueError, 'Unsupported prepared project'):
            inspect_project_folder(self.root)

    def test_initialized_project_never_returns_credentials_or_chmods(self):
        self.initialized()
        credentials = self.root / 'database/native-credentials.json'
        credentials.chmod(0o644)
        result = validate_project_folder(self.root)
        self.assertEqual(result['database_status'], 'initialized')
        self.assertNotIn('fixture-only', json.dumps(result))
        self.assertEqual(credentials.stat().st_mode & 0o777, 0o644)

    def test_missing_data_is_not_treated_as_new_project(self):
        self.initialized()
        for p in (self.root / 'database/mysql').iterdir():
            p.unlink()
        with self.assertRaisesRegex(ValueError, 'previously initialized'):
            validate_project_folder(self.root)

    def test_missing_core_file_is_rejected(self):
        self.initialized()
        (self.root / 'database/mysql/mysql.ibd').unlink()
        with self.assertRaisesRegex(ValueError, 'mysql.ibd'):
            validate_project_folder(self.root)

    def test_missing_owner_preserves_incomplete_database(self):
        self.initialized()
        (self.root / 'database/native-owner.json').unlink()
        with self.assertRaisesRegex(ValueError, 'ownership is missing'):
            validate_project_folder(self.root)

    def test_missing_layout_or_service_or_managed_folder_is_descriptive(self):
        for relative in ('storage.json', 'database/service.json', 'imports'):
            with self.subTest(relative=relative):
                path = self.root / relative
                saved = path.with_name(path.name + '.saved')
                path.rename(saved)
                try:
                    with self.assertRaisesRegex(ValueError, relative):
                        validate_project_folder(self.root)
                finally:
                    saved.rename(path)

    def test_legacy_project_does_not_require_native_layout(self):
        catalog = json.loads((self.root / 'catalog.json').read_text())
        catalog.pop('managed_database')
        catalog['connection']['credential_provider'] = {'kind': 'docker-container-env', 'container': 'legacy'}
        (self.root / 'catalog.json').write_text(json.dumps(catalog))
        (self.root / 'storage.json').unlink()
        self.assertEqual(validate_project_folder(self.root)['database_status'], 'legacy_external')

    def test_manifest_identity_mismatch_and_project_symlink_are_rejected(self):
        link = self.root.parent / 'linked'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            validate_project_folder(link)
        catalog = json.loads((self.root / 'catalog.json').read_text())
        catalog['project_uuid'] = '11111111-1111-4111-8111-111111111111'
        (self.root / 'catalog.json').write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, 'UUIDs do not match'):
            validate_project_folder(self.root)

    def test_nested_selection_suggests_closest_root_without_opening_or_changes(self):
        before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in self.root.rglob('*') if p.is_file()}
        with patch('workspace_project_database.ensure_project_database', side_effect=AssertionError('No server')):
            result = inspect_project_folder(self.root / 'logs/imports')
        self.assertFalse(result['valid'])
        self.assertEqual(result['kind'], 'project-root-suggestions')
        self.assertEqual(result['candidates'], [{'path': str(self.root), 'name': 'Validation',
                                                'kind': 'project', 'reason': 'containing-project'}])
        after = {str(p): (p.read_bytes(), p.stat().st_mode) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_parent_with_several_projects_suggests_all_immediate_valid_roots(self):
        second = create_project_at(str(self.root.parent / 'Exact second project'), 'Second project')
        broken = self.root.parent / 'broken project'
        broken.mkdir()
        (broken / 'project.json').write_text('{"format":"unknown"}')
        (self.root.parent / 'project alias').symlink_to(self.root, target_is_directory=True)
        with patch('workspace_project_database.ensure_project_database', side_effect=AssertionError('No server')):
            result = inspect_project_folder(self.root.parent)
        self.assertFalse(result['valid'])
        self.assertEqual(result['kind'], 'project-root-suggestions')
        paths = {value['path'] for value in result['candidates']}
        self.assertEqual(paths, {str(self.root), second['path']})
        self.assertTrue(all(value['reason'] == 'child-project' for value in result['candidates']))
        self.assertIn('Several projects', result['message'])

    def test_prepared_root_suggestions_validate_complete_inventory(self):
        package = self.prepared().resolve()
        nested = package / 'protocols'
        nested.mkdir()
        result = inspect_project_folder(nested)
        self.assertEqual(result['candidates'][0]['path'], str(package))
        self.assertEqual(result['candidates'][0]['kind'], 'prepared-transfer')
        (package / 'database.sql').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'project.json'):
            inspect_project_folder(nested)

    def test_no_recursive_child_scan_or_automatic_choice(self):
        selected = Path(self.temp.name).resolve() / 'Parent selected by user'
        selected.mkdir()
        deeper = selected / 'one folder down'
        deeper.mkdir()
        create_project_at(str(deeper / 'too deep'), 'Not an immediate child')
        with self.assertRaisesRegex(ValueError, 'project.json'):
            inspect_project_folder(selected)
        create_project_at(str(selected / 'correct root'), 'One direct child')
        result = inspect_project_folder(selected)
        self.assertFalse(result['valid'])
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(result['candidates'][0]['path'], str(selected / 'correct root'))

    def test_selected_project_can_live_far_outside_preferred_parent(self):
        exact = Path(self.temp.name).resolve() / 'Research drives/2026/North lab/My chosen top folder'
        exact.parent.mkdir(parents=True)
        project = create_project_at(str(exact), 'Independent project')
        with patch.dict('os.environ', {'RECORDING_WORKSPACE_ROOT': str(self.root.parent)}):
            report = inspect_project_folder(exact)
            nested = inspect_project_folder(exact / 'imports')
        self.assertEqual(report['kind'], 'project')
        self.assertEqual(report['project']['path'], str(exact))
        self.assertEqual(report['project']['uuid'], project['uuid'])
        self.assertEqual(nested['candidates'][0]['path'], str(exact))

    def test_selected_alias_and_alias_children_are_never_suggested(self):
        selected = Path(self.temp.name).resolve() / 'only aliases'
        selected.mkdir()
        alias = selected / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            inspect_project_folder(alias)
        with self.assertRaisesRegex(ValueError, 'project.json'):
            inspect_project_folder(selected)
        with self.assertRaisesRegex(ValueError, 'project.json'):
            inspect_project_folder(alias / 'imports')

    def test_ancestor_search_is_bounded(self):
        selected = self.root / 'logs'
        for index in range(9):
            selected = selected / ('nested-' + str(index))
        selected.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'project.json'):
            inspect_project_folder(selected)


if __name__ == '__main__':
    unittest.main()
