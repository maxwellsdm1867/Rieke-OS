"""Byte-identity preflight tests; arbitrary fixture bytes need no H5 parser."""
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import workspace_import_check as check


class ImportCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def registration(self, path, contents, **extra):
        identity = hashlib.sha256(contents).hexdigest()
        return {'source_sha256': identity, 'project_uuid': 'project-fixture',
                'experiment_uuid': 'experiment-fixture', 'experiment_id': 1,
                'manifest': {'source_path': str(path), 'source_sha256': identity,
                             'source_size': len(contents)}, **extra}

    def test_renamed_same_bytes_match_recorded_identity_without_reading_old_path(self):
        contents = b'unchanged source bytes\0' * 80
        source = self.root / 'renamed.h5'
        source.write_bytes(contents)
        row = self.registration(self.root / 'unavailable' / 'old-name.h5', contents)
        original = copy.deepcopy(row)
        with patch.object(check, '_CHUNK_SIZE', 31):
            result = check.classify_source(source, [row])
        self.assertEqual(result['source_sha256'], row['source_sha256'])
        self.assertEqual(result['source_size'], len(contents))
        self.assertEqual(result['source_path'], str(source.resolve()))
        self.assertEqual(result['duplicate']['source_path'], row['manifest']['source_path'])
        self.assertEqual(result['duplicate']['experiment_uuid'], 'experiment-fixture')
        self.assertEqual(result['same_name_warnings'], [])
        self.assertEqual(row, original)
        self.assertEqual(source.read_bytes(), contents)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_same_name_different_bytes_is_a_warning_not_duplicate(self):
        source = self.root / 'recording.h5'
        source.write_bytes(b'new contents')
        old = self.registration(self.root / 'elsewhere' / 'RECORDING.H5', b'old contents')
        result = check.classify_source(source, [old])
        self.assertIsNone(result['duplicate'])
        self.assertEqual(len(result['same_name_warnings']), 1)
        self.assertEqual(result['same_name_warnings'][0]['source_sha256'], old['source_sha256'])
        self.assertEqual(source.read_bytes(), b'new contents')

    def test_different_name_and_different_bytes_is_new(self):
        source = self.root / 'new.h5'
        source.write_bytes(b'new')
        result = check.classify_source(source, [self.registration(self.root / 'old.h5', b'old')])
        self.assertIsNone(result['duplicate'])
        self.assertEqual(result['same_name_warnings'], [])

    def test_existing_frozen_or_archived_state_does_not_change_byte_identity(self):
        source = self.root / 'recording.h5'
        source.write_bytes(b'bytes')
        row = self.registration(source, b'bytes', state={'frozen': True, 'archived': True})
        original = copy.deepcopy(row)
        result = check.classify_source(source, [row])
        self.assertIsNotNone(result['duplicate'])
        self.assertEqual(row, original)
        self.assertNotIn('state', result['duplicate'])

    def test_detects_edit_during_stream_hash(self):
        source = self.root / 'changing.h5'
        source.write_bytes(b'original')
        hash_stream = check._hash_stream

        def edit_after_read(handle):
            result = hash_stream(handle)
            source.write_bytes(b'changed recording bytes')
            return result

        with patch.object(check, '_hash_stream', side_effect=edit_after_read):
            with self.assertRaisesRegex(check.SourceChangedError, 'changed during hashing'):
                check.classify_source(source, [])

    def test_detects_replacement_even_when_bytes_size_and_mtime_match(self):
        source = self.root / 'replaced.h5'
        source.write_bytes(b'original')
        before = source.stat()
        hash_stream = check._hash_stream

        def replace_after_read(handle):
            result = hash_stream(handle)
            replacement = self.root / 'replacement.h5'
            replacement.write_bytes(b'original')
            os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
            replacement.replace(source)
            return result

        with patch.object(check, '_hash_stream', side_effect=replace_after_read):
            with self.assertRaises(check.SourceChangedError):
                check.classify_source(source, [])

    def test_directory_and_missing_file_fail_without_hashing(self):
        with patch.object(check, '_hash_stream', side_effect=AssertionError('Must not hash')):
            with self.assertRaisesRegex(ValueError, 'regular recording file'):
                check.classify_source(self.root, [])
            with self.assertRaises(FileNotFoundError):
                check.classify_source(self.root / 'missing.h5', [])

    def test_malformed_registered_identity_fails_closed(self):
        source = self.root / 'recording.h5'
        source.write_bytes(b'bytes')
        row = self.registration(source, b'bytes')
        row['manifest']['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'manifest disagree'):
            check.classify_source(source, [row])

    def test_authoritative_catalog_callback_runs_after_hash_once(self):
        source = self.root / 'recording.h5'
        source.write_bytes(b'bytes')
        order = []
        hash_stream = check._hash_stream

        def tracked_hash(handle):
            result = hash_stream(handle)
            order.append('hashed')
            return result

        def fetch_registered():
            order.append('catalog')
            return [self.registration(self.root / 'already-imported.h5', b'bytes')]

        with patch.object(check, '_hash_stream', side_effect=tracked_hash):
            result = check.classify_source(source, fetch_registered)
        self.assertEqual(order, ['hashed', 'catalog'])
        self.assertIsNotNone(result['duplicate'])

    def test_change_during_catalog_lookup_fails_closed(self):
        source = self.root / 'recording.h5'
        source.write_bytes(b'bytes')

        def fetch_registered():
            source.write_bytes(b'changed while querying SQL')
            return []

        with self.assertRaisesRegex(check.SourceChangedError, 'catalog lookup'):
            check.classify_source(source, fetch_registered)


if __name__ == '__main__':
    unittest.main()
