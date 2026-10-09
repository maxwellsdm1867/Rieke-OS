"""Retain newly imported recordings inside a project's portable folder."""
import hashlib
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
    # Legacy callers without project manifests keep the original contained-copy
    # contract. Native project imports can additionally reuse sibling owners.
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
        if managed_recording_owner(project, source) is not None:
            with source.open('rb') as handle:
                if hashlib.file_digest(handle, 'sha256').hexdigest() != expected_sha256:
                    raise ValueError('Recording changed before import; no catalog import was attempted')
            retained = source
        else:
            retained = _copy_recording(project, source, expected_sha256)
        register_reference(project, retained, expected_sha256)
        return retained


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
