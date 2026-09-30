"""Retain newly imported recordings inside a project's portable folder."""
import hashlib
from pathlib import Path
import shutil
import uuid
from workspace_storage import managed_directory


def retain_recording(project_dir, source, expected_sha256):
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
