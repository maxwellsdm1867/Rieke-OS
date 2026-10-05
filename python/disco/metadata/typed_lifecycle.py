"""Publish disposable typed sidecars only after their native base is verified."""
from __future__ import annotations
import contextlib
import os
from pathlib import Path
import sqlite3
import tempfile

from recording_workspace import digest
from disco.metadata.cache_lifecycle import CacheNamespace
from disco.workbench.recipes import checksum


class TypedGeneration:
    def __init__(self, reader, native, lease, namespace):
        self.reader, self.native, self.lease, self.namespace = reader, native, lease, namespace
        self.generation_token = reader.generation_token

    def _check(self):
        self.native._check()
        self.reader._check()

    def field_registry(self):
        self._check()
        return self.reader.field_registry()

    def clone(self):
        from disco.metadata.typed_index import TypedMetadataIndex
        self._check()
        return TypedMetadataIndex.open_verified(self.reader)

    def publish(self):
        self._check()
        return self.namespace.publish([self.reader.path.name])


def prepare(native, previous=None):
    """Build/open one immutable sidecar; caller owns the publication fence.

    Native leases remain held for as long as any published owner or query uses
    the typed generation. Default open exhaustively verifies the sidecar seal;
    later thread-owned readers reuse that live verification proof.
    """
    from disco.metadata.typed_index import TypedMetadataIndex, build
    import disco.metadata.typed_index as workspace_typed_index, disco.metadata.typed_query as workspace_typed_query
    native._check()
    name = checksum({'native': native.generation, 'typed_contract': [
        digest(Path(module.__file__)) for module in (workspace_typed_index, workspace_typed_query)]}) + '.sqlite'
    namespace = CacheNamespace(native.path.parent.parent / 'typed-metadata', 'metadata', native.project_uuid)
    path = namespace.directory / name
    if previous is not None and previous.reader.path == path:
        previous._check()
        return previous, 'reused'
    lease = namespace.lease(name)
    try:
        with namespace.writer(name):
            try:
                reader = TypedMetadataIndex(path, native.path, expected_generation=native.generation,
                                            expected_project_uuid=native.project_uuid)
                status = 'reopened'
            except (OSError, ValueError, sqlite3.DatabaseError):
                descriptor, temporary = tempfile.mkstemp(prefix=name+'.', suffix='.building', dir=namespace.directory)
                os.close(descriptor)
                os.unlink(temporary)  # Builder exclusively reserves a fresh path.
                try:
                    build(native.path, temporary, expected_generation=native.generation,
                          expected_project_uuid=native.project_uuid)
                    verified = TypedMetadataIndex(temporary, native.path, expected_generation=native.generation,
                                                  expected_project_uuid=native.project_uuid)
                    verified.close()
                    native._check()
                    os.replace(temporary, path)
                    os.replace(temporary+'.sha256.json', str(path)+'.sha256.json')
                    reader = TypedMetadataIndex(path, native.path, expected_generation=native.generation,
                                                expected_project_uuid=native.project_uuid)
                    status = 'built'
                finally:
                    for leftover in (temporary, temporary+'.sha256.json', temporary+'-journal'):
                        with contextlib.suppress(FileNotFoundError):
                            os.unlink(leftover)
        native._check()
        return TypedGeneration(reader, native, lease, namespace), status
    except BaseException:
        lease.close()
        raise
