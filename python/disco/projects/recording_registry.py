"""Workspace-local ownership and conservative references for shared H5 bytes.

The registry is a locator index, never scientific membership or catalog authority.
All reuse verifies the actual bytes. References persist after failed imports so
deletion errs toward retaining a file, not breaking another project's pointer.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import uuid


def project_identity(root):
    root = Path(root)
    path = root / 'project.json'
    if root.is_symlink() or path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text())
        if value.get('format') != 'recording-project' or type(value.get('version')) is not int or value.get('version') != 1:
            return None
        return str(uuid.UUID(value['project_uuid']))
    except (OSError, ValueError, KeyError, TypeError):
        return None


@contextmanager
def recording_lock(project):
    root = Path(project).resolve()
    if project_identity(root) is None:
        yield
        return
    path = root.parent / '.disco-recordings.lock'
    if path.is_symlink():
        raise ValueError('Recording registry lock cannot be a symbolic link')
    with path.open('a') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def read_registry(project):
    path = Path(project).resolve().parent / '.disco-recordings.json'
    if path.is_symlink():
        raise ValueError('Recording registry cannot be a symbolic link')
    if not path.exists():
        return {'format': 'disco-managed-recordings', 'version': 1, 'recordings': {}}
    value = json.loads(path.read_text())
    if value.get('format') != 'disco-managed-recordings' or type(value.get('version')) is not int or value.get('version') != 1 or not isinstance(value.get('recordings'), dict):
        raise ValueError('Unsupported managed recording registry')
    for sha, entry in value['recordings'].items():
        if (not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha)
                or not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
                or Path(entry['path']).is_absolute() or '..' in Path(entry['path']).parts
                or not isinstance(entry.get('consumers'), list)):
            raise ValueError('Invalid managed recording registry entry')
        try:
            uuid.UUID(entry['owner_project_uuid'])
            for consumer in entry['consumers']:
                uuid.UUID(consumer['project_uuid'])
                name = consumer['project_directory']
                if not isinstance(name, str) or name in ('', '.', '..') or Path(name).name != name:
                    raise ValueError('Invalid consumer project directory')
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError('Invalid managed recording owner or consumer') from error
    return value


def owner(project, source):
    """Return a real project owner under the same workspace, or None."""
    project, source = Path(project).resolve(), Path(source).resolve()
    workspace = project.parent
    if not source.is_relative_to(workspace):
        return None
    relative = source.relative_to(workspace)
    if len(relative.parts) < 3 or relative.parts[1] != 'raw-uploads':
        return None
    root = workspace / relative.parts[0]
    identity = project_identity(root)
    if identity is None:
        return None
    for current in (source, *source.parents):
        if current == workspace:
            break
        if current.is_symlink():
            return None
    return {'path': str(root), 'project_uuid': identity}


def candidates(project, expected_sha256):
    """Yield registry and pre-existing validated-import locations, without H5 IO."""
    project = Path(project).resolve()
    workspace = project.parent
    registry = read_registry(project)
    entry = registry['recordings'].get(expected_sha256)
    yielded = set()
    if entry:
        path = (workspace / entry['path']).resolve()
        if not path.is_relative_to(workspace):
            raise ValueError('Recording registry path escapes workspace')
        owning = owner(project, path)
        if path.exists() and (owning is None or owning['project_uuid'] != entry['owner_project_uuid']):
            raise ValueError('Managed recording owner identity changed')
        yielded.add(path)
        yield path
    # Bootstrap recordings imported before this index existed. Only immediate
    # project children and their manifest files are inspected, never raw scans.
    for child in sorted(workspace.iterdir()):
        if project_identity(child) is None:
            continue
        imports = child / 'imports'
        if imports.is_symlink() or not imports.is_dir():
            continue
        for path in sorted(imports.glob('*/import-manifest.json')):
            if path.is_symlink() or path.parent.is_symlink():
                continue
            try:
                manifest = json.loads(path.read_text())
                if manifest.get('source_sha256') != expected_sha256:
                    continue
                raw = Path(manifest['source_path']).resolve()
                if raw in yielded or owner(project, raw) is None:
                    continue
                yielded.add(raw)
                yield raw
            except (OSError, ValueError, KeyError, TypeError):
                continue


def register_reference(project, source, expected_sha256):
    """Caller holds recording_lock and has verified the source's SHA-256."""
    project, source = Path(project).resolve(), Path(source).resolve()
    identity = project_identity(project)
    owning = owner(project, source)
    if identity is None or owning is None:
        raise ValueError('Managed recording registration requires real project owners')
    root = project.parent
    registry = read_registry(project)
    entry = registry['recordings'].get(expected_sha256)
    relative = str(source.relative_to(root))
    if entry and entry['path'] != relative:
        # A previous locator may be stale after an explicit move. Never replace
        # a still-present canonical copy behind existing consumers.
        old = (root / entry['path']).resolve()
        if old.exists():
            raise ValueError('Another managed copy already owns this recording checksum')
    consumers = (entry or {}).get('consumers', [])
    consumer = {'project_uuid': identity, 'project_directory': project.name}
    consumers = [value for value in consumers if value != consumer] + [consumer]
    registry['recordings'][expected_sha256] = {
        'path': relative, 'owner_project_uuid': owning['project_uuid'],
        'owner_project_directory': Path(owning['path']).name, 'consumers': consumers,
    }
    path = root / '.disco-recordings.json'
    descriptor, temporary = tempfile.mkstemp(prefix='.disco-recordings-', dir=root)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(registry, handle, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def dependents(project, source):
    """Conservative cross-project consumers, including detached registrations."""
    project, source = Path(project).resolve(), Path(source).resolve()
    if project_identity(project) is None:
        return []
    result = []
    for entry in read_registry(project)['recordings'].values():
        if (project.parent / entry['path']).resolve() != source:
            continue
        for consumer in entry['consumers']:
            if consumer['project_directory'] != project.name:
                result.append(consumer)
    # The registry accelerates reuse and retains pending consumers. Durable
    # import manifests are a second, independent deletion fence if that index
    # was removed or an older project had already linked this recording.
    for sibling in project.parent.iterdir():
        identity = project_identity(sibling)
        if sibling == project or identity is None:
            continue
        imports = sibling / 'imports'
        if imports.is_symlink():
            raise ValueError('Cannot verify shared recording references through symbolic links')
        for manifest_path in imports.glob('*/import-manifest.json'):
            try:
                if manifest_path.is_symlink() or manifest_path.parent.is_symlink():
                    raise ValueError('Shared import manifest cannot be a symbolic link')
                manifest = json.loads(manifest_path.read_text())
                if not isinstance(manifest, dict):
                    raise ValueError('Shared import manifest must be an object')
                raw = manifest.get('source_path')
                if not isinstance(raw, str) or not raw:
                    raise ValueError('Shared import manifest has no recording locator')
                if Path(raw).resolve() == source:
                    consumer = {'project_uuid': identity, 'project_directory': sibling.name}
                    if consumer not in result:
                        result.append(consumer)
            except (OSError, ValueError, TypeError) as error:
                raise ValueError('Cannot verify recording references in project ' + sibling.name) from error
    return result
