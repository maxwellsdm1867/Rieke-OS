"""Read-only, byte-identity preflight before an expensive recording parse.

The caller supplies authoritative Source rows from the intended catalog/project.
This does not validate H5 contents, detect repeated trials, or replace the final
import transaction's identity checks. It never writes or removes source files.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import stat

_CHUNK_SIZE = 1024 * 1024


class SourceChangedError(ValueError):
    """The file changed while its byte identity was being established."""


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _hash_stream(handle, progress=None, total=None):
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(_CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
        if progress:
            progress("checking_duplicates", completed=size, total=total, unit="bytes")
    return digest.hexdigest(), size


def _registered_summary(row):
    if not isinstance(row, Mapping):
        raise ValueError('Registered sources must contain Source-row mappings')
    identity = row.get('source_sha256')
    if (not isinstance(identity, str) or len(identity) != 64
            or any(character not in '0123456789abcdef' for character in identity)):
        raise ValueError('A registered Source has an invalid SHA-256 identity')
    manifest = row.get('manifest') or {}
    if not isinstance(manifest, Mapping):
        raise ValueError('A registered Source manifest must be a mapping')
    if manifest.get('source_sha256', identity) != identity:
        raise ValueError('Registered Source identity and manifest disagree')
    original_path = manifest.get('source_path') or row.get('source_path')
    if original_path is not None and not isinstance(original_path, (str, os.PathLike)):
        raise ValueError('A registered Source path must be text')
    summary = {'source_sha256': identity,
               'source_path': str(original_path) if original_path else None,
               'filename': Path(original_path).name if original_path else row.get('filename')}
    for key in ('project_uuid', 'experiment_uuid', 'experiment_id'):
        if key in row:
            summary[key] = row[key]
    if 'source_size' in manifest:
        summary['source_size'] = manifest['source_size']
    return summary


def classify_source(path, registered_sources, progress=None):
    """Return SHA/size/path, an exact-byte duplicate, and filename warnings.

    ``registered_sources`` is an iterable of authoritative Source rows or a
    zero-argument callback that fetches them AFTER hashing. A callback avoids
    classifying against an SQL snapshot taken before a long file read. Rows may
    carry their JSON manifest. Different names/paths do not evade duplicate
    detection. Case-insensitive equal filenames with different hashes produce
    warnings only. Existing registrations need not have an accessible raw file.

    The returned ``duplicate`` is a compact recorded-source dictionary or None;
    ``same_name_warnings`` contains the same compact dictionaries for different
    content. This function neither queries SQL nor changes registration state.
    Concurrent imports still require the import transaction's final SHA check.
    """
    source = Path(path).expanduser().resolve(strict=True)
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Choose a regular recording file, not a directory or device')
    expected = _signature(before)
    with source.open('rb') as handle:
        if _signature(os.fstat(handle.fileno())) != expected:
            raise SourceChangedError('Source recording changed before hashing; retry the duplicate check')
        identity, byte_count = _hash_stream(handle, progress, before.st_size) if progress else _hash_stream(handle)
        if _signature(os.fstat(handle.fileno())) != expected or byte_count != before.st_size:
            raise SourceChangedError('Source recording changed during hashing; retry the duplicate check')
        try:
            after = source.stat()
        except OSError as error:
            raise SourceChangedError('Source recording moved or became unavailable during hashing') from error
        if _signature(after) != expected:
            raise SourceChangedError('Source recording was changed or replaced during hashing; retry the duplicate check')

    rows = registered_sources() if callable(registered_sources) else registered_sources
    if isinstance(rows, (Mapping, str, bytes)):
        raise ValueError('Registered sources must be an iterable of Source rows')
    registered = [_registered_summary(row) for row in rows]
    identities = [row['source_sha256'] for row in registered]
    if len(set(identities)) != len(identities):
        raise ValueError('Registered sources contain repeated SHA-256 identities')
    try:
        after_lookup = source.stat()
    except OSError as error:
        raise SourceChangedError('Source recording became unavailable during catalog lookup') from error
    if _signature(after_lookup) != expected:
        raise SourceChangedError('Source recording changed during catalog lookup; retry the duplicate check')

    duplicate = next((row for row in registered if row['source_sha256'] == identity), None)
    warnings = [row for row in registered if row['source_sha256'] != identity
                and isinstance(row['filename'], str)
                and row['filename'].casefold() == source.name.casefold()]
    warnings.sort(key=lambda row: (row['source_path'] or '', row['source_sha256']))
    return {'source_sha256': identity, 'source_size': byte_count,
            'source_path': str(source), 'duplicate': duplicate,
            'same_name_warnings': warnings}
