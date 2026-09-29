"""Inspect a frozen SQLite export or read verified H5 samples, without DataJoint.

Examples:
  python query_workspace_export.py recordings.sqlite
  python query_workspace_export.py recordings.sqlite --epoch UUID --stream UUID --count 20
For repeated windows, use one Python session to verify each H5 source once:
  with ExportReader("recordings.sqlite") as reader:
      samples = reader.read_trace(epoch_uuid, stream_uuid, start=0, count=20)
Use sqlite3 directly for arbitrary analysis queries; example_queries documents joins.
A changed H5 or SQLite file ends the validity of the reader session.
"""
from __future__ import annotations
import argparse
from collections import OrderedDict
import json
from pathlib import Path
import sqlite3
import uuid

from recording_workspace import digest
from workspace_recipes import verify, member_map
from workspace_service import read_response_window, bounded_window
from workspace_sqlite import FORMAT, _fingerprint


def open_export(path, expected_sha256=None):
    path = Path(path).expanduser().resolve(strict=True)
    if expected_sha256 and digest(path) != expected_sha256:
        raise ValueError('Export artifact checksum differs from the saved revision')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = connection.execute('SELECT * FROM export_metadata').fetchall()
        if len(metadata) != 1 or metadata[0]['format'] != FORMAT or metadata[0]['schema_version'] not in {1, 2}:
            raise ValueError('Unsupported recording-workspace SQLite export')
        recipe = verify(json.loads(metadata[0]['recipe_json']))
        if recipe['content_sha256'] != metadata[0]['recipe_sha256'] or recipe['export_uuid'] != metadata[0]['export_uuid']:
            raise ValueError('Export recipe identity or checksum disagrees with the database')
        return connection, dict(metadata[0]), recipe
    except Exception:
        connection.close()
        raise


def _signature(path):
    stat = path.stat()
    return (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


class ExportReader:
    """Read-only session: verify each source once, retain bounded trace reads.

    A source/SQLite file change invalidates the session rather than silently
    accepting a new version. Start a new reader to explicitly re-verify files.
    This object owns a SQLite connection and is intended for one thread.
    Generated stimuli remain metadata-only; read_trace accepts responses only.
    """
    def __init__(self, path, expected_sha256=None):
        self.path = Path(path).expanduser().resolve(strict=True)
        before = _signature(self.path)
        self.connection, self.metadata, self.recipe = open_export(self.path, expected_sha256)
        try:
            if _signature(self.path) != before:
                raise ValueError('SQLite export changed while opening reader')
            self._database_signature = before
            self._sources, self._records = {}, OrderedDict()
            self._members = member_map(self.recipe)
            self._fingerprint_version = self.recipe['query_snapshot'].get('metadata_fingerprint_version', 1)
        except Exception:
            self.connection.close()
            self.connection = None
            raise

    def _ready(self):
        if self.connection is None:
            raise ValueError('Export reader is closed')
        if _signature(self.path) != self._database_signature:
            raise ValueError('SQLite export changed during reader session; reopen and verify it')

    def __enter__(self):
        self._ready()
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self._sources = {}
        self._records = {}

    def describe(self):
        self._ready()
        # Read only tables that exist in this version. Names are quoted as SQL
        # identifiers; no database-provided string is executed as SQL text.
        tables = [row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {table: self.connection.execute('SELECT count(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                  for table in tables}
        self._ready()
        return {'format': FORMAT, 'schema_version': self.metadata['schema_version'],
            'export_uuid': self.recipe['export_uuid'], 'protocol_uuid': self.recipe['protocol_uuid'],
            'query': self.recipe['query'], 'tree': self.recipe.get('options', {}).get('tree_view'),
            'counts': counts, 'compatibility': self.metadata['compatibility'], 'waveforms': self.metadata['waveforms']}

    def _record(self, epoch_uuid):
        if epoch_uuid not in self._records:
            from workspace_sqlite import load_frozen_record
            record = load_frozen_record(self.connection, epoch_uuid)
            member = self._members.get(epoch_uuid)
            if not member or record.get('epoch_uuid') != epoch_uuid or _fingerprint(record, self._fingerprint_version) != member['metadata_hash']:
                raise ValueError('Epoch metadata differs from the frozen query')
            self._records[epoch_uuid] = record
            if len(self._records) > 32:
                self._records.popitem(last=False)
        self._records.move_to_end(epoch_uuid)
        return self._records[epoch_uuid]

    def _verified_source(self, raw, identity):
        key = (identity, str(raw))
        signature = _signature(raw)
        if key in self._sources:
            if self._sources[key] != signature:
                raise ValueError('Source recording changed during export reader session; reopen and verify it')
            return signature
        if digest(raw) != identity:
            raise ValueError('Raw H5 checksum differs from the exported source revision')
        if _signature(raw) != signature:
            raise ValueError('Raw H5 changed during checksum verification')
        self._sources[key] = signature
        return signature

    def read_trace(self, epoch_uuid, stream_uuid, *, start=0, count=20000, source_file=None):
        self._ready()
        try:
            epoch_uuid, stream_uuid = str(uuid.UUID(epoch_uuid)), str(uuid.UUID(stream_uuid))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError('Epoch and stream identities must be UUIDs') from error
        stream = self.connection.execute('SELECT * FROM streams WHERE epoch_uuid=? AND stream_uuid=?',
                                         (epoch_uuid, stream_uuid)).fetchone()
        source = self.connection.execute('SELECT source_sha256,source_path FROM epoch_overview WHERE epoch_uuid=?',
                                         (epoch_uuid,)).fetchone()
        if stream is None or source is None or stream['kind'] != 'responses':
            raise ValueError('Choose an exported epoch and its recorded response stream')
        record = self._record(epoch_uuid)
        original = next((value for value in record['streams'] if value['uuid'] == stream_uuid), None)
        if not original or any(original.get(key) != stream[key] for key in
                              ('kind', 'device', 'h5_path', 'data_path', 'sample_rate', 'sample_rate_units', 'sample_count', 'units')):
            raise ValueError('Stream columns disagree with the frozen epoch record')
        reference = record.get('source_reference', {})
        if (source['source_sha256'] != record['source_sha256'] or
                reference.get('sha256') != source['source_sha256'] or reference.get('path') != source['source_path']):
            raise ValueError('Source identity or pointer differs from the frozen epoch record')
        if stream['sample_rate_units'] != 'Hz':
            raise ValueError('Response sample rate must be recorded in Hz')
        if stream['data_path'] and stream['data_path'] != stream['h5_path'].rstrip('/') + '/data':
            raise ValueError('Response data path disagrees with its H5 stream pointer')
        bounded_window(start, count, stream['sample_count'])
        raw = Path(source_file or source['source_path']).expanduser().resolve(strict=True)
        signature = self._verified_source(raw, source['source_sha256'])
        result = read_response_window(raw, signature,
            {'epoch_uuid': epoch_uuid, 'source_sha256': source['source_sha256']},
            {**dict(stream), 'uuid': stream_uuid}, start, count)
        self._ready()
        return result


def describe_export(path, expected_sha256=None):
    with ExportReader(path, expected_sha256) as reader:
        return reader.describe()


def read_export_trace(path, epoch_uuid, stream_uuid, *, start=0, count=20000, source_file=None, expected_sha256=None):
    with ExportReader(path, expected_sha256) as reader:
        return reader.read_trace(epoch_uuid, stream_uuid, start=start, count=count, source_file=source_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--epoch')
    parser.add_argument('--stream')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=20000)
    parser.add_argument('--source-file', type=Path, help='Relocated H5; must match original SHA-256')
    parser.add_argument('--expected-sha256', help='Optional saved database artifact hash')
    args = parser.parse_args()
    if bool(args.epoch) != bool(args.stream):
        parser.error('--epoch and --stream must be supplied together')
    try:
        result = read_export_trace(args.database, args.epoch, args.stream, start=args.start, count=args.count,
                                   source_file=args.source_file, expected_sha256=args.expected_sha256) if args.epoch else describe_export(args.database, args.expected_sha256)
    except (ValueError, OSError, sqlite3.DatabaseError, KeyError) as error:
        parser.exit(1, 'Export check failed: ' + str(error) + '\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
