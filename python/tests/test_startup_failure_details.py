import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspace_mysql_runtime import _probe
from workspace_desktop import initialize_before_project_database, validate_child_startup_receipt
from workspace_startup_failure import RequiredComponentError, startup_failure_message


class StartupFailureDetails(unittest.TestCase):
    def test_repeated_missing_client_fails_then_repaired_client_probes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bin').mkdir()
            for name in ('mysqld', 'mysqldump'):
                binary = root / 'bin' / name
                binary.touch(); binary.chmod(0o700)
            with patch('workspace_mysql_runtime.subprocess.run', return_value=SimpleNamespace(stdout='Ver 8.4.2')):
                for _ in range(2):
                    with self.assertRaises(RequiredComponentError) as caught:
                        _probe(root, '8.4.2')
                    self.assertEqual((caught.exception.component, caught.exception.reason), ('mysql', 'missing'))
                    message = startup_failure_message(root / 'logs/workspace-launch.log', vars(caught.exception))
                    self.assertIn('MySQL client is missing', message)
                    self.assertIn('trusted distribution', message)
                    self.assertIn('do not delete or replace the project database', message)
                    self.assertIn(str(root / 'logs/workspace-launch.log'), message)
                binary = root / 'bin/mysql'; binary.touch(); binary.chmod(0o700)
                self.assertEqual(_probe(root, '8.4.2')['mysql'], str(binary))

    def test_execution_and_version_failures_are_not_claimed_as_missing_or_corrupt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'bin').mkdir()
            binary = root / 'bin/mysqld'; binary.touch(); binary.chmod(0o700)
            for error in (OSError('secret'), subprocess.CalledProcessError(1, 'secret'), subprocess.TimeoutExpired('secret', 20)):
                with patch('workspace_mysql_runtime.subprocess.run', side_effect=error):
                    with self.assertRaises(RequiredComponentError) as caught: _probe(root, '8.4.2')
                self.assertEqual(caught.exception.reason, 'unavailable')
                self.assertNotIn('secret', str(caught.exception))
            with patch('workspace_mysql_runtime.subprocess.run', return_value=SimpleNamespace(stdout='wrong secret')):
                with self.assertRaises(RequiredComponentError) as caught: _probe(root, '8.4.2')
            self.assertEqual(caught.exception.reason, 'incompatible')

    def test_private_receipt_carries_only_allowlisted_diagnosis_and_still_checks_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'catalog.json').write_text('{"project_uuid":"p"}')
            read, write = os.pipe()
            args = SimpleNamespace(project_dir=root, ready_fd=write, session_id='00000000-0000-0000-0000-000000000001', port=9000)
            def fail(): raise RequiredComponentError('mysql', 'missing')
            with self.assertRaises(RequiredComponentError):
                initialize_before_project_database(args, dict(application_version='1', source_commit='abc'), fail)
            with os.fdopen(read) as source: line = source.read()
            record = json.loads(line.split('=', 1)[1])
            result = validate_child_startup_receipt(line, record)
            self.assertFalse(result['valid']); self.assertTrue(result['pre_database_failed'])
            self.assertEqual(result['component_failure'], dict(component='mysql', reason='missing'))
            with self.assertRaises(ValueError): validate_child_startup_receipt(line, {**record, 'pid': -1})
            for failure in ({'component': 'password=secret', 'reason': 'missing'}, {'component': [], 'reason': 'missing'}, None):
                bad = {**record, 'component_failure': failure}
                result = validate_child_startup_receipt('RIEKE_DESKTOP_STARTUP_FAILED=' + json.dumps(bad), record)
                message = startup_failure_message('/owned/log', result.get('component_failure'))
                self.assertIn('cause has not been identified', message)
                self.assertNotIn('secret', message)
                self.assertNotIn('trusted distribution', message)


if __name__ == '__main__': unittest.main()
