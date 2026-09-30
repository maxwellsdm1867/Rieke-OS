"""Managed project directories and a bounded, metadata-only file inventory.

Code stays in the repository. SQL data files belong to the database service and
are never served or edited by the file browser.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess

from recording_workspace import write_json


DIRECTORIES = {
    'database': ('Main database', 'Database service configuration and managed MySQL storage.'),
    'protocols': ('Protocol queries', 'Reusable protocol query definitions.'),
    'imports': ('Parsed recordings', 'Validated metadata, source pointers and parse manifests.'),
    'raw-uploads': ('Managed recordings', 'Verified project copies used for lazy waveform loading; keep these files in the project.'),
    'query-snapshots': ('Query snapshots', 'Frozen query baselines for comparisons.'),
    'exports': ('Exports', 'Versioned reference packages and their recipes.'),
    'logs': ('Logs', 'Import jobs, app jobs, failures and storage operations.'),
    'cache': ('Derived indexes', 'Disposable metadata indexes and source projections; original recordings remain authoritative.'),
    'backups': ('Backups', 'Automatic app-state snapshots and explicitly verified database backups.'),
}
LOG_FOLDERS = ('imports', 'app-jobs', 'errors', 'storage')


def managed_directory(root, relative):
    root = Path(root).resolve()
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Managed storage directories cannot be symbolic links')
    if not path.resolve().is_relative_to(root):
        raise ValueError('Managed directory leaves the project root')
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir(project, kind):
    if kind not in LOG_FOLDERS:
        raise ValueError('Unknown log category')
    return managed_directory(project, 'logs/' + kind)


def initialize_layout(root, project_uuid, code_root):
    root, code_root = Path(root).resolve(), Path(code_root).resolve()
    if root.is_relative_to(code_root) or code_root.is_relative_to(root):
        raise ValueError('Choose a managed project directory separate from the application code')
    manifest = root / 'storage.json'
    expected = {'format': 'recording-project-storage', 'version': 1,
                'project_uuid': project_uuid,
                'directories': {key: key for key in DIRECTORIES},
                'logs': {kind: 'logs/' + kind for kind in LOG_FOLDERS},
                'catalog_ref': 'catalog.json', 'database_runtime_ref': 'database/runtime.json'}
    add_cache = False
    if manifest.exists():
        existing = json.loads(manifest.read_text())
        if existing != expected:
            legacy = {**expected, 'directories': {key: key for key in DIRECTORIES if key != 'cache'}}
            if existing != legacy:
                raise ValueError('Managed directory layout differs from version 1; explicit reconciliation required')
            add_cache = True  # Exact known additive migration; never remap existing paths.
    for key in DIRECTORIES:
        managed_directory(root, key)
    for kind in LOG_FOLDERS:
        log_dir(root, kind)
    if add_cache:
        write_json(log_dir(root, 'storage') / 'derived-cache-layout.json', {
            'operation': 'add_derived_cache_directory', 'previous_layout': existing,
            'target_layout': expected, 'scientific_files_changed': False})
    if not manifest.exists() or add_cache:
        write_json(manifest, expected)
    return expected


def migrate_legacy_logs(root):
    """One-time relocation preserving historical audit paths through aliases."""
    root = Path(root).resolve()
    moved = []
    for old_name, kind in [('jobs', 'imports'), ('app-jobs', 'app-jobs'), ('app-errors', 'errors')]:
        old, target = root / old_name, log_dir(root, kind)
        if not old.exists() or old.is_symlink():
            continue
        if any(target.iterdir()):
            raise ValueError(f'Cannot relocate {old_name}: destination already contains files')
        target.rmdir()  # Only the just-created, empty destination.
        old.rename(target)
        old.symlink_to(target.relative_to(root), target_is_directory=True)
        moved.append({'from': old_name, 'to': str(target.relative_to(root)), 'legacy_alias': True})
    return moved


class ManagedStorage:
    def __init__(self, root, project_uuid, code_root):
        self.root, self.code_root = Path(root).resolve(), Path(code_root).resolve()
        self.layout = initialize_layout(self.root, project_uuid, self.code_root)

    def directory(self, relative):
        relative = Path(relative or '.')
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Browse only paths inside this managed project')
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Symbolic links are shown as references, not traversed')
        if not current.resolve().is_relative_to(self.root):
            raise ValueError('Path leaves the managed project')
        if current == self.root / 'database/mysql' or (self.root / 'database/mysql') in current.parents:
            raise ValueError('MySQL storage is managed by the database service, not the file browser')
        if not current.is_dir():
            raise ValueError('Choose a managed directory')
        return current

    def files(self, relative='', offset=0, limit=100):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 200:
            raise ValueError('Use a nonnegative offset and page size 1–200')
        folder = self.directory(relative)
        entries = []
        for entry in folder.iterdir():
            stat = entry.lstat()
            kind = 'symlink' if entry.is_symlink() else 'directory' if entry.is_dir() else 'file'
            path = str(entry.relative_to(self.root))
            restricted = path == 'database/mysql'
            entries.append({'name': entry.name, 'path': path,
                'type': 'restricted' if restricted else kind,
                'browseable': kind == 'directory' and not restricted,
                'size_bytes': stat.st_size if kind == 'file' else None,
                'modified_at': dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).isoformat()})
        entries.sort(key=lambda e: (e['type'] != 'directory', e['name'].casefold()))
        path = str(folder.relative_to(self.root))
        return {'path': '' if path == '.' else path,
                'parent': None if folder == self.root else '' if folder.parent == self.root else str(folder.parent.relative_to(self.root)),
                'total': len(entries), 'offset': offset, 'limit': limit,
                'entries': entries[offset:offset + limit], 'has_more': offset + limit < len(entries)}

    def describe(self, config, sources):
        provider = config.get('connection', {}).get('credential_provider', {})
        container = provider.get('container')
        database = {'adapter': config.get('adapter'), 'database': config.get('database'),
                    'workspace_database': config.get('workspace_database'), 'container': container,
                    'storage_path': None, 'status': 'unavailable'}
        if provider.get('kind') == 'native-project':
            from workspace_native_mysql import connection_parameters
            database.update(storage_path=str(self.root / 'database/mysql'), managed=True,
                            runtime='bundled-mysql', container=None)
            try:
                connection_parameters(self.root)
                database['status'] = 'running'
            except (OSError, ValueError):
                database['status'] = 'stopped'
        if container:
            result = subprocess.run(['docker', 'inspect', '--format',
                '{"mounts":{{json .Mounts}},"running":{{json .State.Running}}}', container],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                runtime = json.loads(result.stdout)
                mount = next((m for m in runtime['mounts'] if m['Destination'] == '/var/lib/mysql'), None)
                if mount:
                    database.update(storage_path=mount['Source'],
                        status='running' if runtime['running'] else 'stopped',
                        managed=Path(mount['Source']).resolve() == self.root / 'database/mysql')
        refs = []
        for source in sources:
            path = Path(source['source_path']).resolve()
            refs.append({'filename': source.get('filename', path.name), 'path': str(path),
                         'location': 'managed' if path.is_relative_to(self.root) else 'external',
                         'exists': path.is_file(), 'source_sha256': source['source_sha256']})
        return {'root': str(self.root), 'code_root': str(self.code_root),
                'project_uuid': self.layout['project_uuid'], 'layout_version': 1,
                'sections': [{'key': key, 'label': label, 'path': key, 'description': description}
                             for key, (label, description) in DIRECTORIES.items()],
                'database': database, 'sources': refs}
