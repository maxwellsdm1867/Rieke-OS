"""Read a Disco linked SQLite export without installing Disco or DataJoint.

Metadata and SQL use the Python standard library. Recorded sample reads also
require numpy and h5py. Run this file with --help for command-line examples.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

FORMAT = 'recording-workspace-linked-sqlite'
VERSION = 1
DETAIL_KEYS = ('parameters', 'properties', 'attributes', 'metadata')
SEALED_TABLES = ('sources', 'cells', 'epoch_groups', 'epoch_blocks', 'epochs', 'epoch_records',
                 'streams', 'epoch_tags', 'shared_annotations', 'annotation_revisions',
                 'analysis_groups', 'analysis_group_epochs', 'example_queries')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def signature(path):
    stat = Path(path).stat()
    return (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def database_seal(connection):
    """Detect changes to frozen SQL data, without fetching any external files."""
    result = hashlib.sha256()
    for table in SEALED_TABLES:
        result.update(table.encode() + b'\n')
        columns = len(connection.execute('PRAGMA table_info(' + table + ')').fetchall())
        order = ','.join(str(index + 1) for index in range(columns))
        for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY ' + order):
            result.update(canonical(list(row)).encode() + b'\n')
    return result.hexdigest()


def metadata_records(document):
    """Preserve recorded values and shared ancestors without interpretation."""
    seen = set()
    for animal in document['animals']:
        for preparation in animal['preparations']:
            for cell in preparation['cells']:
                for group in cell['epoch_groups']:
                    for block in group['epoch_blocks']:
                        for epoch in block['epochs']:
                            identity = epoch['uuid']
                            if identity in seen:
                                raise ValueError('Duplicate epoch UUID in referenced metadata')
                            seen.add(identity)
                            yield identity, {
                                **{key: epoch.get(key, {}) for key in DETAIL_KEYS[:3]},
                                'metadata': {
                                    'cell': {key: value for key, value in cell.items() if key != 'epoch_groups'},
                                    'group': {key: value for key, value in group.items() if key != 'epoch_blocks'},
                                    'block': {key: value for key, value in block.items() if key != 'epochs'},
                                    'epoch': epoch,
                                },
                            }


def fingerprint(details, source_sha256, version):
    if version == 2:
        value = {'epoch': details, 'source_sha256': source_sha256}
    elif version == 1:
        value = details['metadata']['epoch']
    else:
        raise ValueError('Unsupported metadata fingerprint version')
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verified_metadata(path, expected_sha256):
    path = Path(path).resolve(strict=True)
    before = signature(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256 or signature(path) != before:
        raise ValueError('Referenced metadata changed; restore the original file or make a new export')
    return dict(metadata_records(json.loads(raw))), before


class LinkedExport:
    """Read-only SQL and lazy, checked metadata/H5 access to frozen membership.

    project_root relocates the exporting project. workspace_root relocates its
    parent and sibling projects. file_map maps original file paths to explicit
    replacements; replacements must have identical checksums. No source is
    searched by filename and no current project query is rerun.
    """
    def __init__(self, database, *, project_root=None, workspace_root=None, file_map=None,
                 expected_sha256=None):
        self.path = Path(database).expanduser().resolve(strict=True)
        self._database_signature = signature(self.path)
        if expected_sha256 and digest(self.path) != expected_sha256:
            raise ValueError('SQLite export checksum mismatch')
        self.connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        self.connection.row_factory = sqlite3.Row
        self._metadata_cache, self._h5_cache = OrderedDict(), {}
        self.project_root = Path(project_root).expanduser().resolve() if project_root else None
        self.workspace_root = Path(workspace_root).expanduser().resolve() if workspace_root else None
        self.file_map = dict(file_map or {})
        try:
            self.connection.execute('PRAGMA query_only=ON')
            self.connection.execute('PRAGMA trusted_schema=OFF')
            rows = self.connection.execute('SELECT * FROM export_info').fetchall()
            if len(rows) != 1 or rows[0]['format'] != FORMAT or rows[0]['version'] != VERSION:
                raise ValueError('Unsupported linked SQLite export')
            self.info = dict(rows[0])
            if database_seal(self.connection) != self.info['content_sha256']:
                raise ValueError('Frozen SQLite tables changed after export')
            self.recipe = json.loads(self.info['recipe_json'])
            self._verify_recipe(self.recipe)
            self._verify_recipe(self.recipe['query_snapshot'])
            snapshot = self.recipe['query_snapshot']
            if any(snapshot.get(key) != self.recipe.get(key) for key in ('project_uuid', 'protocol_uuid', 'catalog_ref', 'query_sha256')):
                raise ValueError('Recipe and frozen query scopes disagree')
            if self.recipe['export_uuid'] != self.info['export_uuid']:
                raise ValueError('Export identity mismatch')
            self.members = {row['uuid']: row for row in self.recipe['epochs']}
            if len(self.members) != len(self.recipe['epochs']):
                raise ValueError('Duplicate frozen export member')
            query_members = {row['uuid']: row for row in snapshot['epochs']}
            if any(query_members.get(key) != member for key, member in self.members.items()):
                raise ValueError('Export members differ from the frozen query')
            actual = {row['epoch_uuid']: row['metadata_fingerprint'] for row in
                      self.connection.execute('SELECT epoch_uuid,metadata_fingerprint FROM epochs')}
            if actual != {key: value['metadata_hash'] for key, value in self.members.items()}:
                raise ValueError('SQLite membership differs from frozen recipe')
            self.sources = {row['source_sha256']: dict(row) for row in self.connection.execute('SELECT * FROM sources')}
            self._ready()
            self.connection.create_function('epoch_metadata', 1, lambda key: canonical(self.record(key)['metadata']))
            self.connection.create_function('epoch_parameters', 1, lambda key: canonical(self.record(key)['parameters']))
            def authorize(action, first, second, database, trigger):
                if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}:
                    return sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_PRAGMA and first.lower() in {
                        'table_info', 'table_xinfo', 'index_list', 'index_info', 'foreign_key_list'}:
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            self.connection.set_authorizer(authorize)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _verify_recipe(value):
        # The recipe seal uses the application's ASCII canonical JSON contract.
        body = {key: item for key, item in value.items() if key != 'content_sha256'}
        raw = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if hashlib.sha256(raw).hexdigest() != value.get('content_sha256'):
            raise ValueError('Frozen recipe checksum mismatch')

    def _ready(self):
        if self.connection is None:
            raise ValueError('Linked export reader is closed')
        if signature(self.path) != self._database_signature:
            raise ValueError('SQLite export changed during the reader session')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self._metadata_cache.clear()
        self._h5_cache.clear()

    def _path(self, source, kind):
        original = source[kind + '_path']
        if original in self.file_map:
            return Path(self.file_map[original]).expanduser().resolve(strict=True)
        relative = source[kind + '_project_relative']
        workspace_relative = source[kind + '_workspace_relative']
        if self.project_root is not None and relative is not None:
            root, part = self.project_root, relative
        elif self.workspace_root is not None and workspace_relative is not None:
            root, part = self.workspace_root, workspace_relative
        else:
            return Path(original).expanduser().resolve(strict=True)
        candidate = (root / part).resolve(strict=True)
        if not candidate.is_relative_to(root):
            raise ValueError('Relocated source escapes the supplied root')
        return candidate

    def query(self, sql, parameters=()):
        """Execute read-only SQL. Lazy metadata functions are available here."""
        self._ready()
        rows = [dict(row) for row in self.connection.execute(sql, parameters)]
        self._ready()
        return rows

    def describe(self):
        self._ready()
        counts = {name: self.connection.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                  for name in ('epochs', 'cells', 'epoch_groups', 'epoch_blocks', 'streams', 'analysis_groups')}
        return {'format': FORMAT, 'export_uuid': self.info['export_uuid'],
                'project_uuid': self.info['project_uuid'], 'counts': counts,
                'split_order': self.recipe.get('options', {}).get('split_order', ''),
                'source_files': list(self.sources.values()), 'usage': 'Metadata and H5 remain in managed project folders.'}

    def record(self, epoch_uuid):
        self._ready()
        row = self.connection.execute('SELECT * FROM epoch_records WHERE epoch_uuid=?', (epoch_uuid,)).fetchone()
        if row is None or epoch_uuid not in self.members:
            raise ValueError('Epoch is not part of this frozen export')
        if hashlib.sha256(row['record_json'].encode()).hexdigest() != row['record_sha256']:
            raise ValueError('Frozen epoch reference checksum mismatch')
        record = json.loads(row['record_json'])
        if record['epoch_uuid'] != epoch_uuid:
            raise ValueError('Epoch reference identity mismatch')
        source = self.sources[record['source_sha256']]
        if (record['source_sha256'] not in self.recipe['source_revisions'] or
                record.get('source_reference') != {'sha256': record['source_sha256'], 'path': source['source_path']}):
            raise ValueError('Recording reference differs from the frozen source')
        path = self._path(source, 'metadata')
        key = (str(path), source['metadata_sha256'])
        if key not in self._metadata_cache:
            self._metadata_cache[key] = verified_metadata(path, source['metadata_sha256'])
            if len(self._metadata_cache) > 2:
                self._metadata_cache.popitem(last=False)
        details, before = self._metadata_cache[key]
        self._metadata_cache.move_to_end(key)
        if signature(path) != before:
            raise ValueError('Referenced metadata changed during the reader session')
        detail = details.get(epoch_uuid)
        version = self.recipe['query_snapshot'].get('metadata_fingerprint_version', 1)
        if detail is None or fingerprint(detail, record['source_sha256'], version) != self.members[epoch_uuid]['metadata_hash']:
            raise ValueError('Referenced epoch metadata differs from frozen export')
        for level, column in (('cell', 'cell_uuid'), ('group', 'group_uuid'), ('block', 'block_uuid'), ('epoch', 'epoch_uuid')):
            if detail['metadata'][level].get('uuid') != record[column]:
                raise ValueError('Referenced hierarchy differs from frozen export')
        self._ready()
        return {**record, **copy.deepcopy(detail)}

    def read_trace(self, epoch_uuid, stream_uuid, *, start=0, count=20000):
        """Read original response samples, not generated stimuli or downsampling."""
        import h5py
        import numpy as np
        record = self.record(epoch_uuid)
        stream = next((item for item in record['streams'] if item['uuid'] == stream_uuid), None)
        if stream is None or stream['kind'] != 'responses':
            raise ValueError('Choose an exported recorded response stream')
        total = stream['sample_count']
        if type(start) is not int or type(count) is not int or not 0 <= start < total or not 1 <= count <= 20000:
            raise ValueError('Choose a valid sample start and count from 1 to 20000')
        source = self.sources[record['source_sha256']]
        path = self._path(source, 'source')
        before = signature(path)
        key = (str(path), record['source_sha256'])
        if key in self._h5_cache and self._h5_cache[key] != before:
            raise ValueError('H5 changed during the reader session')
        if key not in self._h5_cache:
            if digest(path) != record['source_sha256'] or signature(path) != before:
                raise ValueError('H5 checksum differs from the exported recording')
            self._h5_cache[key] = before
        def text(value):
            return value.decode() if isinstance(value, bytes) else str(value)
        with h5py.File(path, 'r') as h5:
            obj = h5[stream['h5_path']]
            if (str(uuid.UUID(text(obj.attrs['uuid']))) != stream_uuid or
                    str(uuid.UUID(text(obj.parent.parent.attrs['uuid']))) != epoch_uuid or
                    str(uuid.UUID(text(obj.parent.parent.parent.parent.attrs['uuid']))) != record['block_uuid']):
                raise ValueError('H5 response identity differs from the exported stream')
            data = obj['data']
            rate = stream['sample_rate']
            if (len(data) != total or float(obj.attrs['sampleRate']) != rate or
                    stream['sample_rate_units'] != 'Hz' or not rate or rate <= 0 or
                    not data.dtype.names or not {'quantity', 'units'} <= set(data.dtype.names)):
                raise ValueError('H5 response representation differs from exported metadata')
            if stream.get('data_path') and data.name != stream['data_path']:
                raise ValueError('H5 data path differs from exported stream')
            end = min(total, start + count)
            samples = data[start:end]
            if any(text(value) != stream['units'] for value in samples['units']):
                raise ValueError('H5 response units changed within the requested window')
            values = np.asarray(samples['quantity'], dtype=float)
            result = {'epoch_uuid': epoch_uuid, 'stream_uuid': stream_uuid, 'start': start,
                      'count': len(values), 'sample_rate': rate, 'units': stream['units'],
                      'time_seconds': (np.arange(start, end) / rate).tolist(),
                      'values': [float(value) if np.isfinite(value) else None for value in values]}
        if signature(path) != before:
            raise ValueError('H5 changed while reading recorded samples')
        self._ready()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--file-map', type=Path, help='JSON mapping original paths to relocated files')
    parser.add_argument('--sql', help='Read-only SQL; epoch_metadata/epoch_parameters functions are available')
    parser.add_argument('--epoch', help='Return complete metadata for this exported epoch UUID')
    parser.add_argument('--stream', help='With --epoch, read a response stream UUID')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=20000)
    args = parser.parse_args()
    if args.stream and not args.epoch:
        parser.error('--stream requires --epoch')
    try:
        mapping = json.loads(args.file_map.read_text()) if args.file_map else None
        with LinkedExport(args.database, project_root=args.project_root, workspace_root=args.workspace_root, file_map=mapping) as export:
            if args.sql:
                result = export.query(args.sql)
            elif args.stream:
                result = export.read_trace(args.epoch, args.stream, start=args.start, count=args.count)
            elif args.epoch:
                result = export.record(args.epoch)
            else:
                result = export.describe()
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, sqlite3.Error, KeyError, ImportError) as error:
        parser.exit(1, 'Linked export read failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
