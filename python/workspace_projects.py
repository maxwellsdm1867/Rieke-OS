"""Read-only discovery of sibling recording projects; never scan arbitrary roots.

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
    except (OSError, ValueError, UnicodeError) as error:
        if not current:
            raise
        # Preserve the known current project's identity without permitting a
        # switch to an invalid catalog. No configuration contents are returned.
        record['available'] = False
        record['unavailable_reason'] = str(error)
    return record


def list_projects(project_dir):
    """Return the current project plus valid immediate siblings, deterministically.

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
            if candidate['uuid'] != current['uuid']:
                candidates.append(candidate)
        except (OSError, ValueError, UnicodeError):
            continue
    occurrences = {}
    for candidate in candidates:
        occurrences[candidate['uuid']] = occurrences.get(candidate['uuid'], 0) + 1
    projects = [candidate for candidate in candidates if occurrences[candidate['uuid']] == 1]
    projects.sort(key=lambda item: (item['name'].casefold(), item['name'], item['path']))
    from workspace_startup_registry import read_registry
    saved = read_registry(current_dir.parent)
    return {'current_project_uuid': current['uuid'], 'projects': [current, *projects],
            'managed_root': str(current_dir.parent), 'last_project_uuid': saved.get('last_project_uuid'), 'launcher': False}


def managed_root(path):
    """Validate a managed root without following a caller supplied symlink."""
    from workspace_paths import workspace_root
    return workspace_root(path)


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
    counts = {}
    for project in projects:
        counts[project['uuid']] = counts.get(project['uuid'], 0) + 1
    projects = [p for p in projects if counts[p['uuid']] == 1]
    projects.sort(key=lambda p: (not p['current'], p['name'].casefold(), p['path']))
    from workspace_startup_registry import read_registry
    saved = read_registry(root)
    identities = {p['uuid'] for p in projects}
    return {'current_project_uuid': next((p['uuid'] for p in projects if p['current']), None),
            'projects': projects, 'managed_root': str(root),
            'workspace_initialized': (root / '.rieke-workspace.json').is_file(),
            'last_project_uuid': saved.get('last_project_uuid') if saved.get('last_project_uuid') in identities else None}


def create_project(root, name, *, directory=None, code_root=None, database_kind="native-mysql"):
    """Create only empty manifests/directories. Database provisioning is deferred."""
    import fcntl
    import re
    import datetime as dt
    from recording_workspace import write_json
    from workspace_storage import initialize_layout
    root = managed_root(root)
    code_root = Path(code_root or Path(__file__).resolve().parents[1]).resolve()
    if root.is_relative_to(code_root) or code_root.is_relative_to(root):
        raise ValueError('Project storage must be separate from application code')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Project name must contain 1–120 printable characters')
    name = name.strip()
    root.mkdir(parents=True, exist_ok=True)
    lock_file = root / '.project-create.lock'
    if lock_file.is_symlink():
        raise ValueError('Project registry lock cannot be a symbolic link')
    with lock_file.open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if any(p['name'].casefold() == name.casefold() for p in list_managed_projects(root)['projects']):
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
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ValueError('Project folder already contains files; nothing was overwritten')
        target.mkdir(exist_ok=True)
        project = {'format':'recording-project','version':1,'project_uuid':identity,
                   'name':name,'display_name':name,'catalog_ref':'catalog.json',
                   'created_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        container = 'rieke-os-' + identity.replace('-', '')
        catalog = {'format':'recording-catalog-reference','version':1,'project_uuid':identity,
                   'catalog_id':'retinanalysis-local','adapter':'datajoint','database':'schema',
                   'workspace_database':'recording_workspace',
                   'connection':{'host':'127.0.0.1','port':None,
                     'credential_provider':{'kind':'docker-container-env','container':container}},
                   'managed_database':{'version':1,'project_uuid':identity,'container':container,
                       'image':'datajoint/mysql:8.0','storage_ref':'database/mysql'}}
        if database_kind == 'native-mysql':
            catalog['connection']['credential_provider'] = {'kind': 'native-mysql'}
            catalog['managed_database'] = {'version':1, 'kind':'native-mysql',
                'project_uuid':identity, 'storage_ref':'database/mysql'}
        elif database_kind != 'docker-container-env':
            raise ValueError('Unsupported database kind')
        initialize_layout(target, identity, code_root)
        write_json(target / 'database/service.json', catalog['managed_database'])
        write_json(target / 'catalog.json', catalog)
        # Publish identity last: discovery ignores incomplete creations.
        write_json(target / 'project.json', project)
        write_json(target / 'logs/storage/project-created.json', {
            'action':'project_created','project_uuid':identity,'created_at':project['created_at'],
            'sources':0,'epochs':0,'protocols':0,'database_status':'not_started'})
        return _project_record(target)
