"""Managed-file reuse and deletion fences using owned disposable byte fixtures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch
import unittest
import uuid

from disco.projects.recording_files import retain_recording, managed_recording_owner
from disco.projects.recording_registry import read_registry, dependents, recording_location, relocated_library_recording
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
        self.assertTrue(first.is_relative_to(self.a.parent / 'recordings'))
        self.assertEqual(list(self.b.glob('raw-uploads/**/*.h5')), [])
        self.assertEqual(first.read_bytes(), self.source.read_bytes())
        self.assertEqual(len(read_registry(self.a)['recordings'][self.sha]['consumers']), 2)
        self.assertEqual(managed_recording_owner(self.b, first)['path'], str(self.a.parent / 'recordings'))
        self.assertEqual(read_registry(self.a)['version'], 2)
        self.assertIsNone(managed_recording_owner(self.a, self.source))
        self.assertTrue(self.source.exists(), 'Do not delete an unowned original')

    def test_repeat_import_into_one_project_does_not_copy_again(self):
        first = retain_recording(self.a, self.source, self.sha)
        self.assertEqual(retain_recording(self.a, self.source, self.sha), first)
        self.assertEqual(len(list((self.a.parent / 'recordings').glob('**/*.h5'))), 1)
        self.assertEqual(len(read_registry(self.a)['recordings'][self.sha]['consumers']), 1)

    def test_concurrent_projects_share_one_retained_copy(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda project: retain_recording(project, self.source, self.sha), [self.a, self.b]))
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(list((self.root / 'workspace').glob('recordings/**/*.h5'))), 1)

    def test_deletion_preserves_owner_file_with_other_project_reference(self):
        retained = retain_recording(self.a, self.source, self.sha)
        self.assertIsNone(managed_recording(self.a, retained), 'Library bytes survive even the last project detaching')
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
        retained = self.a / 'raw-uploads' / 'legacy.h5'
        retained.parent.mkdir()
        retained.write_bytes(self.source.read_bytes())
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
        retained = retain_recording(self.a, self.source, self.sha)
        self.assertTrue(retained.is_relative_to(self.a.parent / 'recordings'))
        self.assertTrue(self.source.exists())

    def test_removing_original_and_first_project_keeps_other_project_recording(self):
        retained = retain_recording(self.a, self.source, self.sha)
        self.assertEqual(retain_recording(self.b, self.source, self.sha), retained)
        expected = self.source.read_bytes()
        self.source.unlink()
        shutil.rmtree(self.a)
        self.assertEqual(retained.read_bytes(), expected)
        self.assertEqual(retain_recording(self.b, retained, self.sha), retained)
        self.assertEqual(managed_recording_owner(self.b, retained)['kind'], 'library')

    def test_registry_write_failure_recovers_published_copy_without_duplication(self):
        with patch('disco.projects.recording_registry.register_reference', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                retain_recording(self.a, self.source, self.sha)
        copies = list((self.a.parent / 'recordings').glob('**/*.h5'))
        self.assertEqual(len(copies), 1)
        self.assertEqual(retain_recording(self.b, self.source, self.sha), copies[0])
        self.assertEqual(len(list((self.a.parent / 'recordings').glob('**/*.h5'))), 1)

    def test_failed_copy_does_not_publish_or_register_partial_bytes(self):
        with self.assertRaisesRegex(ValueError, 'changed while copying'):
            retain_recording(self.a, self.source, '0' * 64)
        self.assertEqual(read_registry(self.a)['recordings'], {})
        self.assertEqual(list((self.a.parent / 'recordings').glob('**/*.h5')), [])
        self.assertEqual(list((self.a.parent / 'recordings').glob('.incoming-*')), [])
        self.assertTrue(self.source.exists())

    def test_unowned_or_symlinked_library_is_not_adopted(self):
        library = self.a.parent / 'recordings'
        library.mkdir()
        (library / 'unrelated.h5').write_bytes(b'keep this')
        with self.assertRaisesRegex(ValueError, 'not a Disco library'):
            retain_recording(self.a, self.source, self.sha)
        self.assertEqual((library / 'unrelated.h5').read_bytes(), b'keep this')
        shutil.rmtree(library)
        library.symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            retain_recording(self.a, self.source, self.sha)

    def test_symlinked_published_file_cannot_be_reused(self):
        retained = retain_recording(self.a, self.source, self.sha)
        retained.unlink()
        retained.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'escapes workspace|owner identity changed'):
            retain_recording(self.b, self.source, self.sha)

    def test_library_identity_change_refuses_reuse_even_for_identical_bytes(self):
        retained = retain_recording(self.a, self.source, self.sha)
        marker = self.a.parent / 'recordings' / '.disco-library.json'
        value = json.loads(marker.read_text())
        value['library_uuid'] = str(uuid.uuid4())
        marker.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'owner identity changed'):
            retain_recording(self.b, self.source, self.sha)
        self.assertTrue(retained.exists())

    def test_version_one_registry_and_legacy_deletion_protection_are_preserved(self):
        retained = self.a / 'raw-uploads' / 'legacy.h5'
        retained.parent.mkdir()
        retained.write_bytes(self.source.read_bytes())
        identity = json.loads((self.a / 'project.json').read_text())['project_uuid']
        (self.a.parent / '.disco-recordings.json').write_text(json.dumps({
            'format': 'disco-managed-recordings', 'version': 1, 'recordings': {self.sha: {
                'path': str(retained.relative_to(self.a.parent)), 'owner_project_uuid': identity,
                'owner_project_directory': self.a.name, 'consumers': []}}}))
        self.assertEqual(managed_recording(self.a, retained), retained)
        self.assertEqual(retain_recording(self.b, self.source, self.sha), retained)
        self.assertIsNone(managed_recording(self.a, retained))
        self.source.write_bytes(b'new file')
        new_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        library = retain_recording(self.a, self.source, new_sha)
        self.assertTrue(library.is_relative_to(self.a.parent / 'recordings'))
        self.assertEqual(read_registry(self.a)['version'], 2)
        self.assertEqual(retain_recording(self.b, retained, self.sha), retained)

    def test_master_folder_move_keeps_relative_recording_identity(self):
        retained = retain_recording(self.a, self.source, self.sha)
        manifest = {'source_path': str(retained), 'source_sha256': self.sha,
                    'recording_location': recording_location(self.a, retained)}
        moved = self.root / 'moved-workspace'
        self.a.parent.rename(moved)
        relocated = relocated_library_recording(moved / 'A', manifest)
        self.assertEqual(relocated, moved / manifest['recording_location']['path'])
        self.assertEqual(relocated.read_bytes(), self.source.read_bytes())
        self.assertEqual(retain_recording(moved / 'B', self.source, self.sha), relocated)

    def test_relative_location_cannot_redirect_to_other_library_or_escape(self):
        retained = retain_recording(self.a, self.source, self.sha)
        location = recording_location(self.a, retained)
        manifest = {'source_sha256': self.sha, 'recording_location': dict(location, library_uuid=str(uuid.uuid4()))}
        self.assertIsNone(relocated_library_recording(self.a, manifest))
        manifest['recording_location'] = dict(location, path='../outside.h5')
        with self.assertRaisesRegex(ValueError, 'Invalid library recording location'):
            relocated_library_recording(self.a, manifest)


if __name__ == '__main__':
    unittest.main()
