"""Disposable source projections with lossless, lazy ancestor reconstruction."""
from __future__ import annotations

import base64
from collections.abc import Mapping
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zlib

from workspace_recipes import checksum
from workspace_cache_lifecycle import CacheNamespace
from workspace_metadata_objects import Decoder, Encoder, KINDS, _identity, _uuid, canonical

VERSION = 2
_REQUIRED = {'rows', 'details', 'cells', 'source', 'fingerprints'}


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _ObjectRows:
    """Immutable compressed rows implementing the decoder's two read queries."""
    def __init__(self, objects):
        self.rows = {}
        identities = set()
        if not isinstance(objects, list):
            raise ValueError('Invalid source projection objects')
        for item in objects:
            if (not isinstance(item, dict) or set(item) != {'id', 'source_sha', 'kind', 'uuid', 'payload', 'sha256'}
                    or type(item['id']) is not int or item['id'] <= 0 or item['id'] in self.rows
                    or not isinstance(item['source_sha'], str) or not item['source_sha']
                    or not isinstance(item['kind'], str) or item['kind'] not in KINDS
                    or _uuid(item['uuid']) != item['uuid'] or item['uuid'] is None
                    or not isinstance(item['sha256'], str) or len(item['sha256']) != 64):
                raise ValueError('Invalid source projection object')
            identity = item['source_sha'], item['kind'], item['uuid']
            if identity in identities:
                raise ValueError('Duplicate source projection object identity')
            identities.add(identity)
            digest = bytes.fromhex(item['sha256'])
            if len(digest) != 32:
                raise ValueError('Invalid source projection object digest')
            payload = base64.b64decode(item['payload'], validate=True)
            self.rows[item['id']] = (*identity, payload, digest)

    def execute(self, query, parameters=()):
        if query == 'PRAGMA database_list':
            return _Cursor([(0, 'main', '')])
        if query == 'SELECT source_sha,kind,object_uuid,payload,sha256 FROM metadata_objects WHERE object_id=?':
            value = self.rows.get(parameters[0])
            return _Cursor([value] if value is not None else [])
        raise ValueError('Unsupported source projection object query')


class _ProjectionDetails(Mapping):
    def __init__(self, rows, documents, objects):
        if not isinstance(rows, dict) or not isinstance(documents, dict) or rows.keys() != documents.keys():
            raise ValueError('Source projection detail membership differs')
        self._objects = _ObjectRows(objects)
        self._documents = documents
        self._rows = {}
        self._decoder = Decoder()
        for identity, document in documents.items():
            row = rows[identity]
            if (not isinstance(row, dict) or not isinstance(document, dict)
                    or set(document) != {'version', 'inline', 'objects'}
                    or type(document['version']) is not int or document['version'] != 1
                    or not isinstance(document['inline'], dict) or not isinstance(document['objects'], dict)
                    or set(document['objects']) - set(KINDS)):
                raise ValueError('Invalid source projection detail')
            # Retain ownership independently of mutable rows returned to callers.
            self._rows[identity] = {name: row.get(name) for name in ('source_sha256', *KINDS.values())}
            metadata = document['inline'].get('metadata')
            for kind, number in document['objects'].items():
                if type(number) is not int or number <= 0 or not isinstance(metadata, dict) or kind in metadata:
                    raise ValueError('Invalid source projection ancestor reference')
                saved = self._objects.rows.get(number)
                if saved is None or tuple(saved[:3]) != _identity(row, kind):
                    raise ValueError('Source projection ancestor ownership differs')

    def __len__(self):
        return len(self._documents)

    def __iter__(self):
        return iter(self._documents)

    def __getitem__(self, identity):
        document = self._documents[identity]
        return self._decoder.decode(self._objects, self._rows[identity], zlib.compress(canonical(document)))

    def __deepcopy__(self, memo):
        return {identity: copy.deepcopy(self[identity], memo) for identity in self}


class ProjectionCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        if self.directory.is_symlink() or self.directory.parent.is_symlink():
            raise ValueError('Derived cache directories cannot be symbolic links')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.namespace = CacheNamespace(self.directory, 'projections')

    def _path(self, key):
        return self.directory / (checksum({'version': VERSION, 'key': key}) + '.json.zlib')

    def read(self, key):
        with self.namespace.writer(self._path(key).name):
            return self._read(key)

    def _read(self, key):
        path = self._path(key)
        seal = path.with_suffix('.sha256')
        with self.namespace.lease(path.name, reclaim=False):
            if not path.exists() or not seal.exists() or path.is_symlink() or seal.is_symlink():
                return None
            try:
                blob = path.read_bytes()
                if hashlib.sha256(blob).hexdigest() != seal.read_text().strip():
                    return None
                document = json.loads(zlib.decompress(blob))
                if (not isinstance(document, dict) or type(document.get('version')) is not int
                        or document['version'] != VERSION or document.get('key_hash') != checksum(key)):
                    return None
                projection = document['projection']
                if not isinstance(projection, dict) or not _REQUIRED - {'details'} <= projection.keys():
                    return None
                projection['details'] = _ProjectionDetails(projection['rows'], document['details'], document['objects'])
                return projection
            except (OSError, ValueError, KeyError, TypeError, zlib.error):
                return None  # Cache miss: rebuild from verified scientific inputs.

    def hold(self, keys):
        """Pin prepared sources through whole-refresh publication or failure."""
        return self.namespace.hold(self._path(key).name for key in keys)

    def publish(self, keys):
        return self.namespace.publish(self._path(key).name for key in keys)

    def write(self, key, projection):
        with self.namespace.writer(self._path(key).name):
            return self._write(key, projection)

    def _write(self, key, projection):
        if not isinstance(projection, dict) or not _REQUIRED <= projection.keys():
            raise ValueError('Incomplete source projection')
        rows, details = projection['rows'], projection['details']
        if rows.keys() != details.keys():
            raise ValueError('Source projection detail membership differs')
        path = self._path(key)
        temporary_paths = []

        def temporary():
            descriptor, name = tempfile.mkstemp(dir=self.directory, prefix=path.name+'.', suffix='.writing')
            temporary_paths.append(name)
            return descriptor, name

        with self.namespace.lease(path.name, reclaim=False):
            connection = None
            try:
                descriptor, database = temporary()
                os.close(descriptor)
                connection = sqlite3.connect(database)
                connection.execute('PRAGMA cache_size=-8192')
                connection.execute('PRAGMA temp_store=FILE')
                encoder = Encoder(connection)
                descriptor, payload_path = temporary()
                digest = hashlib.sha256()
                compressor = zlib.compressobj(level=1)
                json_encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                with os.fdopen(descriptor, 'wb') as handle:
                    def emit(text):
                        compressed = compressor.compress(text.encode())
                        handle.write(compressed)
                        digest.update(compressed)

                    def emit_json(value):
                        for chunk in json_encoder.iterencode(value):
                            emit(chunk)

                    emit('{"version":2,"key_hash":')
                    emit_json(checksum(key))
                    emit(',"projection":')
                    emit_json({name: value for name, value in projection.items() if name != 'details'})
                    emit(',"details":{')
                    for position, identity in enumerate(details):
                        if position:
                            emit(',')
                        emit_json(identity)
                        emit(':')
                        emit_json(encoder.partition(rows[identity], details[identity]))
                    emit('},"objects":[')
                    for position, item in enumerate(connection.execute('SELECT object_id,source_sha,kind,object_uuid,payload,sha256 '
                            'FROM metadata_objects ORDER BY object_id')):
                        if position:
                            emit(',')
                        number, source, kind, identity, payload, sha = item
                        emit_json({'id': number, 'source_sha': source, 'kind': kind, 'uuid': identity,
                            'payload': base64.b64encode(payload).decode('ascii'), 'sha256': sha.hex()})
                    emit(']}')
                    tail = compressor.flush()
                    handle.write(tail)
                    digest.update(tail)
                    handle.flush()
                    os.fsync(handle.fileno())
                descriptor, seal_path = temporary()
                with os.fdopen(descriptor, 'w') as handle:
                    handle.write(digest.hexdigest())
                    handle.flush()
                    os.fsync(handle.fileno())
                # Both files are fully built before publication. A crash between
                # replacements yields a checksum cache miss, never partial data.
                os.replace(payload_path, path)
                os.replace(seal_path, path.with_suffix('.sha256'))
            finally:
                if connection is not None:
                    connection.close()
                for name in temporary_paths:
                    for suffix in ('', '-journal', '-wal', '-shm'):
                        try:
                            os.unlink(name + suffix)
                        except FileNotFoundError:
                            pass
        return str(path)
