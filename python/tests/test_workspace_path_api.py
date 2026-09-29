"""Path inputs must not depend on the server CWD or escape managed uploads."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import test_workspace_api as api_tests
else:
    import test_workspace_api as api_tests


class ImportPathTests(unittest.TestCase):
    def setUp(self):
        self.case = api_tests.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_relative_existing_file_rejected_before_queueing(self):
        root = Path(self.case.temp.name)
        (root / 'ambiguous.h5').write_bytes(b'Not parsed by this test')
        previous = Path.cwd()
        try:
            os.chdir(root)
            with patch('workspace_api.threading.Thread') as thread:
                response = self.case.client.post('/api/imports',
                    json={'source_path':'ambiguous.h5'}, headers=self.case.headers)
                self.assertEqual(response.status_code, 400, response.json)
                self.assertIn('absolute recording file path', response.json['error'])
                thread.assert_not_called()
        finally:
            os.chdir(previous)

    def test_upload_directory_symlink_rejected_without_external_write(self):
        with tempfile.TemporaryDirectory() as outside:
            uploads = Path(self.case.temp.name) / 'raw-uploads'
            if uploads.exists():
                uploads.rmdir()  # Fixture directory is empty.
            uploads.symlink_to(outside, target_is_directory=True)
            response = self.case.client.post('/api/imports',
                data={'file':(io.BytesIO(b'Unparsed fixture'), 'recording.h5')},
                content_type='multipart/form-data', headers=self.case.headers)
            self.assertEqual(response.status_code, 400, response.json)
            self.assertIn('symbolic links', response.json['error'])
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
