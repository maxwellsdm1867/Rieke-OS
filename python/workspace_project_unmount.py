"""Exact catalog detachment, with owned-service close or conservative refusal."""
from contextlib import ExitStack
from pathlib import Path
import fcntl
import json
import os
import sys
from http.client import HTTPConnection, HTTPException
from urllib.parse import urlsplit
from flask import jsonify
from workspace_startup_registry import read_project_index, unmount_project_record


def launcher_url():
    return 'http://127.0.0.1:' + str(int(os.environ.get('RIEKE_DESKTOP_LAUNCHER_PORT',
        os.environ.get('RIEKE_LAUNCHER_PORT', '8766')))) + '/'


def _desktop_chooser_headers(port):
    """The packaged chooser directly owns its child project processes."""
    import psutil
    try:
        child = psutil.Process()
        owner = child.parent()
        command, own_command = owner.cmdline(), child.cmdline()
        def argument(arguments, flag):
            if arguments.count(flag) != 1:
                raise ValueError('Desktop owner argument is missing or ambiguous')
            return arguments[arguments.index(flag) + 1]
        entry = str(Path(__file__).with_name('workspace_desktop.py').resolve())
        if (owner.pid <= 1 or owner.uids().real != os.getuid()
                or Path(owner.exe()).resolve() != Path(sys.executable).resolve()
                or entry not in command[1:3] or '-c' in command[1:3] or '--project-dir' in command
                or argument(command, '--port') != str(port)
                or Path(argument(command, '--user-state')).resolve() != Path(os.environ['RIEKE_DESKTOP_USER_STATE']).resolve()
                or argument(command, '--session-id') != argument(own_command, '--session-id')
                or not any(connection.status == psutil.CONN_LISTEN
                           and connection.laddr.ip == '127.0.0.1' and connection.laddr.port == port
                           for connection in owner.net_connections(kind='tcp'))):
            raise ValueError('Desktop chooser ownership is unavailable')
        return {'X-Rieke-Desktop-Capability': os.environ['RIEKE_DESKTOP_CAPABILITY']}
    except (psutil.Error, AttributeError, IndexError, KeyError) as error:
        raise ValueError('Desktop chooser ownership is unavailable') from error


def require_ready_launcher():
    """Prove the chooser and its page are reachable before releasing a project.

    Use direct loopback HTTP without proxies or redirects. Desktop requests use
    the existing private capability; it must never follow a redirect elsewhere.
    A port number alone (including the development default) proves nothing.
    """
    try:
        destination = launcher_url()
        port = urlsplit(destination).port
        if port is None or not 1024 <= port <= 65535:
            raise ValueError('Invalid chooser port')
        headers = {}
        if os.environ.get('RIEKE_DESKTOP_MODE') == '1':
            headers = _desktop_chooser_headers(port)
        def read(path, limit):
            connection = HTTPConnection('127.0.0.1', port, timeout=2)
            try:
                connection.request('GET', path, headers=headers)
                response = connection.getresponse()
                payload = response.read(limit + 1)
                if response.status != 200 or len(payload) > limit:
                    raise ValueError('Chooser did not return a ready page')
                return response.getheader('Content-Type', ''), payload
            finally:
                connection.close()
        _, payload = read('/api/health', 65536)
        health = json.loads(payload)
        if (not isinstance(health, dict) or health.get('status') != 'ready'
                or health.get('launcher') is not True or health.get('project_uuid') is not None):
            raise ValueError('Destination is not a project chooser')
        content_type, page = read('/', 512 * 1024)
        if 'text/html' not in content_type or b'id="root"' not in page or b'<script' not in page:
            raise ValueError('Chooser app page is unavailable')
        return destination
    except (OSError, HTTPException, ValueError) as error:
        raise ValueError('The project chooser is unavailable. Keep this window open, open the project chooser, then retry unmount. Nothing was detached; files and database are retained.') from error


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
        try:
            destination = require_ready_launcher()
        except ValueError as error:
            return jsonify(error=str(error)), 409
        def detach_after_close():
            try:
                unmount_project_record(record)
            except Exception:
                app.logger.exception('Closed project could not be detached from the catalog')
                # The database is closed: never resume scientific handlers or
                # call this a successful detach. The chooser can retry safely.
                return jsonify(state='closed', unmounted=False, launcher_url=destination,
                               error='Project closed, but its mounted entry could not be saved. Retry unmount from the project chooser. Files and database are retained.'), 507
            return jsonify(state='unmounted', closed=True, path=path, project_uuid=identity,
                           launcher_url=destination), 200
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
