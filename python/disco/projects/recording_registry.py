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


LIBRARY_DIRECTORY = 'recordings'
LIBRARY_MARKER = '.disco-library.json'


def library_identity(directory):
    """Read a library's durable identity without adopting arbitrary folders."""
    directory = Path(directory)
    marker = directory / LIBRARY_MARKER
    if directory.is_symlink() or marker.is_symlink():
        raise ValueError('Managed recording library cannot contain symbolic links')
    if not marker.exists():
        return None
    value = json.loads(marker.read_text())
    if not isinstance(value, dict) or value.get('format') != 'disco-recording-library' or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Unsupported managed recording library')
    return str(uuid.UUID(value['library_uuid']))


def library_directory(project):
    """Create/open the shared library. Caller holds recording_lock."""
    root = Path(project).resolve().parent / LIBRARY_DIRECTORY
    if library_identity(root) is not None:
        return root
    root.mkdir(exist_ok=True)
    if any(root.iterdir()):
        raise ValueError('The recordings folder is not a DISCO library; choose a different project parent folder')
    marker = root / LIBRARY_MARKER
    with marker.open('x') as handle:
        json.dump({'format': 'disco-recording-library', 'version': 1, 'library_uuid': str(uuid.uuid4())}, handle)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(root)
    sync_directory(root.parent)
    return root


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def library_candidate(project, expected_sha256):
    """Recover a published copy even if registry publication was interrupted."""
    root = Path(project).resolve().parent / LIBRARY_DIRECTORY
    if library_identity(root) is None:
        return None
    directory = root / expected_sha256
    if directory.is_symlink():
        raise ValueError('Managed recording directory cannot be a symbolic link')
    if not directory.exists():
        return None
    files = list(directory.iterdir())
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ValueError('Managed recording directory is incomplete or changed')
    return files[0]


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
    if not isinstance(value, dict) or value.get('format') != 'disco-managed-recordings' or type(value.get('version')) is not int or value.get('version') not in (1, 2) or not isinstance(value.get('recordings'), dict):
        raise ValueError('Unsupported managed recording registry')
    for sha, entry in value['recordings'].items():
        if (not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha)
                or not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
                or Path(entry['path']).is_absolute() or '..' in Path(entry['path']).parts
                or not isinstance(entry.get('consumers'), list)):
            raise ValueError('Invalid managed recording registry entry')
        try:
            if entry.get('owner_kind', 'project') == 'library' and value['version'] == 2:
                uuid.UUID(entry['owner_library_uuid'])
                parts = Path(entry['path']).parts
                if len(parts) != 3 or parts[:2] != (LIBRARY_DIRECTORY, sha):
                    raise ValueError('Invalid managed library recording path')
            elif entry.get('owner_kind', 'project') == 'project':
                uuid.UUID(entry['owner_project_uuid'])
            else:
                raise ValueError('Invalid managed recording owner kind')
            for consumer in entry['consumers']:
                uuid.UUID(consumer['project_uuid'])
                name = consumer['project_directory']
                if not isinstance(name, str) or name in ('', '.', '..') or Path(name).name != name:
                    raise ValueError('Invalid consumer project directory')
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError('Invalid managed recording owner or consumer') from error
    return value


def owner(project, source):
    """Return a library or legacy project owner under the same workspace."""
    project, source = Path(project).resolve(), Path(source).absolute()
    workspace = project.parent
    if not source.is_relative_to(workspace) or '..' in source.parts:
        return None
    for current in (source, *source.parents):
        if current == workspace:
            break
        if current.is_symlink():
            return None
    relative = source.relative_to(workspace)
    if len(relative.parts) == 3 and relative.parts[0] == LIBRARY_DIRECTORY:
        digest = relative.parts[1]
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            return None
        root = workspace / LIBRARY_DIRECTORY
        identity = library_identity(root)
        if identity is not None:
            return {'kind': 'library', 'path': str(root), 'library_uuid': identity, 'project_uuid': None}
        return None
    if len(relative.parts) < 3 or relative.parts[1] != 'raw-uploads':
        return None
    root = workspace / relative.parts[0]
    identity = project_identity(root)
    if identity is None:
        return None
    return {'path': str(root), 'project_uuid': identity}


def is_managed_source(source):
    """Do not advise deleting another project's/library's original input."""
    source = Path(source).resolve()
    for directory in source.parents:
        if directory.name == 'raw-uploads' and project_identity(directory.parent) is not None:
            return True
        if directory.name == LIBRARY_DIRECTORY and library_identity(directory) is not None:
            return True
    return False


def recording_location(project, source):
    """Portable identity/relative locator alongside the current absolute path."""
    owning = owner(project, source)
    if owning and owning.get('kind') == 'library':
        return {'kind': 'library', 'library_uuid': owning['library_uuid'],
                'path': str(Path(source).relative_to(Path(project).resolve().parent))}
    return None


def candidates(project, expected_sha256):
    """Yield registry and pre-existing validated-import locations, without H5 IO."""
    project = Path(project).resolve()
    workspace = project.parent
    registry = read_registry(project)
    entry = registry['recordings'].get(expected_sha256)
    yielded = set()
    if entry:
        path = workspace / entry['path']
        if not path.resolve().is_relative_to(workspace):
            raise ValueError('Recording registry path escapes workspace')
        owning = owner(project, path)
        key = 'library_uuid' if entry.get('owner_kind') == 'library' else 'project_uuid'
        if path.exists() and (owning is None or owning.get(key) != entry.get('owner_' + key)):
            raise ValueError('Managed recording owner identity changed')
        yielded.add(path)
        yield path
    published = library_candidate(project, expected_sha256)
    if published is not None and published not in yielded:
        yielded.add(published)
        yield published
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
                raw = Path(manifest['source_path']).absolute()
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
    if owning.get('kind') == 'library':
        registry['version'] = 2
        ownership = {'owner_kind': 'library', 'owner_library_uuid': owning['library_uuid']}
    else:
        ownership = {'owner_project_uuid': owning['project_uuid'],
                     'owner_project_directory': Path(owning['path']).name}
    registry['recordings'][expected_sha256] = {
        'path': relative, **ownership, 'consumers': consumers,
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


def relocated_library_recording(project, manifest):
    """Resolve the same library after a master-folder move, never by name alone."""
    location = manifest.get('recording_location')
    if location is None:
        return None
    if not isinstance(location, dict) or location.get('kind') != 'library':
        raise ValueError('Unsupported recording location')
    relative = Path(location.get('path', ''))
    parts = relative.parts
    if (relative.is_absolute() or '..' in parts or len(parts) != 3 or
            parts[:2] != (LIBRARY_DIRECTORY, manifest['source_sha256'])):
        raise ValueError('Invalid library recording location')
    candidate = Path(project).resolve().parent / relative
    owning = owner(project, candidate)
    if owning and owning.get('library_uuid') == location.get('library_uuid'):
        return candidate
    return None
