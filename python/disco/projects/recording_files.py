"""Retain verified H5 bytes once in a library shared by sibling projects."""
import hashlib
import os
import re
import tempfile
from pathlib import Path
import shutil
import uuid
from disco.projects.storage import managed_directory


def managed_recording_owner(project_dir, source):
    from disco.projects.recording_registry import owner
    return owner(project_dir, source)


def retain_recording(project_dir, source, expected_sha256):
    from disco.projects.recording_registry import candidates, project_identity, recording_lock, register_reference
    project = Path(project_dir).resolve()
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Recording SHA-256 must be 64 lowercase hexadecimal characters')
    # Legacy callers without project manifests keep the original contained-copy
    # contract. Real projects store new bytes independently of any project.
    if project_identity(project) is None:
        return _copy_recording(project, source, expected_sha256)
    with recording_lock(project):
        source = Path(source).resolve(strict=True)
        for candidate in candidates(project, expected_sha256):
            if not candidate.is_file() or managed_recording_owner(project, candidate) is None:
                continue
            with candidate.open('rb') as handle:
                actual = hashlib.file_digest(handle, 'sha256').hexdigest()
            if actual != expected_sha256:
                raise ValueError('Managed recording changed; refusing to reuse its identity')
            # Validate the chosen input too: matching a catalog hash does not
            # excuse a file changing between duplicate checking and retention.
            with source.open('rb') as handle:
                if hashlib.file_digest(handle, 'sha256').hexdigest() != expected_sha256:
                    raise ValueError('Recording changed before import; no catalog import was attempted')
            register_reference(project, candidate, expected_sha256)
            return candidate
        retained = _copy_library_recording(project, source, expected_sha256)
        register_reference(project, retained, expected_sha256)
        return retained


def _copy_library_recording(project, source, expected_sha256):
    from disco.projects.recording_registry import library_directory, sync_directory
    root = library_directory(project)
    destination = root / expected_sha256
    # A complete checksum directory is published atomically. Crashes can leave
    # only an unreferenced staging folder, never a partially published H5.
    temporary = Path(tempfile.mkdtemp(prefix='.incoming-', dir=root))
    output = temporary / source.name
    try:
        with source.open('rb') as reader, output.open('xb') as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        with output.open('rb') as reader:
            actual = hashlib.file_digest(reader, 'sha256').hexdigest()
        if actual != expected_sha256:
            raise ValueError('Recording changed while copying it into the library; no catalog import was attempted')
        sync_directory(temporary)
        if destination.exists() or destination.is_symlink():
            raise ValueError('Managed recording destination already exists; refusing overwrite')
        temporary.rename(destination)
        sync_directory(root)
        return destination / source.name
    finally:
        # Never remove a published recording if a later registry write fails.
        if temporary.exists():
            output.unlink(missing_ok=True)
            temporary.rmdir()


def _copy_recording(project_dir, source, expected_sha256):
    source = Path(source).resolve(strict=True)
    root = managed_directory(Path(project_dir).resolve(), 'raw-uploads')
    if source.is_relative_to(root):
        with source.open('rb') as reader:
            actual = hashlib.file_digest(reader, 'sha256').hexdigest()
        if actual != expected_sha256:
            raise ValueError('Recording changed before import; no catalog import was attempted')
        return source
    destination = root / str(uuid.uuid4())
    destination.mkdir()
    output = destination / source.name
    try:
        with source.open('rb') as reader, output.open('xb') as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
        with output.open('rb') as reader:
            actual = hashlib.file_digest(reader, 'sha256').hexdigest()
        if actual != expected_sha256:
            raise ValueError('Recording changed while copying it into the project; no catalog import was attempted')
        return output
    except BaseException:
        output.unlink(missing_ok=True)
        destination.rmdir()
        raise


def recording_display_name(manifest):
    """Keep recording display identity independent of its relocatable locator."""
    name = manifest.get('source_filename')
    if isinstance(name, str) and name.strip() and '/' not in name and '\\' not in name:
        return name
    return Path(manifest.get('source_path', '')).name


def recording_storage_receipt(project_dir, source, expected_sha256):
    """Describe an already verified retained file; not a catalog commit receipt."""
    project, source = Path(project_dir).resolve(), Path(source).resolve()
    owning = managed_recording_owner(project, source)
    library = owning is not None and owning.get('kind') == 'library'
    shared = owning is not None and Path(owning['path']) != project
    return {'kind': 'managed_library' if library else 'managed_reference' if shared else 'managed_copy',
            'path': str(source), 'owner_project': None if library else owning,
            'library_path': owning['path'] if library else None,
            'shared': shared, 'sha256': expected_sha256, 'verified': True,
            'original_removal_safe': False}


def verified_duplicate_storage(project_dir, source, expected_sha256):
    """A duplicate catalog row alone does not prove its recording is retained."""
    from disco.projects.recording_registry import recording_lock
    with recording_lock(project_dir):
        if not isinstance(source, (str, Path)) or not source:
            return None
        source = Path(source)
        if managed_recording_owner(project_dir, source) is None or not source.is_file():
            return None
        with source.open('rb') as reader:
            if hashlib.file_digest(reader, 'sha256').hexdigest() != expected_sha256:
                return None
        return recording_storage_receipt(project_dir, source, expected_sha256)
