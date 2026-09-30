"""Small durable launcher preference; no database credentials or source payloads."""
from pathlib import Path
import json
import uuid
import fcntl
import os
import tempfile
from recording_workspace import write_json


def read_registry(root):
    path = Path(root) / '.rieke-os.json'
    if path.is_symlink():
        raise ValueError('Startup registry cannot be a symbolic link')
    if not path.exists():
        return {'format':'rieke-os-startup','version':1,'last_project_uuid':None}
    if path.stat().st_size > 64 * 1024:
        raise ValueError('Startup registry is unexpectedly large')
    value = json.loads(path.read_text())
    if not isinstance(value,dict) or value.get('format') != 'rieke-os-startup' or value.get('version') != 1:
        raise ValueError('Startup registry is invalid; preserve it and repair its configuration')
    if value.get('last_project_uuid') is not None:
        uuid.UUID(value['last_project_uuid'])
    return value


def _update_registry(root, changes):
    root = Path(root)
    lock_path = root / '.rieke-os.lock'
    if lock_path.is_symlink():
        raise ValueError('Startup registry lock cannot be a symbolic link')
    with lock_path.open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        value = {**read_registry(root), **changes}
        if len(json.dumps(value).encode()) > 64 * 1024:
            raise ValueError('Startup registry is unexpectedly large')
        write_json(root / '.rieke-os.json', value)


def remember_project(root, identity):
    _update_registry(root, {'last_project_uuid': str(uuid.UUID(identity))})


def remember_project_order(root, paths):
    _update_registry(root, {'project_order': paths})


def ordered_projects(projects, saved):
    # A folder identifies an independent native copy even when UUIDs match.
    paths = saved.get('project_order')
    ranks = {path: index for index, path in enumerate(paths)} if isinstance(paths, list) and all(isinstance(path, str) for path in paths) else {}
    return sorted(projects, key=lambda item: (ranks.get(item['path'], len(ranks)),
        item['name'].casefold(), item['name'], item['path']))


PROJECT_INDEX_FORMAT = 'rieke-local-projects'
PROJECT_INDEX_LIMIT = 1024 * 1024


def project_index_path():
    """Local OS-user discovery state, independent of project and application roots."""
    override = os.environ.get('RIEKE_PROJECT_INDEX')
    if override:
        path = Path(override).expanduser()
    elif os.environ.get('RIEKE_DESKTOP_USER_STATE'):
        path = Path(os.environ['RIEKE_DESKTOP_USER_STATE']).expanduser() / 'preferences/project-index.json'
    else:
        path = Path(os.environ.get('RIEKE_PREFERENCES_DIR', Path.home() / '.rieke-os')).expanduser() / 'project-index.json'
    if not path.is_absolute():
        raise ValueError('Local project index must use an absolute path')
    if path.is_symlink():
        raise ValueError('Local project index cannot be a symbolic link')
    # macOS /tmp and /var are system aliases. Preserve the selected filename
    # while canonicalizing its parent, rather than rejecting normal OS paths.
    return path.parent.resolve() / path.name


def _path_string(value):
    if (not isinstance(value, str) or not value or len(value) > 4096 or '\0' in value
            or not Path(value).is_absolute() or '..' in Path(value).parts
            or str(Path(value)) != value):
        raise ValueError('Local project references must be normalized absolute folders')
    return value


def _validate_project_index(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'version', 'projects', 'last_project_path', 'project_order'}
            or value['format'] != PROJECT_INDEX_FORMAT or type(value['version']) is not int or value['version'] != 1
            or not isinstance(value['projects'], list) or len(value['projects']) > 1000
            or not isinstance(value['project_order'], list) or len(value['project_order']) > 1000):
        raise ValueError('Local project index is invalid; preserve it and repair its configuration')
    seen = set()
    for project in value['projects']:
        if not isinstance(project, dict) or set(project) != {'path', 'project_uuid', 'name', 'database_kind'}:
            raise ValueError('Local project index contains an invalid project record')
        path = _path_string(project['path'])
        if path in seen:
            raise ValueError('Local project index contains duplicate folder references')
        seen.add(path)
        if (not isinstance(project['project_uuid'], str) or str(uuid.UUID(project['project_uuid'])) != project['project_uuid']
                or not isinstance(project['name'], str) or not 1 <= len(project['name'].strip()) <= 200
                or not isinstance(project['database_kind'], str) or project['database_kind'] not in {'native-mysql', 'legacy-mysql'}):
            raise ValueError('Local project index identity or display fields are invalid')
    order = [_path_string(path) for path in value['project_order']]
    if len(set(order)) != len(order):
        raise ValueError('Local project order contains duplicate folders')
    if value['last_project_path'] is not None:
        _path_string(value['last_project_path'])
        if value['last_project_path'] not in seen:
            raise ValueError('Last-open project is missing from the local project index')
    return value


def read_project_index():
    path = project_index_path()
    if path.is_symlink():
        raise ValueError('Local project index cannot be a symbolic link')
    if not path.exists():
        return {'format': PROJECT_INDEX_FORMAT, 'version': 1, 'projects': [],
                'last_project_path': None, 'project_order': []}
    if not path.is_file() or path.stat().st_size > PROJECT_INDEX_LIMIT:
        raise ValueError('Local project index is invalid or unexpectedly large')
    return _validate_project_index(json.loads(path.read_text()))


def _update_project_index(change):
    path = project_index_path()
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Local project index cannot be a symbolic link')
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix('.lock')
    if lock_path.is_symlink():
        raise ValueError('Local project index lock cannot be a symbolic link')
    with lock_path.open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        value = _validate_project_index(change(read_project_index()))
        content = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'
        if len(content) > PROJECT_INDEX_LIMIT:
            raise ValueError('Local project index is unexpectedly large')
        fd, temporary = tempfile.mkstemp(prefix='.project-index-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return value


def remember_project_path(directory, identity=None, *, set_last=False, previous_directory=None):
    """Remember one explicitly created/opened folder; never inspect its neighbors."""
    from workspace_projects import _project_record
    directory = Path(directory).expanduser()
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError('Remember an existing regular project folder by its absolute path')
    record = _project_record(directory.resolve())
    if identity is not None and record['uuid'] != str(uuid.UUID(identity)):
        raise ValueError('Remembered project identity disagrees with its folder')
    entry = {'path': record['path'], 'project_uuid': record['uuid'], 'name': record['name'],
             'database_kind': 'native-mysql' if record.get('database_kind') == 'native-mysql' else 'legacy-mysql'}
    previous = None
    if previous_directory is not None:
        previous = Path(previous_directory).expanduser()
        if not previous.is_absolute():
            raise ValueError('Previous project folder must be absolute')
        previous = str(previous.resolve())

    def update(value):
        value['projects'] = [project for project in value['projects'] if project['path'] not in {entry['path'], previous}]
        value['projects'].append(entry)
        if previous and previous != entry['path']:
            value['project_order'] = [entry['path'] if path == previous else path for path in value['project_order'] if path != entry['path']]
        if set_last or (previous is not None and value['last_project_path'] == previous):
            value['last_project_path'] = entry['path']
        return value
    return _update_project_index(update)


def remember_project_paths_order(paths):
    """Preserve global path order across preferred locations and copied UUIDs."""
    if not isinstance(paths, list) or len(paths) > 1000:
        raise ValueError('Project order must be a bounded folder list')
    paths = [_path_string(path) for path in paths]
    if len(set(paths)) != len(paths):
        raise ValueError('Project order cannot contain duplicate folders')
    return _update_project_index(lambda value: {**value, 'project_order': paths})


def remember_project_result(directory, result, *, set_last=False, previous_directory=None):
    """A failed discovery preference must not undo a completed project operation."""
    options = {}
    if set_last:
        options['set_last'] = True
    if previous_directory is not None:
        options['previous_directory'] = previous_directory
    try:
        remember_project_path(directory, **options)
    except (OSError, ValueError) as error:
        return {**result, 'registry_warning':
                f'Project is ready at {directory}, but its project-list entry could not be saved: {error}'}
    return result
