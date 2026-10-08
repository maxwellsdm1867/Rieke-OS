"""Managed-file reuse and deletion fences using owned disposable byte fixtures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from disco.projects.recording_files import retain_recording, managed_recording_owner
from disco.projects.recording_registry import read_registry, dependents
from disco.projects.datastore_deletion import managed_recording


class SharedRecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.a, self.b = self.project('A'), self.project('B')
        self.source = self.root / 'Downloads' / 'recording.h5'
        self.source.parent.mkdir()
        self.source.write_bytes(b'owned fixture recording bytes')
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def project(self, name):
        path = self.root / 'workspace' / name
        path.mkdir(parents=True)
        (path / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1,
                                                       'project_uuid': str(uuid.uuid4()), 'name': name}))
        return path

    def test_external_source_retained_once_and_reused_across_projects(self):
        first = retain_recording(self.a, self.source, self.sha)
        second = retain_recording(self.b, self.source, self.sha)
        self.assertEqual(first, second)
        self.assertTrue(first.is_relative_to(self.a / 'raw-uploads'))
        self.assertEqual(list(self.b.glob('raw-uploads/**/*.h5')), [])
        self.assertEqual(first.read_bytes(), self.source.read_bytes())
        self.assertEqual(len(read_registry(self.a)['recordings'][self.sha]['consumers']), 2)
        self.assertEqual(managed_recording_owner(self.b, first)['path'], str(self.a))
        self.assertIsNone(managed_recording_owner(self.a, self.source))
        self.assertTrue(self.source.exists(), 'Do not delete an unowned original')

    def test_repeat_import_into_one_project_does_not_copy_again(self):
        first = retain_recording(self.a, self.source, self.sha)
        self.assertEqual(retain_recording(self.a, self.source, self.sha), first)
        self.assertEqual(len(list(self.a.glob('raw-uploads/**/*.h5'))), 1)
        self.assertEqual(len(read_registry(self.a)['recordings'][self.sha]['consumers']), 1)

    def test_concurrent_projects_share_one_retained_copy(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda project: retain_recording(project, self.source, self.sha), [self.a, self.b]))
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(list((self.root / 'workspace').glob('*/raw-uploads/**/*.h5'))), 1)

    def test_deletion_preserves_owner_file_with_other_project_reference(self):
        retained = retain_recording(self.a, self.source, self.sha)
        self.assertEqual(managed_recording(self.a, retained), retained)
        retain_recording(self.b, retained, self.sha)
        self.assertIsNone(managed_recording(self.a, retained))
        self.assertIsNone(managed_recording(self.b, retained))
        self.assertEqual(dependents(self.a, retained)[0]['project_directory'], 'B')
        self.assertTrue(retained.exists())

    def test_existing_import_manifest_is_discovered_without_copying_h5(self):
        managed = self.a / 'raw-uploads' / 'existing' / self.source.name
        managed.parent.mkdir(parents=True)
        managed.write_bytes(self.source.read_bytes())
        manifest = self.a / 'imports' / 'existing' / 'import-manifest.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'source_sha256': self.sha, 'source_path': str(managed)}))
        self.assertEqual(retain_recording(self.b, self.source, self.sha), managed)
        self.assertEqual(len(list((self.root / 'workspace').glob('*/raw-uploads/**/*.h5'))), 1)

    def test_changed_existing_copy_is_rejected(self):
        retained = retain_recording(self.a, self.source, self.sha)
        retained.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Managed recording changed'):
            retain_recording(self.b, self.source, self.sha)
        self.assertEqual(list(self.b.glob('raw-uploads/**/*.h5')), [])

    def test_import_manifest_protects_shared_file_when_registry_is_missing(self):
        retained = retain_recording(self.a, self.source, self.sha)
        manifest = self.b / 'imports' / 'shared' / 'import-manifest.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'source_sha256': self.sha, 'source_path': str(retained)}))
        (self.a.parent / '.disco-recordings.json').unlink()
        self.assertIsNone(managed_recording(self.a, retained))
        self.assertEqual(dependents(self.a, retained)[0]['project_directory'], 'B')

    def test_unreadable_sibling_manifest_refuses_file_deletion(self):
        retained = retain_recording(self.a, self.source, self.sha)
        manifest = self.b / 'imports' / 'unknown' / 'import-manifest.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{broken')
        with self.assertRaisesRegex(ValueError, 'Cannot verify recording references'):
            managed_recording(self.a, retained)
        self.assertTrue(retained.exists())

    def test_same_name_different_bytes_are_not_deduplicated(self):
        first = retain_recording(self.a, self.source, self.sha)
        self.source.write_bytes(b'a different recording')
        other_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        second = retain_recording(self.b, self.source, other_sha)
        self.assertNotEqual(first, second)
        self.assertEqual(second.read_bytes(), self.source.read_bytes())

    def test_symlinked_recording_storage_does_not_become_managed_ownership(self):
        (self.a / 'raw-uploads').symlink_to(self.source.parent, target_is_directory=True)
        self.assertIsNone(managed_recording_owner(self.b, self.a / 'raw-uploads' / self.source.name))
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            retain_recording(self.a, self.source, self.sha)


if __name__ == '__main__':
    unittest.main()
