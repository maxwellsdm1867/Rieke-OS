import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from workspace_projects import create_project
from workspace_native_database import descriptor, ensure_native_database, read_state, save_state, running, stop_native_database, validate_catalog_location
from recording_workspace import configured_container

class NativeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = create_project(Path(self.temp.name)/'workspace', 'Native project')
        self.root = Path(self.project['path'])

    def test_new_projects_use_native_credentials_and_isolated_storage(self):
        root, expected = descriptor(self.root)
        self.assertEqual(configured_container(root), root)
        self.assertEqual(expected['project_uuid'], self.project['uuid'])
        self.assertFalse((root/'database/mysql').exists())
        self.assertNotIn('password', (root/'catalog.json').read_text())

    def test_wrong_owner_and_symlinks_rejected(self):
        path = self.root/'database/service.json'
        value = json.loads(path.read_text()); value['project_uuid'] = 'foreign'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'ownership'):
            descriptor(self.root)

    def test_orphaned_files_never_reinitialized(self):
        data = self.root/'database/mysql'; data.mkdir()
        (data/'science').write_text('preserve')
        with patch('workspace_native_database.server_binary', return_value=Path('/unused/mysqld')), patch('workspace_native_database.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'Recover'):
                ensure_native_database(self.root)
            run.assert_not_called()
        self.assertEqual((data/'science').read_text(), 'preserve')

    def test_credentials_private_and_identity_checked(self):
        state = {'version':1,'project_uuid':self.project['uuid'],'port':45001,'password':'x'*64}
        save_state(self.root, state)
        self.assertEqual((self.root/'database/native.json').stat().st_mode & 0o777, 0o600)
        _, expected = descriptor(self.root)
        self.assertEqual(read_state(self.root, expected), state)
        with self.assertRaises(ValueError):
            read_state(self.root, {**expected,'project_uuid':'foreign'})

    def fake_connection(self, data_dir):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ('server-uuid', str(data_dir))
        cursor.fetchall.return_value = []
        return connection, cursor

    def test_same_server_uuid_in_different_directory_is_not_attached_or_stopped(self):
        state = {'version':1, 'project_uuid':self.project['uuid'], 'port':45001,
                 'password':'x'*64, 'server_uuid':'server-uuid'}
        save_state(self.root, state)
        connection, cursor = self.fake_connection(self.root.parent / 'original/database/mysql')
        with patch('workspace_native_database.sql_connection', return_value=connection), \
             patch('workspace_native_database.server_binary') as binary:
            for operation in (ensure_native_database, stop_native_database):
                with self.subTest(operation=operation.__name__), self.assertRaisesRegex(ValueError, 'different project folder'):
                    operation(self.root)
            binary.assert_not_called()
        self.assertTrue(all(call.args[0] != 'SHUTDOWN' for call in cursor.execute.call_args_list))
        self.assertEqual(json.loads((self.root/'database/native.json').read_text()), state)

    def test_matching_physical_datadir_is_accepted(self):
        data = self.root / 'database/mysql'
        connection, _ = self.fake_connection(data)
        with patch('workspace_native_database.sql_connection', return_value=connection):
            self.assertTrue(running({'server_uuid':'server-uuid'}, data))
            self.assertFalse(running({'server_uuid':'other'}, data))

    def test_moved_catalog_metadata_is_rejected_without_rebasing(self):
        connection, cursor = self.fake_connection(self.root/'database/mysql')
        old = str(self.root.parent/'old-project/imports/source/metadata.catalog.json')
        cursor.fetchall.return_value = [(json.dumps({'metadata_path':old}),)]
        with patch('workspace_native_database.sql_connection', return_value=connection):
            with self.assertRaisesRegex(ValueError, 'moved or copied'):
                validate_catalog_location(self.root, {'project_uuid':self.project['uuid']})
        self.assertEqual(cursor.execute.call_count, 1)
        self.assertTrue(cursor.execute.call_args.args[0].startswith('SELECT'))

    def test_empty_or_current_catalog_location_is_accepted(self):
        connection, cursor = self.fake_connection(self.root/'database/mysql')
        for rows in ([], [(json.dumps({'metadata_path':str(self.root/'imports/source/metadata.catalog.json')}),)]):
            cursor.fetchall.return_value = rows
            with patch('workspace_native_database.sql_connection', return_value=connection):
                validate_catalog_location(self.root, {'project_uuid':self.project['uuid']})
