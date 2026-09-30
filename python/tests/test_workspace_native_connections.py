"""Native project routing must not fall through to Docker credentials."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from recording_workspace import configured_database, connect
from workspace_recording_files import retain_recording


class NativeConnectionTests(unittest.TestCase):
    def test_native_configuration_routes_without_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            provider={'kind':'native-project','credentials_ref':'database/native-credentials.json'}
            (root/'catalog.json').write_text(json.dumps({'connection':{'credential_provider':provider}}))
            self.assertEqual(configured_database(root),provider)
            fake=types.SimpleNamespace(config={})
            with patch.dict('sys.modules',datajoint=fake), patch('workspace_native_mysql.connection_parameters',return_value={'host':'127.0.0.1','port':9999,'user':'root','password':'fixture-only'}), patch('subprocess.run',side_effect=AssertionError('Must not call Docker')):
                self.assertIs(connect(provider,project_dir=root),fake)
            self.assertEqual(fake.config['database.port'],9999)

    def test_recording_copy_survives_external_source_removal_and_checks_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original.h5';source.write_bytes(b'recording')
            project=(root/'project').resolve();project.mkdir()
            expected=hashlib.sha256(source.read_bytes()).hexdigest()
            copy=retain_recording(project,source,expected)
            self.assertTrue(copy.is_relative_to(project/'raw-uploads'))
            source.unlink();self.assertEqual(copy.read_bytes(),b'recording')
            self.assertEqual(retain_recording(project,copy,expected),copy)
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed'):
                retain_recording(project,source,expected)
            self.assertEqual(len(list((project/'raw-uploads').iterdir())),1)

    def test_existing_managed_copy_is_reverified(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / 'original.h5'
            source.write_bytes(b'original')
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            retained = retain_recording(project, source, expected)
            retained.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                retain_recording(project, retained, expected)


if __name__=='__main__':unittest.main()
