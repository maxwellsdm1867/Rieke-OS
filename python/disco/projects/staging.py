"""Owned staging folders for transfer, verification and migration.

Each ``.rieke-transfer-*``, ``.rieke-verify-*`` and ``.rieke-migration-*``
folder is created here with an owner file (PID, process creation time and an
operation id) and is recorded in a small per-user registry beside the project
index. A sweep removes only registered folders whose owner file still matches
the registry and whose owner process is provably gone (``runtime_state``). A
verify folder's private database is stopped through ``stop_native_database``
first. Unregistered folders, folders without a matching owner file, and folders
whose database cannot be stopped are never deleted; they are reported instead.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import uuid

OWNER_FILE = '.disco-staging-owner.json'
PREFIXES = ('.rieke-transfer-', '.rieke-verify-', '.rieke-migration-')
_REGISTRY_NAME = 'staging-registry.json'
_LOCK_NAME = 'staging-registry.lock'
_last_report = {'removed': [], 'retained': []}
_report_lock = threading.Lock()


def _directory():
    from workspace_startup_registry import project_index_path
    return project_index_path().parent


@contextlib.contextmanager
def _locked():
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / _LOCK_NAME
    if lock.is_symlink():
        raise ValueError('Staging registry lock cannot be a symbolic link')
    with lock.open('a') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield directory / _REGISTRY_NAME


def _read(path):
    if path.is_symlink():
        raise ValueError('Staging registry cannot be a symbolic link')
    if not path.exists():
        return {'version': 1, 'folders': []}
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Staging registry is too large')
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('folders'), list)
            or any(not isinstance(item, dict) or not isinstance(item.get('path'), str) for item in value['folders'])):
        raise ValueError('Staging registry is invalid')
    return value


def _write(path, value):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_registry():
    with _locked() as path:
        return _read(path)


def create_staging(parent, prefix, operation):
    """Create an owned staging folder after sweeping provably abandoned ones."""
    if prefix not in PREFIXES:
        raise ValueError('Unsupported staging folder prefix')
    from disco.projects.runtime_state import current_process_created
    with contextlib.suppress(OSError, ValueError):
        sweep_registered_staging()
    with _locked() as registry:
        value = _read(registry)
        folder = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()
        owner = {'version': 1, 'pid': os.getpid(), 'process_created': current_process_created(),
                 'operation': operation, 'operation_id': str(uuid.uuid4()),
                 'created_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            _write(folder / OWNER_FILE, owner)
            value['folders'].append({'path': str(folder), **owner})
            _write(registry, value)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return folder


def release_owner(folder):
    """Remove the owner file before a staging folder's contents are published."""
    (Path(folder) / OWNER_FILE).unlink(missing_ok=True)


def forget_staging(folder):
    """Drop the registry record once the folder was published or removed."""
    with _locked() as registry:
        value = _read(registry)
        remaining = [item for item in value['folders'] if item['path'] != str(Path(folder).resolve())]
        if len(remaining) != len(value['folders']):
            value['folders'] = remaining
            _write(registry, value)


def discard_staging(folder):
    """Remove this process's own staging folder and its registry record."""
    folder = Path(folder)
    if folder.exists() and not folder.is_symlink():
        shutil.rmtree(folder)
    forget_staging(folder)


def _owner_alive(owner):
    from disco.projects.runtime_state import recorded_process_alive
    return recorded_process_alive(owner.get('pid'), owner.get('process_created'))


def _stop_databases(folder):
    """Stop any verify-folder database; True only when none remains running."""
    from disco.projects import runtime_state
    for project in sorted(path for path in folder.iterdir() if path.is_dir() and not path.is_symlink()):
        if not (project / 'database').is_dir():
            continue
        state = runtime_state.project_runtime_state(project)
        if state['state'] == runtime_state.RUNNING_OWNED:
            import workspace_native_mysql
            with contextlib.suppress(OSError, ValueError):
                workspace_native_mysql.stop_native_database(project)
            state = runtime_state.project_runtime_state(project)
        if state['state'] in runtime_state.RUNNING:
            return False
    return True


def sweep_registered_staging():
    """Remove registered folders whose owner process is provably gone."""
    removed, retained = [], []
    with _locked() as registry:
        value = _read(registry)
        kept = []
        for item in value['folders']:
            folder = Path(item['path'])
            def retain(reason):
                kept.append(item)
                retained.append({'path': item['path'], 'operation': item.get('operation'), 'reason': reason})
            try:
                if not folder.exists() and not folder.is_symlink():
                    continue  # Already published or removed by its owner.
                if folder.is_symlink() or not folder.is_dir() or not folder.name.startswith(PREFIXES):
                    retain('not_a_staging_folder'); continue
                owner_path = folder / OWNER_FILE
                if owner_path.is_symlink() or not owner_path.is_file():
                    retain('owner_file_missing'); continue
                owner = json.loads(owner_path.read_text())
                if not isinstance(owner, dict) or any(owner.get(key) != item.get(key) for key in ('operation_id', 'pid', 'process_created')):
                    retain('owner_file_mismatch'); continue
                if _owner_alive(owner):
                    retain('owner_running'); continue
                if folder.name.startswith('.rieke-verify-') and not _stop_databases(folder):
                    retain('database_running'); continue
                shutil.rmtree(folder)
                removed.append(item['path'])
            except (OSError, ValueError) as error:
                retain('unavailable: ' + type(error).__name__)
        if len(kept) != len(value['folders']):
            value['folders'] = kept
            _write(registry, value)
    report = {'removed': removed, 'retained': retained}
    with _report_lock:
        _last_report.update(removed=list(removed), retained=list(retained))
    return report


def last_report():
    """Most recent sweep outcome for health displays; never triggers I/O."""
    with _report_lock:
        return {'removed': list(_last_report['removed']), 'retained': [dict(item) for item in _last_report['retained']]}


def sweep_in_background():
    """Startup sweep that never delays the launcher (staging may be on slow drives)."""
    def run():
        with contextlib.suppress(Exception):
            sweep_registered_staging()
    thread = threading.Thread(target=run, name='disco-staging-sweep', daemon=True)
    thread.start()
    return thread
