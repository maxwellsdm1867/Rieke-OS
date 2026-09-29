"""Standalone SQLite consumer uses the same checked trace path as the UI."""
import shutil
import os
import json
import sqlite3
import unittest
from unittest.mock import patch
import h5py
import numpy as np

from recording_workspace import digest
from query_workspace_export import ExportReader, describe_export, read_export_trace
from workspace_sqlite import build_sqlite_export
if __package__:
    from . import test_workspace_sqlite as sqlite_tests
else:
    import test_workspace_sqlite as sqlite_tests


class ExportReaderTests(unittest.TestCase):
    def setUp(self):
        self.case = sqlite_tests.SQLiteExportTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service = self.case.service
        self.raw = self.service.project_dir / 'fixture.h5'
        with h5py.File(self.raw, 'w') as file:
            for index, key in enumerate(self.service.ids):
                stream = self.service.rows[key]['streams'][0]
                group = file.create_group(stream['h5_path'])
                group.attrs['uuid'] = stream['uuid']
                group.attrs['sampleRate'] = stream['sample_rate']
                group.parent.parent.attrs['uuid'] = key
                values = np.zeros(200, dtype=[('quantity', 'f8'), ('units', 'S8')])
                values['quantity'] = np.arange(200) + index * 1000
                values['units'] = b'pA'
                group.create_dataset('data', data=values)
        source = self.service.sources[0]
        old_sha = source['source_sha256']
        source['source_sha256'] = digest(self.raw)
        self.service.manifests[source['source_sha256']] = self.service.manifests.pop(old_sha)
        for row in self.service.rows.values():
            row['source_sha256'] = source['source_sha256']
        self.service.protocols[self.service.protocol_id]['result']['source_revisions'] = [source['source_sha256']]
        self.case.fingerprint()
        self.package = self.case.package_for(self.service.ids)
        self.path = self.case.path
        build_sqlite_export(self.package, self.path)
        self.epoch = self.service.ids[0]
        self.stream = self.service.rows[self.epoch]['streams'][0]['uuid']

    def test_bounded_full_rate_samples_work_without_datajoint(self):
        with patch('recording_workspace.connect', side_effect=AssertionError('No catalog connection')):
            result = read_export_trace(self.path, self.epoch, self.stream, start=3, count=5)
            self.assertEqual(result['values'], [3, 4, 5, 6, 7])
            self.assertEqual(result['sample_rate'], 10000)
            self.assertEqual(result['units'], 'pA')
            self.assertFalse(result['decimated'])
            self.assertEqual(describe_export(self.path)['counts']['epochs'], 2)

    def test_relocated_source_must_have_identical_bytes(self):
        relocated = self.raw.with_name('relocated.h5')
        shutil.copyfile(self.raw, relocated)
        self.assertEqual(read_export_trace(self.path, self.epoch, self.stream, source_file=relocated, count=1)['values'], [0])
        with h5py.File(relocated, 'a') as file:
            file.attrs['changed'] = 'unexpected'
        with self.assertRaisesRegex(ValueError, 'checksum differs'):
            read_export_trace(self.path, self.epoch, self.stream, source_file=relocated, count=1)

    def test_bad_identity_window_and_export_hash_are_rejected(self):
        other_stream = self.service.rows[self.service.ids[1]]['streams'][0]['uuid']
        with self.assertRaisesRegex(ValueError, 'Choose an exported'):
            read_export_trace(self.path, self.epoch, other_stream)
        with self.assertRaisesRegex(ValueError, 'Invalid sample window'):
            read_export_trace(self.path, self.epoch, self.stream, count=100001)
        with self.assertRaisesRegex(ValueError, 'artifact checksum'):
            describe_export(self.path, '0' * 64)

    def test_session_reuses_source_checksum_and_frozen_record_across_windows(self):
        from workspace_sqlite import load_frozen_record
        with patch('query_workspace_export.digest', wraps=digest) as checksum, \
             patch('workspace_sqlite.load_frozen_record', wraps=load_frozen_record) as decode, \
             patch('recording_workspace.connect', side_effect=AssertionError('No catalog connection')):
            with ExportReader(self.path) as reader:
                for start in (0, 10, 20):
                    self.assertEqual(reader.read_trace(self.epoch, self.stream, start=start, count=2)['values'], [start,start+1])
                other = self.service.ids[1]
                other_stream = self.service.rows[other]['streams'][0]['uuid']
                self.assertEqual(reader.read_trace(other, other_stream, count=1)['values'], [1000])
                self.assertEqual(checksum.call_count, 1)
                self.assertEqual(decode.call_count, 2)
            with self.assertRaisesRegex(ValueError,'closed'):
                reader.read_trace(self.epoch,self.stream,count=1)

    def test_modified_source_invalidates_session_without_silent_reverification(self):
        with patch('query_workspace_export.digest', wraps=digest) as checksum, ExportReader(self.path) as reader:
            reader.read_trace(self.epoch,self.stream,count=1)
            with h5py.File(self.raw,'a') as file:
                file.attrs['changed']='changed during session'
            with self.assertRaisesRegex(ValueError,'changed during export reader session'):
                reader.read_trace(self.epoch,self.stream,count=1)
            self.assertEqual(checksum.call_count,1)
        with self.assertRaisesRegex(ValueError,'checksum differs'):
            read_export_trace(self.path,self.epoch,self.stream,count=1)

    def test_database_change_and_source_change_during_checksum_are_rejected(self):
        with ExportReader(self.path) as reader:
            stamp=self.path.stat()
            os.utime(self.path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000))
            with self.assertRaisesRegex(ValueError,'SQLite export changed'):
                reader.describe()
        def modified_digest(path):
            result=digest(path)
            stamp=path.stat()
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000))
            return result
        with patch('query_workspace_export.digest',side_effect=modified_digest), ExportReader(self.path) as reader:
            with self.assertRaisesRegex(ValueError,'changed during checksum'):
                reader.read_trace(self.epoch,self.stream,count=1)

    def test_stimulus_is_metadata_only_and_invalid_window_never_hashes_source(self):
        stimulus=self.service.rows[self.epoch]['streams'][1]['uuid']
        with patch('query_workspace_export.digest',side_effect=AssertionError('Do not hash invalid requests')), ExportReader(self.path) as reader:
            with self.assertRaisesRegex(ValueError,'recorded response'):
                reader.read_trace(self.epoch,stimulus,count=1)
            with self.assertRaisesRegex(ValueError,'Invalid sample window'):
                reader.read_trace(self.epoch,self.stream,count=100001)

    def test_legacy_v1_schema_reads_and_describes_only_present_tables(self):
        # Build a minimal genuine v1 projection independently of v2 encoding.
        legacy=self.path.with_name('legacy.sqlite')
        with sqlite3.connect(self.path) as current, sqlite3.connect(legacy) as db:
            current.row_factory=sqlite3.Row
            metadata=dict(current.execute('SELECT * FROM export_metadata').fetchone())
            metadata['schema_version']=1
            db.execute('CREATE TABLE export_metadata ('+','.join('"'+key+'"' for key in metadata)+')')
            db.execute('INSERT INTO export_metadata VALUES ('+','.join('?' for _ in metadata)+')',list(metadata.values()))
            db.execute('CREATE TABLE epochs (epoch_uuid TEXT PRIMARY KEY,record_json TEXT)')
            db.executemany('INSERT INTO epochs VALUES (?,?)',[(row['epoch_uuid'],json.dumps(row)) for row in self.package['epochs']])
            stream_schema=current.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='streams'").fetchone()[0]
            db.execute(stream_schema)
            rows=current.execute('SELECT * FROM streams').fetchall()
            db.executemany('INSERT INTO streams VALUES ('+','.join('?' for _ in rows[0])+')',[tuple(row) for row in rows])
            db.execute('CREATE TABLE epoch_sources(epoch_uuid TEXT,source_sha256 TEXT,source_path TEXT)')
            db.executemany('INSERT INTO epoch_sources VALUES (?,?,?)',[(row['epoch_uuid'],row['source_sha256'],row['source_reference']['path']) for row in self.package['epochs']])
            db.execute('CREATE VIEW epoch_overview AS SELECT * FROM epoch_sources')
        with ExportReader(legacy) as reader:
            self.assertEqual(reader.describe()['schema_version'],1)
            self.assertNotIn('frozen_records',reader.describe()['counts'])
            self.assertEqual(reader.read_trace(self.epoch,self.stream,start=7,count=2)['values'],[7,8])

    def test_stream_data_path_and_rate_units_must_match_frozen_record(self):
        for column,value in [('data_path','/wrong/data'),('sample_rate_units','kHz')]:
            changed=self.path.with_name(column+'.sqlite')
            shutil.copyfile(self.path,changed)
            with sqlite3.connect(changed) as db:
                db.execute('DROP TRIGGER freeze_streams_update')
                db.execute('UPDATE streams SET '+column+'=? WHERE stream_uuid=?',(value,self.stream))
            with self.subTest(column=column),self.assertRaisesRegex(ValueError,'Stream columns disagree'):
                read_export_trace(changed,self.epoch,self.stream,count=1)
