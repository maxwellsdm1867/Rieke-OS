"""Lossless ancestor references inside a sealed, disposable metadata index.

Objects are scoped by source revision, object kind and acquisition UUID. Equal
names never establish identity. Conflicting content for one identity is rejected;
the original detail shape is reconstructed for callers and exported unchanged.
"""
from collections import OrderedDict
import copy
import hashlib
import json
import os
import sys
import threading
import uuid
import zlib

KINDS = {'cell': 'cell_uuid', 'group': 'group_uuid', 'block': 'block_uuid'}
CACHE_BYTES = 8 * 1024 * 1024
CACHE_ENTRIES = 128
_UNSET = object()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def _uuid(value):
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def _identity(row, kind, value=_UNSET):
    source = row.get('source_sha256')
    identity = _uuid(row.get(KINDS[kind]))
    if not isinstance(source, str) or not source or identity is None:
        return None
    if value is not _UNSET:
        # Unidentified legacy/synthetic metadata stays inline. Do not invent an
        # ancestor identity from labels, contents or the nearest matching row.
        if not isinstance(value, dict) or _uuid(value.get('uuid')) is None:
            return None
        if _uuid(value['uuid']) != identity:
            raise ValueError('Ancestor metadata UUID disagrees with epoch ownership')
    return source, kind, identity


def _retained_bytes(value):
    size = 0
    pending = [value]
    seen = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        size += sys.getsizeof(item)
        if isinstance(item, dict):
            pending.extend(item.keys()); pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return size


class _Cache:
    def __init__(self, budget):
        self.budget = budget
        self.values = OrderedDict()
        self.bytes = 0

    def get(self, key):
        entry = self.values.get(key)
        if entry is None:
            return None
        self.values.move_to_end(key)
        return entry[0]

    def put(self, key, value):
        size = _retained_bytes((key, value))
        previous = self.values.pop(key, None)
        if previous:
            self.bytes -= previous[1]
        if size > self.budget:
            return
        while self.values and (self.bytes + size > self.budget or len(self.values) >= CACHE_ENTRIES):
            _, (_, removed) = self.values.popitem(last=False)
            self.bytes -= removed
        self.values[key] = value, size
        self.bytes += size


class Encoder:
    def __init__(self, connection, *, cache_bytes=CACHE_BYTES):
        self.connection = connection
        self.cache = _Cache(cache_bytes)
        connection.execute('CREATE TABLE metadata_objects ('
            'object_id INTEGER PRIMARY KEY,source_sha TEXT COLLATE BINARY NOT NULL,'
            'kind TEXT COLLATE BINARY NOT NULL,object_uuid TEXT COLLATE BINARY NOT NULL,'
            'payload BLOB NOT NULL,sha256 BLOB NOT NULL,UNIQUE(source_sha,kind,object_uuid))')

    def _object(self, identity, value):
        raw = canonical(value)
        cached = self.cache.get(identity)
        if cached is not None:
            number, expected = cached
        else:
            saved = self.connection.execute('SELECT object_id,payload,sha256 FROM metadata_objects '
                'WHERE source_sha=? AND kind=? AND object_uuid=?', identity).fetchone()
            if saved is None:
                number = self.connection.execute('INSERT INTO metadata_objects '
                    '(source_sha,kind,object_uuid,payload,sha256) VALUES (?,?,?,?,?)',
                    (*identity, zlib.compress(raw), hashlib.sha256(raw).digest())).lastrowid
                expected = raw
            else:
                number, payload, digest = saved
                expected = zlib.decompress(payload)
                if hashlib.sha256(expected).digest() != digest:
                    raise ValueError('Ancestor metadata checksum differs')
            self.cache.put(identity, (number, expected))
        if expected != raw:
            raise ValueError('Conflicting ancestor metadata for one source UUID')
        return number

    def partition(self, row, detail):
        if not isinstance(detail, dict):
            raise ValueError('Epoch detail must be a metadata object')
        inline = dict(detail)
        objects = {}
        if isinstance(detail.get('metadata'), dict):
            inline['metadata'] = dict(detail['metadata'])
            for kind in KINDS:
                value = detail['metadata'].get(kind)
                identity = _identity(row, kind, value) if kind in detail['metadata'] else None
                if identity is not None:
                    objects[kind] = self._object(identity, value)
                    del inline['metadata'][kind]
        return {'version': 1, 'inline': inline, 'objects': objects}

    def encode(self, row, detail):
        return zlib.compress(canonical(self.partition(row, detail)))


class Decoder:
    def __init__(self, *, cache_bytes=CACHE_BYTES):
        self.cache = _Cache(cache_bytes)
        self.lock = threading.RLock()
        self.object_decodes = 0
        self.database_identity = None

    def _bind(self, connection):
        paths = [row[2] for row in connection.execute('PRAGMA database_list') if row[1] == 'main']
        if len(paths) != 1:
            raise ValueError('Metadata decoder requires one main database')
        if paths[0]:
            status = os.stat(paths[0])
            identity = (paths[0], status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)
        else:
            # Retain the handle identity; an object-id integer could be reused
            # after another in-memory database closes.
            identity = ('memory', connection, getattr(connection, 'total_changes', None))
        if self.database_identity is None:
            self.database_identity = identity
        elif self.database_identity != identity:
            raise ValueError('Metadata decoder belongs to a different database generation')

    def clear(self):
        with self.lock:
            self.cache.values.clear()
            self.cache.bytes = 0

    def _object(self, connection, number, identity):
        cached = self.cache.get(number)
        if cached is None:
            saved = connection.execute('SELECT source_sha,kind,object_uuid,payload,sha256 '
                'FROM metadata_objects WHERE object_id=?', (number,)).fetchone()
            if saved is None:
                raise ValueError('Epoch references missing ancestor metadata')
            raw = zlib.decompress(saved[3])
            if hashlib.sha256(raw).digest() != saved[4]:
                raise ValueError('Ancestor metadata checksum differs')
            value = json.loads(raw)
            if not isinstance(value, dict) or _uuid(value.get('uuid')) != saved[2]:
                raise ValueError('Ancestor metadata identity differs')
            cached = tuple(saved[:3]), value, _retained_bytes(value)
            self.object_decodes += 1
            self.cache.put(number, cached)
        if cached[0] != identity:
            raise ValueError('Epoch references a different source or ancestor UUID')
        return cached[1], cached[2]

    def decode(self, connection, row, blob, *, shared_objects=False, cache_receipt=False):
        document = json.loads(zlib.decompress(blob))
        if (not isinstance(document, dict) or set(document) != {'version', 'inline', 'objects'}
                or type(document['version']) is not int or document['version'] != 1 or not isinstance(document['inline'], dict)
                or not isinstance(document['objects'], dict) or set(document['objects']) - set(KINDS)):
            raise ValueError('Unsupported indexed epoch metadata')
        result = document['inline']
        if document['objects'] and not isinstance(result.get('metadata'), dict):
            raise ValueError('Invalid indexed ancestor references')
        retained_bytes = _retained_bytes(result) if cache_receipt else 0
        with self.lock:
            self._bind(connection)
            for kind, number in document['objects'].items():
                identity = _identity(row, kind)
                if identity is None or type(number) is not int or number <= 0 or kind in result['metadata']:
                    raise ValueError('Invalid indexed ancestor reference')
                value, size = self._object(connection, number, identity)
                retained_bytes += size
                # Internal detail-cache entries may share immutable ancestors;
                # public calls receive independent mutable dictionaries.
                result['metadata'][kind] = value if shared_objects else copy.deepcopy(value)
            reusable = all(number in self.cache.values for number in document['objects'].values())
        if cache_receipt:
            return result, retained_bytes, reusable
        return result
