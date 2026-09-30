"""Private MySQL ownership guards and an opt-in Docker-free lifecycle test."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid

import workspace_native_mysql as native
from workspace_project_database import ensure_project_database


class NativeMysqlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rieke-native-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / 'project'
        self.root.mkdir()
        (self.root / 'database').mkdir()
        self.identity = str(uuid.uuid4())
        self.catalog = native.native_catalog(self.identity)
        self.descriptor = self.catalog['managed_database']
        (self.root / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1,
            'project_uuid': self.identity, 'name': 'Native test'}))
        (self.root / 'catalog.json').write_text(json.dumps(self.catalog))
        (self.root / 'database/service.json').write_text(json.dumps(self.descriptor))

    def test_native_dispatch_never_calls_docker(self):
        with patch('workspace_project_database._run') as docker, patch.object(native, 'ensure_native_database', return_value={'pid': 42}) as start:
            self.assertEqual(ensure_project_database(self.root), {'pid': 42})
            start.assert_called_once_with(self.root, timeout=120)
            docker.assert_not_called()

    def test_orphaned_data_never_initialized_or_credentials_created(self):
        data = self.root / 'database/mysql'
        data.mkdir()
        (data / 'existing.ibd').write_bytes(b'preserve')
        with patch.object(native, 'native_binary'), patch('subprocess.Popen') as process:
            with self.assertRaisesRegex(ValueError, 'no native ownership'):
                native.ensure_native_database(self.root)
            process.assert_not_called()
        self.assertEqual((data / 'existing.ibd').read_bytes(), b'preserve')
        self.assertFalse((self.root / self.descriptor['credentials_ref']).exists())

    def test_runtime_missing_does_not_create_credentials(self):
        with patch.object(native, 'native_binary', side_effect=ValueError('runtime missing')):
            with self.assertRaisesRegex(ValueError, 'runtime missing'):
                native.ensure_native_database(self.root)
        self.assertFalse((self.root / self.descriptor['credentials_ref']).exists())

    def test_credential_permissions_and_identity_are_verified(self):
        credential_path = self.root / self.descriptor['credentials_ref']
        native._write(credential_path, {'project_uuid': self.identity,
            'instance_uuid': self.descriptor['instance_uuid'], 'password': 'x' * 40})
        self.assertEqual(stat.S_IMODE(credential_path.stat().st_mode), 0o600)
        self.assertEqual(native._credentials(self.root, self.descriptor)['password'], 'x' * 40)
        credential_path.chmod(0o644)
        self.assertEqual(native._credentials(self.root, self.descriptor)['password'], 'x' * 40)
        self.assertEqual(stat.S_IMODE(credential_path.stat().st_mode), 0o600)
        with patch.object(native.os, 'getuid', return_value=credential_path.stat().st_uid + 1), patch.object(native.os, 'fchmod') as chmod:
            with self.assertRaisesRegex(ValueError, 'owned by this user'):
                native._credentials(self.root, self.descriptor)
            chmod.assert_not_called()

    def test_foreign_pid_is_never_signalled(self):
        import psutil
        me = psutil.Process()
        forged = {'pid': me.pid, 'process_created': me.create_time(),
                  'executable': '/not/the/current/executable', 'argv': me.cmdline()}
        with patch('os.kill') as kill:
            with self.assertRaisesRegex(ValueError, 'ownership changed'):
                native._owned_process(forged)
            kill.assert_not_called()

    def test_recycled_pid_is_stale_and_never_signalled(self):
        import psutil
        me = psutil.Process()
        stale = {'pid': me.pid, 'process_created': me.create_time() - 100,
                 'executable': '/old/mysqld', 'argv': ['/old/mysqld']}
        with patch('os.kill') as kill:
            self.assertIsNone(native._owned_process(stale))
            kill.assert_not_called()

    def test_symlinked_data_and_changed_descriptors_fail_before_start(self):
        (self.root / 'database/mysql').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            native._configuration(self.root)
        (self.root / 'database/mysql').unlink()
        bad = dict(self.descriptor, instance_uuid=str(uuid.uuid4()))
        (self.root / 'database/service.json').write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, 'ownership records disagree'):
            native._configuration(self.root)

    def test_dirty_relocated_folder_is_refused_without_start(self):
        data = self.root / 'database/mysql'
        data.mkdir()
        native._write(self.root / 'database/native-owner.json', {'version': 1, 'project_uuid': self.identity,
            'instance_uuid': self.descriptor['instance_uuid'], 'mysql_series': '8.4',
            'clean_shutdown': False, 'last_project_path': '/another-machine/original'})
        with patch.object(native, 'native_binary'), patch.object(native, '_machine_identity', return_value='known-machine'), patch('subprocess.Popen') as process:
            with self.assertRaisesRegex(ValueError, 'not closed cleanly'):
                native.ensure_native_database(self.root)
            process.assert_not_called()

    def _owned_fixture(self, *, clean, machine='machine-a', path=None):
        (self.root / 'database/mysql').mkdir(exist_ok=True)
        native._write(self.root / 'database/native-owner.json', {'version': 1, 'project_uuid': self.identity,
            'instance_uuid': self.descriptor['instance_uuid'], 'mysql_series': '8.4',
            'clean_shutdown': clean, 'last_project_path': str(path or self.root), 'machine_id': machine})
        native._write(self.root / self.descriptor['credentials_ref'], {'version': 1, 'project_uuid': self.identity,
            'instance_uuid': self.descriptor['instance_uuid'], 'password': 'x' * 40})

    def test_dirty_same_path_on_another_machine_or_unknown_machine_is_rejected(self):
        self._owned_fixture(clean=False)
        for machine in ('machine-b', None):
            with self.subTest(machine=machine), patch.object(native, '_machine_identity', return_value=machine), \
                 patch.object(native, 'native_binary'), patch.object(native, '_launch') as launch:
                with self.assertRaisesRegex(ValueError, 'not closed cleanly'):
                    native.ensure_native_database(self.root)
                launch.assert_not_called()

    def test_crash_recovery_requires_same_known_machine_and_path(self):
        self._owned_fixture(clean=False)
        with patch.object(native, '_machine_identity', return_value='machine-a'), \
             patch.object(native, 'native_binary'), patch.object(native, '_launch', return_value={'ready': True}) as launch:
            self.assertEqual(native.ensure_native_database(self.root), {'ready': True})
            launch.assert_called_once()

    def test_clean_copy_ignores_sender_runtime_pid_and_repairs_copied_permissions(self):
        self._owned_fixture(clean=True, path=Path('/sender/project'))
        credential_path = self.root / self.descriptor['credentials_ref']
        credential_path.chmod(0o644)
        native._write(self.root / self.descriptor['runtime_ref'], {
            'project_uuid': self.identity, 'instance_uuid': self.descriptor['instance_uuid'],
            'pid': os.getpid(), 'executable': '/sender/mysqld', 'project_path': '/sender/project',
            'machine_id': 'sender-machine'})
        with patch.object(native, '_machine_identity', return_value='recipient-machine'), \
             patch.object(native, 'native_binary'), patch.object(native, '_owned_process', side_effect=AssertionError('Never inspect sender PID')), \
             patch.object(native, '_launch', return_value={'ready': True}) as launch:
            self.assertEqual(native.ensure_native_database(self.root), {'ready': True})
            launch.assert_called_once()
        self.assertEqual(stat.S_IMODE(credential_path.stat().st_mode), 0o600)

    def test_successful_shutdown_request_can_finish_after_wait_timeout(self):
        self._owned_fixture(clean=False)
        runtime = {'pid': 123456789, 'socket': '/private/test.sock', 'machine_id': 'machine-a'}
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (str(self.root / 'database/mysql'), runtime['socket'])
        with patch.object(native, '_owned_process', return_value=MagicMock()), \
             patch.object(native, '_unix_connection', return_value=connection), \
             patch.object(native, '_await_shutdown', side_effect=ValueError('still shutting down')):
            with self.assertRaisesRegex(ValueError, 'still shutting down'):
                native._shutdown(self.root, self.descriptor, runtime, 'unused')
        pending = native._read(self.root / self.descriptor['runtime_ref'])
        self.assertTrue(pending['shutdown_requested'])
        self.assertFalse(native._read(self.root / 'database/native-owner.json')['clean_shutdown'])
        with patch.object(native, '_runtime', return_value=pending), \
             patch.object(native, '_owned_process', return_value=None), \
             patch.object(native, '_machine_identity', return_value='machine-a'), \
             patch.object(native, '_unix_connection', side_effect=AssertionError('Do not reconnect to a stopped server')):
            self.assertTrue(native.stop_native_database(self.root))
        self.assertTrue(native._read(self.root / 'database/native-owner.json')['clean_shutdown'])
        self.assertFalse((self.root / self.descriptor['runtime_ref']).exists())

    def test_missing_process_without_authenticated_shutdown_remains_dirty(self):
        self._owned_fixture(clean=False)
        runtime = {'pid': 123456789, 'machine_id': 'machine-a'}
        native._write(self.root / self.descriptor['runtime_ref'], runtime)
        with patch.object(native, '_runtime', return_value=runtime), \
             patch.object(native, '_owned_process', return_value=None), \
             patch.object(native, '_machine_identity', return_value='machine-a'):
            self.assertFalse(native.stop_native_database(self.root))
        self.assertFalse(native._read(self.root / 'database/native-owner.json')['clean_shutdown'])

    def test_machine_identity_hashes_hardware_uuid_and_fails_closed(self):
        native._machine_identity.cache_clear()
        self.addCleanup(native._machine_identity.cache_clear)
        hardware = '12345678-1234-1234-1234-123456789abc'
        with patch.object(native.os, 'uname', return_value=SimpleNamespace(sysname='Darwin')), \
             patch.object(native.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='"IOPlatformUUID" = "'+hardware+'"')):
            value = native._machine_identity()
            self.assertEqual(len(value), 64)
            self.assertNotIn(hardware, value)
        native._machine_identity.cache_clear()
        with patch.object(native.os, 'uname', return_value=SimpleNamespace(sysname='Darwin')), \
             patch.object(native.subprocess, 'run', side_effect=OSError('unavailable')):
            self.assertIsNone(native._machine_identity())

    @unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL') == '1', 'opt-in private native MySQL test')
    def test_protocol_delta_with_real_datajoint_attribute_lineages(self):
        ensure_project_database(self.root)
        try:
            script = r'''import sys
from types import SimpleNamespace
import datajoint as dj
from workspace_native_mysql import connection_parameters
from recording_workspace import new_project_protocol_types
settings = connection_parameters(sys.argv[1])
connection = dj.Connection(**settings)
schema = dj.Schema('protocol_delta_fixture', connection=connection)
@schema
class Experiment(dj.Manual):
    definition = "experiment_id: int"
@schema
class Protocol(dj.Manual):
    definition = "protocol_id: int\n---\nname: varchar(255)"
@schema
class EpochBlock(dj.Manual):
    definition = "block_id: int\n---\n-> Experiment\n-> Protocol"
@schema
class Source(dj.Manual):
    definition = "source_id: int\n---\nproject_uuid: varchar(36)\nexperiment_id: int"
Experiment.insert([{'experiment_id': 1}, {'experiment_id': 2}])
Protocol.insert([{'protocol_id': 1, 'name': 'known'}, {'protocol_id': 2, 'name': 'foreign'}])
EpochBlock.insert([{'block_id': 1, 'experiment_id': 1, 'protocol_id': 1}, {'block_id': 2, 'experiment_id': 2, 'protocol_id': 2}])
Source.insert([{'source_id': 1, 'project_uuid': 'mine', 'experiment_id': 1}, {'source_id': 2, 'project_uuid': 'other', 'experiment_id': 2}])
catalog = SimpleNamespace(EpochBlock=EpochBlock, Protocol=Protocol)
assert new_project_protocol_types(catalog, Source, 'mine', ['known', 'foreign', 'new']) == {'foreign', 'new'}
assert new_project_protocol_types(catalog, Source, 'empty', ['known']) == {'known'}
connection.close()
'''
            result = subprocess.run([sys.executable, '-c', script, str(self.root)],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, 'PYTHONPATH': str(native.ROOT / 'python')})
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            native.stop_native_database(self.root)

    @unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL') == '1', 'opt-in private native MySQL test')
    def test_project_api_process_can_close_chooser_owned_database(self):
        runtime = ensure_project_database(self.root)
        try:
            command = 'from workspace_native_mysql import stop_native_database; import sys; print(stop_native_database(sys.argv[1]))'
            started = time.monotonic()
            result = subprocess.run([sys.executable, '-c', command, str(self.root)],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, 'PYTHONPATH': str(native.ROOT / 'python')})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'True')
            self.assertLess(time.monotonic() - started, 10)
            self.assertTrue(native._read(self.root / 'database/native-owner.json')['clean_shutdown'])
            self.assertFalse((self.root / self.descriptor['runtime_ref']).exists())
            # The starter can reap its old child and reopen the project normally.
            restarted = ensure_project_database(self.root)
            self.assertNotEqual(restarted['pid'], runtime['pid'])
            self.assertNotIn(runtime['pid'], native._PROCESSES)
        finally:
            native.stop_native_database(self.root)

    @unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL') == '1', 'opt-in private native MySQL test')
    def test_initialize_restart_and_cold_folder_copy_without_docker(self):
        import pymysql
        copy = self.root.parent / 'copied-project'
        active = []
        try:
            with patch('workspace_project_database._run', side_effect=AssertionError('Docker must never run')):
                first = ensure_project_database(self.root)
                active.append(self.root)
                settings = native.connection_parameters(self.root)
                self.assertEqual(settings['host'], '127.0.0.1')
                connection = pymysql.connect(**settings, autocommit=True)
                with connection.cursor() as cursor:
                    cursor.execute('CREATE DATABASE recording_workspace')
                    cursor.execute('CREATE TABLE recording_workspace.evidence (id INT PRIMARY KEY, note TEXT)')
                    cursor.execute('INSERT INTO recording_workspace.evidence VALUES (1,%s)', ('preserve scientific state',))
                connection.close()
                again = ensure_project_database(self.root)
                self.assertEqual(first['pid'], again['pid'])
                self.assertFalse(native._read(self.root / 'database/native-owner.json')['clean_shutdown'])
                self.assertTrue(native.stop_native_database(self.root))
                active.remove(self.root)
                self.assertTrue(native._read(self.root / 'database/native-owner.json')['clean_shutdown'])
                shutil.copytree(self.root, copy)
                copied_runtime = ensure_project_database(copy)
                active.append(copy)
                original_runtime = ensure_project_database(self.root)
                active.append(self.root)
                self.assertNotEqual(copied_runtime['port'], original_runtime['port'])
                self.assertNotEqual(copied_runtime['socket'], original_runtime['socket'])
                for directory in (self.root, copy):
                    connection = pymysql.connect(**native.connection_parameters(directory))
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT note FROM recording_workspace.evidence WHERE id=1')
                        self.assertEqual(cursor.fetchone()[0], 'preserve scientific state')
                    connection.close()
                self.assertEqual(native._read(copy / 'project.json')['project_uuid'], self.identity)
        finally:
            for directory in reversed(active):
                native.stop_native_database(directory)


if __name__ == '__main__':
    unittest.main()
