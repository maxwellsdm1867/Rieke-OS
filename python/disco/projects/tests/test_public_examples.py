"""Isolated public examples: stdlib, owned temporary bytes, no scientific imports.

Run this file directly with python3 -I -B. The sole upstream recording_workspace
stand-in rejects JSON writes; the real storage/retention modules are imported.
This is filesystem-copy/admission evidence, never native or scientific evidence.
"""
import builtins
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest

if __name__ != '__main__':
    class IsolatedPublicExamples(unittest.TestCase):
        def test_public_examples_in_isolated_interpreter(self):
            # The import guard and recording stand-in belong only to the child.
            # Discovery must not replace another test's process-wide imports.
            result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve())],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    _original_import = builtins.__import__
    _forbidden = {'datajoint', 'h5py', 'numpy', 'scipy', 'flask', 'workspace_native_mysql',
                  'workspace_service', 'workspace_api', 'workspace_portability'}

    def _guarded_import(name, *args, **kwargs):
        if name.split('.')[0] in _forbidden:
            raise AssertionError('Scientific/native import forbidden in this example: ' + name)
        return _original_import(name, *args, **kwargs)

    builtins.__import__ = _guarded_import
    upstream = types.ModuleType('recording_workspace')
    def unexpected_write(*args, **kwargs):
        raise AssertionError('Retention/admission must not write scientific JSON')
    upstream.write_json = unexpected_write
    sys.modules['recording_workspace'] = upstream

    from disco.projects.recording_files import retain_recording, recording_display_name
    from disco.projects.project_database import ensure_project_database


    class RetentionExamples(unittest.TestCase):
        def test_verified_copy_keeps_name_and_reuse_rechecks_bytes(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                source = root / 'opaque-recording.bin'
                source.write_bytes(b'opaque fixture, not scientific data')
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                project = root / 'project'
                result = retain_recording(project, source, digest)
                self.assertTrue(result.is_relative_to(project / 'raw-uploads'))
                self.assertEqual(result.name, source.name)
                self.assertEqual(result.read_bytes(), source.read_bytes())
                self.assertEqual(retain_recording(project, result, digest), result)
                result.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'changed before import'):
                    retain_recording(project, result, digest)
                self.assertTrue(source.exists(), 'retention does not delete original')

        def test_failed_copy_removes_only_its_new_destination(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                source = root / 'source.bin'; source.write_bytes(b'opaque bytes')
                managed = root / 'project/raw-uploads'; managed.mkdir(parents=True)
                existing = managed / 'existing'; existing.mkdir()
                with self.assertRaisesRegex(ValueError, 'changed while copying'):
                    retain_recording(root / 'project', source, '0' * 64)
                self.assertEqual(list(managed.iterdir()), [existing])
                self.assertEqual(source.read_bytes(), b'opaque bytes')

        def test_redirected_managed_directory_refuses_before_copy(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(); project = root / 'project'; project.mkdir()
                external = root / 'external'; external.mkdir()
                (project / 'raw-uploads').symlink_to(external, target_is_directory=True)
                source = root / 'source.bin'; source.write_bytes(b'opaque bytes')
                with self.assertRaisesRegex(ValueError, 'symbolic links'):
                    retain_recording(project, source, hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(list(external.iterdir()), [])

        def test_display_identity_does_not_follow_relocated_locator(self):
            self.assertEqual(recording_display_name({'source_filename':'recording.h5',
                                                    'source_path':'/relocated/locator.bin'}), 'recording.h5')
            self.assertEqual(recording_display_name({'source_filename':'../unsafe',
                                                    'source_path':'/relocated/locator.bin'}), 'locator.bin')


    class DatabaseAdmissionExamples(unittest.TestCase):
        def test_pending_restore_refuses_before_descriptor_or_process_access(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(); (root / '.portable-restore.pending').touch()
                with self.assertRaisesRegex(ValueError, 'restore is incomplete'):
                    ensure_project_database(root)
                self.assertEqual([p.name for p in root.iterdir()], ['.portable-restore.pending'])

        def test_wrong_project_identity_refuses_before_provider_access(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                (root / 'project.json').write_text(json.dumps({'project_uuid':'project-a'}))
                (root / 'catalog.json').write_text(json.dumps({'project_uuid':'project-b'}))
                with self.assertRaisesRegex(ValueError, 'identities disagree'):
                    ensure_project_database(root)


    if __name__ == '__main__':
        unittest.main()
