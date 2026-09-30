"""Read-only discovery of immediate siblings and explicitly remembered projects.

Availability means the local identity manifests are valid and readable. It does
not claim that the project's SQL server is reachable or that source H5 files exist.
"""
from __future__ import annotations

import json
from pathlib import Path
import uuid

MANIFEST_LIMIT = 256 * 1024


def _read_manifest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Project manifests must be regular local files')
    if path.stat().st_size > MANIFEST_LIMIT:
        raise ValueError('Project manifest is unexpectedly large')
    with path.open(encoding='utf-8') as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError('Project manifest must be a JSON object')
    return value


def _identity(value):
    if not isinstance(value, str):
        raise ValueError('Project identity must be a UUID string')
    return str(uuid.UUID(value))


def _project_record(directory, *, current=False):
    if (directory / 'transfer.json').exists() or (directory / 'transfer.json').is_symlink():
        raise ValueError('Prepared project copies must be restored into a working project folder')
    if (directory / '.portable-restore.pending').exists():
        raise ValueError('Project transfer restore is incomplete; finish recovery before opening it')
    project = _read_manifest(directory / 'project.json')
    if project.get('format') != 'recording-project' or type(project.get('version')) is not int or project['version'] != 1:
        raise ValueError('Unsupported recording project manifest')
    identity = _identity(project.get('project_uuid'))
    name = project.get('display_name') or project.get('name')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
        raise ValueError('Project display name must contain 1–200 characters')
    if project.get('catalog_ref', 'catalog.json') != 'catalog.json':
        raise ValueError('Project catalog must use the adjacent catalog.json')
    record = {'uuid': identity, 'name': name.strip(), 'path': str(directory),
              'available': True, 'current': current}
    try:
        catalog = _read_manifest(directory / 'catalog.json')
        if catalog.get('format') != 'recording-catalog-reference' or type(catalog.get('version')) is not int or catalog['version'] != 1:
            raise ValueError('Unsupported recording catalog reference')
        if _identity(catalog.get('project_uuid')) != identity:
            raise ValueError('Project and catalog UUIDs do not match')
        record['database_kind'] = (catalog.get('managed_database') or {}).get('kind', 'legacy-mysql')
    except (OSError, ValueError, UnicodeError) as error:
        if not current:
            raise
        # Preserve the known current project's identity without permitting a
        # switch to an invalid catalog. No configuration contents are returned.
        record['available'] = False
        record['unavailable_reason'] = str(error)
    return record


def list_projects(project_dir):
    """Return current, immediate siblings and remembered external projects.

    Sibling directory and manifest symlinks are excluded. Duplicate UUIDs cannot
    establish a second selectable project: current wins; ambiguous non-current
    identities are omitted. The method performs no database/network calls/writes.
    """
    current_dir = Path(project_dir).expanduser().resolve(strict=True)
    if not current_dir.is_dir():
        raise ValueError('Current project must be a directory')
    current = _project_record(current_dir, current=True)
    candidates = []
    try:
        siblings = sorted(current_dir.parent.iterdir(), key=lambda path: (path.name.casefold(), path.name))
    except OSError:
        siblings = []
    for directory in siblings:
        try:
            if directory == current_dir or directory.is_symlink() or not directory.is_dir():
                continue
            candidate = _project_record(directory)
            if candidate['uuid'] != current['uuid'] or candidate.get('database_kind') == 'native-mysql':
                candidates.append(candidate)
        except (OSError, ValueError, UnicodeError):
            continue
    projects, last = _combined_projects([current, *candidates], current_dir.parent, current_dir)
    return {'current_project_uuid': current['uuid'], 'projects': projects,
            'managed_root': str(current_dir.parent), **last, 'launcher': False}


def _combined_projects(discovered, root, current=None):
    """Read only saved exact folders; their parents are never searched."""
    from workspace_startup_registry import read_registry, read_project_index, ordered_projects
    local = read_registry(root)
    index = read_project_index()
    by_path = {project['path']: project for project in discovered}
    for saved in index['projects']:
        path = saved['path']
        if path in by_path:
            continue
        directory = Path(path)
        try:
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError('Project folder is unavailable; reconnect its drive or add its new location')
            project = _project_record(directory, current=directory == current)
            if project['uuid'] != saved['project_uuid']:
                raise ValueError('This folder now contains a different project; add its new location')
        except (OSError, ValueError, UnicodeError) as error:
            # Keep removable-drive and moved-project references visible without
            # trusting stale manifests, following links, or exposing credentials.
            project = {'uuid': saved['project_uuid'], 'name': saved['name'], 'path': path,
                       'database_kind': saved['database_kind'], 'current': False,
                       'available': False, 'unavailable_reason': str(error)}
        by_path[path] = project
    projects = list(by_path.values())
    current_record = next((project for project in projects if project['current']), None)
    if current_record:
        projects = [project for project in projects if project['current']
                    or project['uuid'] != current_record['uuid'] or project.get('database_kind') == 'native-mysql']
    counts = {}
    for project in projects:
        counts[project['uuid']] = counts.get(project['uuid'], 0) + 1
    projects = [project for project in projects if project['current']
                or project.get('database_kind') == 'native-mysql' or counts[project['uuid']] == 1]
    saved_order = {**local, 'project_order': index['project_order'] or local.get('project_order', [])}
    projects = ordered_projects(projects, saved_order)
    last_path = index['last_project_path']
    last = next((project for project in projects if project['path'] == last_path), None)
    if last is None:
        matches = [project for project in projects if project['uuid'] == local.get('last_project_uuid')]
        last = matches[0] if len(matches) == 1 else None
    return projects, {'last_project_path': last['path'] if last else None,
                      'last_project_uuid': last['uuid'] if last else None}


def managed_root(path, *, allow_workspace_descendant=False):
    """Validate a managed root without following a caller supplied symlink."""
    from workspace_paths import workspace_root
    return workspace_root(path, allow_workspace_descendant=allow_workspace_descendant)


def list_managed_projects(root, current_project=None):
    root = managed_root(root)
    projects = []
    if root.exists():
        if not root.is_dir():
            raise ValueError('Managed project root must be a directory')
        for directory in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
            try:
                if directory.is_symlink() or not directory.is_dir():
                    continue
                projects.append(_project_record(directory, current=directory == current_project))
            except (OSError, ValueError, UnicodeError):
                continue
    projects, last = _combined_projects(projects, root, current_project)
    return {'current_project_uuid': next((p['uuid'] for p in projects if p['current']), None),
            'projects': projects, 'managed_root': str(root),
            'workspace_initialized': (root / '.rieke-workspace.json').is_file(),
            **last}


def create_project(root, name, *, directory=None, code_root=None, _lock_path=None):
    """Create only empty manifests/directories. Database provisioning is deferred."""
    import fcntl
    import re
    import datetime as dt
    from contextlib import ExitStack
    from recording_workspace import write_json
    from workspace_storage import initialize_layout
    # An explicit exact project folder does not select/create a new workspace.
    # It may be grouped under one, but never inside another project.
    root = managed_root(root, allow_workspace_descendant=_lock_path is not None)
    from workspace_desktop_paths import require_external_data_path
    require_external_data_path(root, reject_ancestor=False)
    if directory is not None and isinstance(directory, str) and directory.strip():
        chosen = Path(directory).expanduser()
        require_external_data_path(chosen if chosen.is_absolute() else root / chosen)
    code_root = Path(code_root or Path(__file__).resolve().parents[1]).resolve()
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Project name must contain 1–120 printable characters')
    name = name.strip()
    root.mkdir(parents=True, exist_ok=True)
    lock_file = Path(_lock_path) if _lock_path is not None else root / '.project-create.lock'
    if lock_file.is_symlink():
        raise ValueError('Project registry lock cannot be a symbolic link')
    with lock_file.open('a') as lock, ExitStack() as target_locks:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if _lock_path is None and any(p['available'] and Path(p['path']).parent == root and p['name'].casefold() == name.casefold()
                                     for p in list_managed_projects(root)['projects']):
            raise ValueError('A project with this name already exists; open it or choose another name')
        identity = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')[:60] or 'project'
        if directory is not None and (not isinstance(directory, str) or not directory.strip()):
            raise ValueError('Choose a nonempty folder name or omit it for an automatic folder')
        target = Path(directory).expanduser() if directory else root / f'{slug}-{identity[:8]}'
        if not target.is_absolute():
            target = root / target
        if target.is_symlink() or target.name.startswith('.') or target.resolve().parent != root:
            raise ValueError('Choose a direct project folder inside the managed project directory')
        target = target.resolve()
        if target.is_relative_to(code_root) or code_root.is_relative_to(target):
            raise ValueError('Project storage must be separate from application code')
        if _lock_path is None:
            # Managed-root and exact-folder routes must share a target lock.
            # The root lock still serializes automatic names across siblings.
            target_lock = target_locks.enter_context(_creation_lock_path(target).open('a'))
            fcntl.flock(target_lock.fileno(), fcntl.LOCK_EX)
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ValueError('Project folder already contains files; nothing was overwritten')
        target.mkdir(exist_ok=True)
        project = {'format':'recording-project','version':1,'project_uuid':identity,
                   'name':name,'display_name':name,'catalog_ref':'catalog.json',
                   'created_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        instance = str(uuid.uuid4())
        native = {'version':1,'kind':'native-mysql','project_uuid':identity,'instance_uuid':instance,
                  'storage_ref':'database/mysql','runtime_ref':'database/native-runtime.json',
                  'credentials_ref':'database/native-credentials.json'}
        catalog = {'format':'recording-catalog-reference','version':1,'project_uuid':identity,
                   'catalog_id':'retinanalysis-local','adapter':'datajoint','database':'schema',
                   'workspace_database':'recording_workspace',
                   'connection':{'host':'127.0.0.1','port':None,
                     'credential_provider':{'kind':'native-project','credentials_ref':'database/native-credentials.json'}},
                   'managed_database':native}
        initialize_layout(target, identity, code_root)
        write_json(target / 'database/service.json', catalog['managed_database'])
        write_json(target / 'catalog.json', catalog)
        # Publish identity last: discovery ignores incomplete creations.
        write_json(target / 'project.json', project)
        write_json(target / 'logs/storage/project-created.json', {
            'action':'project_created','project_uuid':identity,'created_at':project['created_at'],
            'sources':0,'epochs':0,'protocols':0,'database_status':'not_started'})
        return _project_record(target)


def _creation_lock_path(directory):
    from workspace_startup_registry import project_index_path
    import hashlib
    preference_root = project_index_path().parent
    if preference_root.is_symlink():
        raise ValueError('Local project preferences cannot be a symbolic link')
    preference_root.mkdir(parents=True, exist_ok=True)
    lock = preference_root / ('project-create-' + hashlib.sha256(str(directory).encode()).hexdigest()[:32] + '.lock')
    if lock.is_symlink():
        raise ValueError('Project creation lock cannot be a symbolic link')
    return lock


def create_project_at(directory, name, *, code_root=None):
    """Use the user's exact project folder, independently of preferred storage."""
    if not isinstance(directory, str) or not directory.strip():
        raise ValueError('Choose a project folder')
    path = Path(directory.strip()).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ValueError('Choose an absolute project folder, not a symbolic link')
    from workspace_desktop_paths import require_external_data_path
    require_external_data_path(path)
    code = Path(code_root or Path(__file__).resolve().parents[1]).resolve()
    if path.resolve().is_relative_to(code) or code.is_relative_to(path.resolve()):
        raise ValueError('Project storage must be separate from application code')
    # System paths such as macOS /tmp may have a symlinked parent. Resolve
    # the selected location after rejecting a symlink at the project itself.
    path = path.resolve()
    return create_project(path.parent, name, directory=str(path), code_root=code, _lock_path=_creation_lock_path(path))
