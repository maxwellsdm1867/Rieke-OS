import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workspace_projects import create_project
from workspace_native_database import descriptor, ensure_native_database, read_state, save_state
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
