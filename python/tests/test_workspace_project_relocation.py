"""Closed-project moves never start MySQL, overwrite a destination, or copy/delete."""
import errno
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from workspace_projects import create_project
import workspace_portability as transfer
import workspace_native_mysql as native


class ProjectRelocationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rieke-move-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        project = create_project(self.base / 'original-parent', 'Move study')
        self.root, self.identity = Path(project['path']), project['uuid']
        self.target = self.base / 'Chosen project folder'
        self.descriptor = json.loads((self.root / 'database/service.json').read_text())
        native._write(self.root / self.descriptor['credentials_ref'], {'version': 1,
            'project_uuid': self.identity, 'instance_uuid': self.descriptor['instance_uuid'], 'password': 'x' * 40})
        native._write(self.root / 'database/native-owner.json', {'version': 1,
            'project_uuid': self.identity, 'instance_uuid': self.descriptor['instance_uuid'],
            'mysql_series': '8.4', 'clean_shutdown': True, 'last_project_path': str(self.root),
            'machine_id': 'fixture-machine'})
        data = self.root / 'database/mysql'
        data.mkdir()
        (data / 'evidence.ibd').write_bytes(b'closed database fixture; never launch')
        (self.root / 'raw-uploads/recording.h5').write_bytes(b'preserved recording fixture')
        self.original = {path.relative_to(self.root).as_posix(): path.read_bytes()
                         for path in self.root.rglob('*') if path.is_file()}

    def assert_source_intact(self):
        self.assertTrue(self.root.is_dir())
        for relative, contents in self.original.items():
            self.assertEqual((self.root / relative).read_bytes(), contents)

    def test_move_preserves_identity_files_and_inode_without_database_start(self):
        inode = (self.root / 'database/mysql/evidence.ibd').stat().st_ino
        with patch('workspace_project_database.ensure_project_database', side_effect=AssertionError('Do not start DB')):
            result = transfer.relocate_project(self.root, self.target)
        self.assertTrue(result['moved'])
        self.assertEqual(result['project_uuid'], self.identity)
        self.assertEqual(result['directory'], str(self.target))
        self.assertEqual(result['previous_directory'], str(self.root))
        self.assertFalse(self.root.exists())
        for relative, contents in self.original.items():
            self.assertEqual((self.target / relative).read_bytes(), contents)
        self.assertEqual((self.target / 'database/mysql/evidence.ibd').stat().st_ino, inode)

    def test_existing_destination_and_related_paths_never_overwritten(self):
        self.target.mkdir()
        for target in (self.target, self.root / 'inside', self.root.parent):
            with self.subTest(target=target), self.assertRaises(ValueError):
                transfer.relocate_project(self.root, target)
        self.assert_source_intact()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_symlink_roots_are_rejected(self):
        alias = self.base / 'linked-project'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            transfer.relocate_project(alias, self.target)
        self.target.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            transfer.relocate_project(self.root, self.target)
        self.assert_source_intact()

    def test_active_app_or_startup_lock_rejects_move(self):
        for relative in ('.app-state-session.lock', 'logs/workspace-server.lock', 'database/native.lock'):
            with self.subTest(relative=relative), (self.root / relative).open('a') as active:
                fcntl.flock(active, fcntl.LOCK_SH | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, 'active|Close'):
                    transfer.relocate_project(self.root, self.target)
            self.assert_source_intact()
        self.assertFalse(self.target.exists())

    def test_dirty_database_or_interrupted_rebase_cannot_move(self):
        owner_path = self.root / 'database/native-owner.json'
        owner = json.loads(owner_path.read_text())
        native._write(owner_path, {**owner, 'clean_shutdown': False})
        with self.assertRaisesRegex(ValueError, 'cleanly'):
            transfer.relocate_project(self.root, self.target)
        native._write(owner_path, owner)
        (self.root / '.project-path-rebase.pending').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            transfer.relocate_project(self.root, self.target)
        self.assertFalse(self.target.exists())

    def test_destination_race_cannot_replace_even_empty_directory(self):
        actual = transfer._rename_project_exclusive
        def raced(source, destination):
            destination.mkdir()
            return actual(source, destination)
        with patch.object(transfer, '_rename_project_exclusive', side_effect=raced):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                transfer.relocate_project(self.root, self.target)
        self.assert_source_intact()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_cross_volume_failure_retains_source_without_partial_target(self):
        library = Mock()
        library.renamex_np.return_value = -1
        library.renameat2.return_value = -1
        with patch('ctypes.CDLL', return_value=library), patch('ctypes.get_errno', return_value=errno.EXDEV):
            with self.assertRaisesRegex(ValueError, 'between volumes'):
                transfer.relocate_project(self.root, self.target)
        self.assert_source_intact()
        self.assertFalse(self.target.exists())

    def test_never_opened_empty_native_project_can_move(self):
        fresh = create_project(self.base / 'fresh', 'Unopened project')
        result = transfer.relocate_project(fresh['path'], self.base / 'unopened destination')
        self.assertEqual(result['project_uuid'], fresh['uuid'])
        self.assertFalse((Path(result['directory']) / 'database/mysql').exists())


if __name__ == '__main__':
    unittest.main()
