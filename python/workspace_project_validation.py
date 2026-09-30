"""Read-only folder preflight. Database availability and H5 checks happen on open."""
from pathlib import Path
from itertools import islice

from workspace_projects import _project_record, _read_manifest
from workspace_storage import DIRECTORIES, LOG_FOLDERS


def _manifest(root, relative):
    try:
        return _read_manifest(root / relative)
    except (OSError, ValueError, UnicodeError) as error:
        raise ValueError(f'Cannot open project: {relative} is missing or invalid ({error})') from error


def validate_project_folder(path):
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValueError('Choose an absolute project folder path')
    candidate = Path(str(path).strip()).expanduser()
    if not candidate.is_absolute():
        raise ValueError('Choose an absolute project folder path')
    if candidate.is_symlink():
        raise ValueError('Choose the project folder itself, not a symbolic link')
    if not candidate.is_dir():
        raise ValueError('Choose an existing project folder containing project.json')
    root = candidate.resolve()
    _manifest(root, 'project.json')
    _manifest(root, 'catalog.json')
    try:
        record = _project_record(root)
    except (OSError, ValueError, UnicodeError, TypeError) as error:
        raise ValueError(f'Cannot open project: {error}') from error
    catalog = _manifest(root, 'catalog.json')
    result = {'valid': True, 'kind': 'project', 'project': record, 'checks': ['Project and catalog identities match'],
              'warnings': [], 'database_status': 'legacy_external'}
    provider = catalog.get('connection', {}).get('credential_provider', {})
    if record['database_kind'] != 'native-mysql' and provider.get('kind') != 'native-project':
        result['warnings'].append('Legacy database configuration: database availability and linked recording files are checked when opening.')
        import os
        if os.environ.get('RIEKE_DESKTOP_MODE') == '1':
            result['desktop_compatibility'] = {'can_open': False, 'requires_migration': True,
                'migration_available': provider.get('kind') == 'docker-container-env',
                'migration_endpoint': '/api/projects/migrate-source',
                'message': 'Create a desktop copy in a separate folder. The original project and source database stay unchanged.'}
        return result
    # _configuration checks descriptors and rejects symlinked native state without
    # calling the runtime, opening a database connection, or changing file modes.
    _manifest(root, 'database/service.json')
    from workspace_native_mysql import _configuration
    try:
        _, descriptor = _configuration(root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f'Cannot open project: invalid native database configuration ({error})') from error
    layout = _manifest(root, 'storage.json')
    directories = {key: key for key in DIRECTORIES}
    expected = {'format': 'recording-project-storage', 'version': 1,
                'project_uuid': record['uuid'], 'directories': directories,
                'logs': {kind: 'logs/' + kind for kind in LOG_FOLDERS},
                'catalog_ref': 'catalog.json', 'database_runtime_ref': 'database/runtime.json'}
    legacy = {**expected, 'directories': {key: value for key, value in directories.items() if key != 'cache'}}
    if layout != expected and layout != legacy:
        raise ValueError('Cannot open project: storage.json does not match this project or its supported folder layout')
    for relative in layout['directories'].values():
        folder = root / relative
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f'Cannot open project: required managed folder {relative}/ is missing or is a symbolic link')
    result['checks'].append('Managed folder layout and database ownership descriptor match')
    owner_path = root / 'database/native-owner.json'
    data = root / descriptor['storage_ref']
    credentials_path = root / descriptor['credentials_ref']
    if not owner_path.exists():
        evidence = (credentials_path.exists() or (root / descriptor['runtime_ref']).exists()
                    or (data.exists() and (not data.is_dir() or any(data.iterdir())))
                    or any((root / 'imports').iterdir()) or any((root / 'raw-uploads').iterdir())
                    or any((root / 'protocols').iterdir()))
        if evidence:
            raise ValueError('Cannot open project: database ownership is missing from an initialized or incomplete project; restore its database files before opening')
        result['database_status'] = 'not_initialized'
        result['checks'].append('Empty project; private database will be initialized when opened')
        return result
    owner = _manifest(root, 'database/native-owner.json')
    expected_owner = {'version': 1, 'project_uuid': record['uuid'],
                      'instance_uuid': descriptor['instance_uuid'], 'mysql_series': '8.4'}
    if any(owner.get(key) != value for key, value in expected_owner.items()):
        raise ValueError('Cannot open project: native database ownership belongs to a different project or unsupported MySQL version')
    if not data.is_dir() or not any(data.iterdir()):
        raise ValueError('Cannot open project: previously initialized database/mysql is missing or empty; restore the complete project folder')
    for filename in ('ibdata1', 'mysql.ibd'):
        file = data / filename
        if file.is_symlink() or not file.is_file() or file.stat().st_size == 0:
            raise ValueError(f'Cannot open project: database/mysql/{filename} is missing or invalid; restore the complete database')
    credentials = _manifest(root, descriptor['credentials_ref'])
    if (credentials.get('version') != 1 or credentials.get('project_uuid') != record['uuid']
            or credentials.get('instance_uuid') != descriptor['instance_uuid']
            or not isinstance(credentials.get('password'), str) or len(credentials['password']) < 32):
        raise ValueError('Cannot open project: native database credentials do not match the project')
    result['database_status'] = 'initialized'
    result['checks'].append('Previously initialized database files and credentials are present')
    if owner.get('clean_shutdown') is not True:
        result['warnings'].append('Database is open or was not closed cleanly; opening will check whether local recovery is safe. A moved unclean database cannot be opened.')
    result['warnings'].append('Recording availability and checksums are verified when opening.')
    return result


def _inspect_exact(candidate):
    from workspace_portability import MANIFEST, inspect_package
    if (candidate / MANIFEST).exists() or (candidate / MANIFEST).is_symlink():
        transfer = inspect_package(candidate)
        root = candidate.resolve()
        project = _manifest(root, 'project.json')
        return {'valid': True, 'kind': 'prepared-transfer',
                'project': {'uuid': transfer['project_uuid'],
                            'name': project.get('display_name') or project['name'],
                            'path': str(root), 'available': True, 'current': False},
                'database_status': 'restore_required',
                'checks': ['Prepared project identity and complete file inventory verified',
                           'Recording and parsed metadata checksums verified'],
                'warnings': [], 'source_count': len(transfer['sources'])}
    return validate_project_folder(candidate)


def inspect_project_folder(path):
    """Inspect an exact root, or propose nearby fully validated roots read-only.

    Search at most eight ancestors and 128 immediate children. Never descend
    into unrelated directory trees, follow directory aliases, open a server,
    select a candidate automatically, or change the user's selected folder.
    """
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValueError('Choose an absolute project folder path')
    candidate = Path(str(path).strip()).expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ValueError('Choose an absolute project folder path, not a symbolic link')
    if not candidate.is_dir():
        raise ValueError('Choose an existing project folder')
    try:
        return _inspect_exact(candidate)
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as error:
        original_error = error

    def suggestion(folder, reason):
        if folder.is_symlink() or not folder.is_dir():
            return None
        if not any((folder / marker).exists() or (folder / marker).is_symlink()
                   for marker in ('project.json', 'transfer.json')):
            return None
        try:
            report = _inspect_exact(folder)
        except (ValueError, OSError, UnicodeError, TypeError, KeyError):
            return None
        project = report['project']
        return {'path': project['path'], 'name': project['name'], 'kind': report['kind'],
                'reason': reason}

    candidates = []
    for parent in islice(candidate.parents, 8):
        if parent.is_symlink():
            # A nested selection beneath an alias cannot identify its actual root.
            break
        found = suggestion(parent, 'containing-project')
        if found:
            candidates.append(found)
            break  # The closest enclosing valid root owns this selection.
    if not candidates:
        try:
            children = list(islice(candidate.iterdir(), 128))
        except OSError:
            children = []
        for child in sorted(children, key=lambda entry: entry.name.casefold()):
            found = suggestion(child, 'child-project')
            if found:
                candidates.append(found)
    if not candidates:
        if isinstance(original_error, ValueError):
            raise original_error
        raise ValueError(f'Cannot open project: {original_error}') from original_error
    if candidates[0]['reason'] == 'containing-project':
        message = 'This folder is inside a project. Choose its top folder below.'
    elif len(candidates) == 1:
        message = 'A project was found one folder below. Choose its top folder below.'
    else:
        message = 'Several projects were found one folder below. Choose the project you want.'
    return {'valid': False, 'kind': 'project-root-suggestions', 'restore_required': False,
            'message': message, 'candidates': candidates}
