"""Disposable, checksum-sealed source projections; acquisition files stay untouched."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import zlib

from workspace_recipes import checksum

VERSION = 1


class ProjectionCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        if self.directory.is_symlink() or self.directory.parent.is_symlink():
            raise ValueError('Derived cache directories cannot be symbolic links')
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        return self.directory / (checksum({'version': VERSION, 'key': key}) + '.json.zlib')

    def read(self, key):
        path = self._path(key)
        seal = path.with_suffix('.sha256')
        if not path.exists() or not seal.exists():
            return None
        try:
            blob = path.read_bytes()
            if hashlib.sha256(blob).hexdigest() != seal.read_text().strip():
                return None
            document = json.loads(zlib.decompress(blob))
            if document.get('version') != VERSION or document.get('key_hash') != checksum(key):
                return None
            projection = document['projection']
            if not isinstance(projection, dict) or not {'rows', 'details', 'cells', 'source', 'fingerprints'} <= projection.keys():
                return None
            return projection
        except (OSError, ValueError, KeyError, zlib.error):
            return None  # Cache miss: rebuild from verified scientific inputs.

    def write(self, key, projection):
        path = self._path(key)
        blob = zlib.compress(json.dumps({'version': VERSION, 'key_hash': checksum(key),
            'projection': projection}, allow_nan=False, separators=(',', ':')).encode(), level=1)
        seal = hashlib.sha256(blob).hexdigest().encode()
        # A crash between these replacements produces a cache miss, not bad data.
        for destination, content in ((path, blob), (path.with_suffix('.sha256'), seal)):
            fd, temporary = tempfile.mkstemp(dir=self.directory, prefix='.writing-')
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return str(path)
