"""Exact catalog detachment, with owned-service close or conservative refusal."""
from contextlib import ExitStack
from pathlib import Path
import fcntl
import json
import os
from flask import jsonify
from workspace_startup_registry import read_project_index, unmount_project_record


def launcher_url():
    return 'http://127.0.0.1:' + str(int(os.environ.get('RIEKE_DESKTOP_LAUNCHER_PORT',
        os.environ.get('RIEKE_LAUNCHER_PORT', '8766')))) + '/'


def unmount_project(app, inventory, body, *, current=None):
    path, identity = body['path'], body['project_uuid']
    record = next((item for item in inventory['projects'] if item['path'] == path and item['uuid'] == identity), None)
    if record is None:
        prior = next((item for item in read_project_index().get('unmounted', [])
                      if item['path'] == path and item['project_uuid'] == identity), None)
        if prior:
            return jsonify(state='unmounted', already_unmounted=True, path=path, project_uuid=identity)
        return jsonify(error='Project list changed; refresh it before unmounting.'), 409
    if app.extensions.get('app_active_writers', lambda: False)():
        return jsonify(error='Wait for the current import, export or project transfer to finish before unmounting.'), 409
    active = current is not None and str(current) == path
    if active:
        close = app.extensions.get('close_project_for_unmount')
        if not close or 'shutdown_project_server' not in app.extensions:
            return jsonify(error='This project service cannot verify a clean close. Close it through its owner before unmounting from the project chooser.'), 409
        def detach_after_close():
            try:
                unmount_project_record(record)
            except Exception:
                app.logger.exception('Closed project could not be detached from the catalog')
                # The database is closed: never resume scientific handlers or
                # call this a successful detach. The chooser can retry safely.
                return jsonify(state='closed', unmounted=False, launcher_url=launcher_url(),
                               error='Project closed, but its mounted entry could not be saved. Retry unmount from the project chooser. Files and database are retained.'), 507
            return jsonify(state='unmounted', closed=True, path=path, project_uuid=identity,
                           launcher_url=launcher_url()), 200
        return close(detach_after_close)
    # A missing drive can be forgotten without following its path or altering it.
    # A present project must not be detached behind an owning service's back.
    directory = Path(path)
    try:
        with ExitStack() as stack:
            owner = app.extensions.get('project_catalog_owner')
            if owner:
                stack.enter_context(owner.lock)
                if owner.draining or owner.database_operation_records() or any(item.get('project_path') == path for item in owner.records()):
                    raise ValueError('This project is owned by the desktop service. Open it and unmount there after its operations finish')
            if directory.is_symlink():
                raise ValueError('Project folder changed; refresh its location before unmounting')
            if directory.is_dir():
                for name in ('logs/workspace-server.lock', '.app-state-session.lock'):
                    lock_path = directory / name
                    if lock_path.is_symlink():
                        raise ValueError('Project ownership lock is unavailable')
                    if lock_path.exists() or (name.startswith('logs/') and lock_path.parent.is_dir()):
                        handle = stack.enter_context(lock_path.open('a'))
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Fail closed for old services that predate session locks, and
                # for a native database left running without its app service.
                import psutil
                for name in ('logs/workspace-server.json', 'database/native-runtime.json'):
                    runtime_path = directory / name
                    if runtime_path.is_symlink():
                        raise ValueError('Project service ownership is unavailable')
                    if runtime_path.exists():
                        if runtime_path.stat().st_size > 65536:
                            raise ValueError('Project service ownership record is invalid')
                        runtime = json.loads(runtime_path.read_text())
                        pid = runtime.get('pid')
                        if type(pid) is not int or pid <= 1:
                            raise ValueError('Project service ownership record is invalid')
                        if psutil.pid_exists(pid):
                            raise ValueError('This project has a running service. Open it and unmount there after its operations finish')
                # Recheck identity after acquiring the opening/session locks.
                if record.get('available'):
                    from workspace_projects import _project_record
                    if _project_record(directory)['uuid'] != identity:
                        raise ValueError('Project identity changed; refresh before unmounting')
            unmount_project_record(record)
    except (OSError, ValueError) as error:
        return jsonify(error=str(error) if not isinstance(error, BlockingIOError) else
                       'This project is owned by an active operation. Wait for it to finish, then open the project and unmount there.'), 409
    return jsonify(state='unmounted', path=path, project_uuid=identity)
