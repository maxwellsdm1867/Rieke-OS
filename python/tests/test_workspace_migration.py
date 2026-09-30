"""Read-only legacy migration boundary contracts; real SQL is exercised by E2E."""
import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from workspace_migration import inspect_source_container, readonly_project_session, source_connection, _source_dump


class MigrationBoundaryTests(unittest.TestCase):
    def test_declared_container_cannot_select_another_docker_api(self):
        for value in ('../../containers', '/all', 'project?force=true', '', None):
            with self.subTest(value=value), patch('workspace_migration._UnixHTTPConnection') as connect:
                with self.assertRaisesRegex(ValueError, 'identity'):
                    inspect_source_container(value)
                connect.assert_not_called()

    def test_unavailable_source_has_actionable_transfer_alternative(self):
        with tempfile.TemporaryDirectory() as temporary, patch('workspace_migration.Path.home', return_value=Path(temporary)), \
                patch('workspace_migration.Path.resolve', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, 'prepare a transfer'):
                inspect_source_container('existing-project')

    def test_existing_source_lease_blocks_without_creating_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / '.app-state-session.lock'
            path.write_bytes(b'existing source lease')
            with path.open('r') as existing:
                fcntl.flock(existing.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, 'still active'):
                    with readonly_project_session(root):
                        self.fail('Source lease was ignored')
            self.assertEqual(path.read_bytes(), b'existing source lease')
            path.unlink()
            with readonly_project_session(root):
                self.assertEqual(list(root.iterdir()), [])

    def test_source_profile_must_be_declared_loopback_and_not_native(self):
        for profile in ({'host': 'remote.example', 'credential_provider': {'kind': 'docker-container-env'}},
                        {'host': '127.0.0.1', 'credential_provider': {'kind': 'native-project'}}):
            with self.subTest(profile=profile), patch('workspace_migration._json', return_value={'connection': profile}), \
                    patch('workspace_migration.inspect_source_container') as inspect:
                with self.assertRaisesRegex(ValueError, 'localhost Docker'):
                    source_connection('/source')
                inspect.assert_not_called()

    def test_backup_omits_only_explicitly_verified_derived_triggers_and_keeps_password_off_argv(self):
        settings = {'port': 3307, 'user': 'root', 'password': 'private-source-credential'}
        commands = []
        def backup(arguments, **kwargs):
            commands.append(arguments)
            self.assertNotIn(settings['password'], ' '.join(arguments))
            self.assertEqual(kwargs['env']['MYSQL_PWD'], settings['password'])
            kwargs['stdout'].write(b'logical backup fixture')
            return Mock(returncode=0)
        with tempfile.TemporaryDirectory() as temporary, \
                patch('workspace_native_mysql.native_binary', return_value=Path('/bundle/mysqldump')), \
                patch('workspace_migration.subprocess.run', side_effect=backup):
            _source_dump(settings, Path(temporary)/'original.sql')
            _source_dump(settings, Path(temporary)/'verified.sql', omit_derived_triggers=True)
        self.assertNotIn('--skip-triggers', commands[0])
        self.assertIn('--skip-triggers', commands[1])
        self.assertTrue(all('--skip-lock-tables' in command for command in commands))


if __name__ == '__main__':
    unittest.main()
