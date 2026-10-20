"""Owned transfer/verify/migration staging folders; disposable files only, no MySQL."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from disco.projects import runtime_state, staging
import workspace_portability as transfer
from workspace_projects import create_project


class StagingOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.parent = self.root / 'destinations'
        self.parent.mkdir()
        isolated = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(self.root / 'profile/project-index.json')})
        isolated.start()
        self.addCleanup(isolated.stop)

    def registry(self):
        return staging.read_registry()['folders']

    def crashed_folder(self, prefix='.rieke-transfer-'):
        """A real child process creates a staging folder and dies without cleanup."""
        script = ('import sys, os; from disco.projects import staging; '
                  'path = staging.create_staging(sys.argv[1], sys.argv[2], "prepare_transfer"); '
                  '(path / "partial.sql").write_text("partial"); print(path); sys.stdout.flush(); os._exit(0)')
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.parent), prefix],
                                capture_output=True, text=True, timeout=30,
                                env={**os.environ, 'PYTHONPATH': str(Path(staging.__file__).resolve().parents[2])})
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def test_owner_file_and_registry_record_each_new_staging_folder(self):
        folder = staging.create_staging(self.parent, '.rieke-verify-', 'verify_transfer')
        owner = json.loads((folder / staging.OWNER_FILE).read_text())
        self.assertEqual(owner['pid'], os.getpid())
        self.assertAlmostEqual(owner['process_created'], runtime_state.current_process_created(), places=3)
        self.assertEqual([item['path'] for item in self.registry()], [str(folder)])
        self.assertEqual(self.registry()[0]['operation_id'], owner['operation_id'])
        staging.discard_staging(folder)
        self.assertFalse(folder.exists())
        self.assertEqual(self.registry(), [])

    def test_crash_left_folder_is_swept_and_live_owner_is_kept(self):
        crashed = self.crashed_folder()
        self.assertTrue(crashed.exists())
        report = staging.sweep_registered_staging()
        self.assertFalse(crashed.exists())
        self.assertEqual(report['removed'], [str(crashed)])
        live = staging.create_staging(self.parent, '.rieke-migration-', 'migrate_source')
        report = staging.sweep_registered_staging()
        self.assertTrue(live.exists())
        self.assertEqual(report['removed'], [])
        self.assertEqual(report['retained'][0]['reason'], 'owner_running')
        self.assertEqual([item['path'] for item in self.registry()], [str(live)])

    def test_unowned_folders_are_never_deleted_and_are_reported(self):
        registered = self.crashed_folder()
        (registered / staging.OWNER_FILE).unlink()
        unregistered = self.parent / '.rieke-transfer-from-an-older-version'
        unregistered.mkdir()
        report = staging.sweep_registered_staging()
        self.assertTrue(registered.exists())
        self.assertTrue(unregistered.exists())
        self.assertEqual([item['path'] for item in report['retained']], [str(registered)])
        self.assertEqual(report['retained'][0]['reason'], 'owner_file_missing')
        self.assertEqual(staging.last_report()['retained'][0]['path'], str(registered))

    def test_verify_folder_database_is_stopped_before_removal(self):
        crashed = self.crashed_folder('.rieke-verify-')
        project = crashed / 'project'
        (project / 'database').mkdir(parents=True)
        events = []
        states = iter([{'state': runtime_state.RUNNING_OWNED, 'reason': 'alive'},
                       {'state': runtime_state.STOPPED_CLEAN, 'reason': 'clean'}])
        def stop(path):
            events.append(('stop', Path(path)))
            self.assertTrue(crashed.exists())
            return True
        with patch.object(runtime_state, 'project_runtime_state', side_effect=lambda path: next(states)), \
             patch('workspace_native_mysql.stop_native_database', side_effect=stop):
            report = staging.sweep_registered_staging()
        self.assertEqual(events, [('stop', project)])
        self.assertFalse(crashed.exists())
        self.assertEqual(report['removed'], [str(crashed)])

    def test_verify_folder_with_unstoppable_database_is_retained(self):
        crashed = self.crashed_folder('.rieke-verify-')
        (crashed / 'project/database').mkdir(parents=True)
        with patch.object(runtime_state, 'project_runtime_state',
                          return_value={'state': runtime_state.RUNNING_OWNED, 'reason': 'alive'}), \
             patch('workspace_native_mysql.stop_native_database', side_effect=ValueError('still shutting down')):
            report = staging.sweep_registered_staging()
        self.assertTrue(crashed.exists())
        self.assertEqual(report['retained'][0]['reason'], 'database_running')
        self.assertEqual(len(self.registry()), 1)

    def test_new_transfer_sweeps_crashed_staging_first_and_publishes_no_owner_file(self):
        crashed = self.crashed_folder()
        project = create_project(self.root / 'workspace', 'Staged')
        root = Path(project['path'])
        connection = MagicMock()
        with patch('disco.projects.project_database.ensure_project_database'), \
             patch.object(transfer, '_connection', return_value=connection), \
             patch.object(transfer, '_sources', return_value=[]), \
             patch.object(transfer, '_dump', side_effect=ValueError('dump failed')):
            with self.assertRaisesRegex(ValueError, 'dump failed'):
                transfer.prepare_project(root, self.parent / 'outgoing')
        self.assertFalse(crashed.exists())
        self.assertEqual(list(self.parent.glob('.rieke-*')), [])
        self.assertEqual(self.registry(), [])

    def test_migration_uses_owned_staging_and_removes_it_after_failure(self):
        from disco.projects import migration
        source = self.root / 'legacy'
        source.mkdir()
        seen = []
        def failing_snapshot(project, destination):
            parent = Path(destination).parent
            seen.append(json.loads((parent / staging.OWNER_FILE).read_text())['operation'])
            raise ValueError('snapshot failed')
        with patch.object(migration, 'snapshot_source_project', side_effect=failing_snapshot):
            with self.assertRaisesRegex(ValueError, 'snapshot failed'):
                migration.migrate_source_project(source, self.parent / 'desktop-copy')
        self.assertEqual(seen, ['migrate_source'])
        self.assertEqual(list(self.parent.glob('.rieke-*')), [])
        self.assertEqual(self.registry(), [])

    def test_owner_file_is_removed_before_a_staging_folder_is_published(self):
        folder = staging.create_staging(self.parent, '.rieke-transfer-', 'prepare_transfer')
        staging.release_owner(folder)
        self.assertFalse((folder / staging.OWNER_FILE).exists())
        target = self.parent / 'published'
        folder.rename(target)
        staging.forget_staging(folder)
        self.assertEqual(self.registry(), [])
        self.assertEqual(list(target.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
