"""Publish disposable typed sidecars only after their native base is verified."""
from __future__ import annotations
import contextlib
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import weakref
from collections import OrderedDict

from recording_workspace import digest
from disco.metadata.cache_lifecycle import CacheNamespace
from disco.workbench.recipes import checksum


class TypedGeneration:
    def __init__(self, reader, native, lease, namespace):
        self.reader, self.native, self.lease, self.namespace = reader, native, lease, namespace
        self.generation_token = reader.generation_token
        self.memberships = MembershipCache(reader, native)

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


class VerifiedMembership:
    """Process-local proof of a completed, immutable, disposable member table.

    The directory and native lease outlive every attached reader. Paths or
    signatures supplied by HTTP callers never construct this object.
    """
    def __init__(self, path, directory, native, generation_token, sources):
        from disco.metadata.typed_index import _signature
        self.path, self.directory, self.native = path, directory, native
        self.generation_token, self.sources = generation_token, sources
        self.signature = _signature(path)
        self._remove = weakref.finalize(self, self._unlink, path)

    @staticmethod
    def _unlink(path):
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    def check(self, reader):
        from disco.metadata.typed_index import _signature
        self.native._check()
        if (reader.generation_token != self.generation_token or self.path.is_symlink()
                or _signature(self.path) != self.signature):
            raise ValueError('Protocol membership generation changed')


class _MembershipDirectory:
    def __init__(self):
        temporary = tempfile.TemporaryDirectory(prefix='disco-membership-')
        self.name = temporary.name
        self._cleanup = weakref.finalize(self, temporary.cleanup)


class MembershipCache:
    """Share disk-backed scopes across thread-owned readers of one generation.

    Session-private storage avoids trusting persisted cache claims or repairing
    an immutable file in place. Misses are serialized; failed builds never enter
    the cache. LRU eviction releases only the cache reference: in-flight readers
    retain the original file until their connection closes. Budgets control
    retention, never reject a larger scientific membership.
    """
    def __init__(self, reader, native):
        self.reader, self.native = reader, native
        self.directory = None
        self.entries = OrderedDict()
        self.lock = threading.RLock()

    def get(self, authority, sources, identities):
        from disco.metadata.typed_index import attach_native
        sources = tuple(sorted(set(sources)))
        key = checksum({'binding': authority, 'sources': sources,
                        'generation': self.reader.generation_token})
        with self.lock:
            self.reader._check()
            self.native._check()
            found = self.entries.get(key)
            if found is not None:
                found.check(self.reader)
                self.entries.move_to_end(key)
                return found
            if self.directory is None:
                self.directory = _MembershipDirectory()
            descriptor, temporary = tempfile.mkstemp(suffix='.sqlite', dir=self.directory.name)
            os.close(descriptor)
            path = Path(temporary)
            try:
                connection = sqlite3.connect(path, uri=True)
                try:
                    attach_native(connection, self.reader.source_path)
                    connection.execute('CREATE TABLE members(epoch_id INTEGER PRIMARY KEY)')
                    connection.execute('CREATE TEMP TABLE member_sources(source_sha TEXT PRIMARY KEY)')
                    connection.executemany('INSERT INTO member_sources VALUES (?)', ((s,) for s in sources))
                    def checked():
                        for number, identity in enumerate(identities()):
                            if number % 2000 == 0:
                                self.reader._check()
                                self.native._check()
                            if not isinstance(identity, str):
                                raise ValueError('Scope identities must be strings')
                            yield (identity,)
                    connection.executemany('INSERT OR IGNORE INTO members '
                        'SELECT epoch_id FROM native.epochs WHERE epoch_uuid=?', checked())
                    connection.execute('DELETE FROM members WHERE NOT EXISTS ('
                        'SELECT 1 FROM native.epochs e WHERE e.epoch_id=members.epoch_id '
                        'AND e.source_sha IN (SELECT source_sha FROM member_sources))')
                    connection.commit()
                finally:
                    connection.close()
                self.reader._check()
                self.native._check()
                found = VerifiedMembership(path, self.directory, self.native,
                                           self.reader.generation_token, sources)
                self.entries[key] = found
                while len(self.entries) > 1 and (len(self.entries) > 16 or
                        sum(item.signature[2] for item in self.entries.values()) > 256 * 1024 * 1024):
                    self.entries.popitem(last=False)
                return found
            except BaseException:
                for leftover in (path, Path(str(path) + '-journal')):
                    with contextlib.suppress(FileNotFoundError):
                        leftover.unlink()
                raise


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
        try:
            previous._check()
        except (OSError, ValueError, sqlite3.DatabaseError):
            # A stale live proof cannot be reused, but must not prevent an
            # explicit refresh from fully verifying/rebuilding the sidecar.
            # Existing readers keep their original witnesses and still refuse.
            pass
        else:
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
