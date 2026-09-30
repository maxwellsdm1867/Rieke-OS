"""Open each DataJoint project in its own process (connection state is global)."""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from recording_workspace import write_json
from workspace_projects import list_projects, list_managed_projects
from workspace_startup_registry import remember_project_result


def server_record(project_dir):
    return Path(project_dir) / 'logs' / 'workspace-server.json'


def _close_failed_native_start(directory):
    """A failed app start must not strand its newly opened private database."""
    try:
        config = json.loads((directory / 'catalog.json').read_text())
        if config.get('connection', {}).get('credential_provider', {}).get('kind') == 'native-project':
            session_file = directory / '.app-state-session.lock'
            if session_file.is_symlink():
                return
            with session_file.open('a') as session:
                fcntl.flock(session.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                from workspace_native_mysql import stop_native_database
                stop_native_database(directory)
    except (OSError, ValueError):
        pass  # Preserve the startup error; runtime diagnostics remain in the project.


def write_server_record(project_dir, identity, port):
    from workspace_updates import release_metadata
    write_json(server_record(project_dir), {'project_uuid': identity, 'port': port, 'pid': os.getpid(),
        'project_path': str(Path(project_dir).resolve()), 'app_release': release_metadata()['version']})


def ready_url(project_dir, identity):
    try:
        record = json.loads(server_record(project_dir).read_text())
        if not isinstance(record, dict):
            return None
        port = record.get('port')
        if record.get('project_uuid') != identity or type(port) is not int or not 1024 <= port <= 65535:
            return None
        if record.get('project_path') != str(Path(project_dir).resolve()):
            return None
        url = f'http://127.0.0.1:{port}'
        with urlopen(url + '/api/health', timeout=0.4) as response:
            value = json.load(response)
        if isinstance(value, dict) and value.get('status') == 'ready' and value.get('project_uuid') == identity:
            if value.get('project_path') != str(Path(project_dir).resolve()):
                return None
            if os.environ.get('RIEKE_INSTALLATION_ROOT'):
                from workspace_updates import release_metadata
                version = release_metadata()['version']
                if (record.get('app_release') != version or value.get('app_release') != version
                        or record.get('project_path') != str(Path(project_dir).resolve())):
                    raise RuntimeError('A project service from a different release or folder is still active. Close it before reopening.')
            return url + '/'
    except (OSError, ValueError):
        pass
    return None


def project_server_port(project_dir, identity):
    """Keep this local project's browser origin when its last port is available."""
    previous = None
    path = server_record(project_dir)
    try:
        if not path.is_symlink() and path.is_file() and path.stat().st_size <= 65536:
            record = json.loads(path.read_text())
            if (isinstance(record, dict) and record.get('project_uuid') == identity
                    and record.get('project_path') == str(Path(project_dir).resolve())
                    and type(record.get('port')) is int and 1024 <= record['port'] <= 65535):
                previous = record['port']
    except (OSError, ValueError):
        pass
    if previous is not None:
        with socket.socket() as listener:
            # Werkzeug also uses SO_REUSEADDR; allow its normal TIME_WAIT sockets
            # after Close without ever displacing an actively listening server.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(('127.0.0.1', previous))
                return previous
            except OSError:
                pass
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def open_project(project_dir, identity, retinanalysis_dir, *, timeout=300, managed=False):
    if os.environ.get('RIEKE_DESKTOP_MODE') == '1':
        from workspace_desktop import desktop_open_project
        return desktop_open_project(project_dir, identity, retinanalysis_dir, timeout=timeout, managed=managed)
    registry = list_managed_projects(project_dir) if managed else list_projects(project_dir)
    selected_path = str(Path(project_dir).expanduser().resolve())
    project = next((row for row in registry['projects'] if row['uuid'] == identity and row['available']
                    and (managed or row['path'] == selected_path)), None)
    if project is None:
        raise ValueError('Select an available registered project')
    directory = Path(project['path'])
    logs = directory / 'logs'
    logs.mkdir(exist_ok=True)
    with (logs / 'workspace-server.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = ready_url(directory, identity)
        if existing:
            return remember_project_result(directory, {'url': existing, 'project_uuid': identity}, set_last=True)
        from workspace_project_database import ensure_project_database
        ensure_project_database(directory)
        config = json.loads((directory / 'catalog.json').read_text())
        if config.get('connection', {}).get('credential_provider', {}).get('kind') == 'native-project':
            try:
                from workspace_portability import rebase_project_paths
                rebase_project_paths(directory)
            except Exception:
                _close_failed_native_start(directory)
                raise
        port = project_server_port(directory, identity)
        with (logs / 'workspace-launch.log').open('ab') as log:
            command = [sys.executable, str(Path(__file__).with_name('workspace_api.py')),
                '--project-dir', str(directory), '--retinanalysis', str(Path(retinanalysis_dir).resolve()),
                '--port', str(port)]
            if os.environ.get('RIEKE_INSTALLATION_ROOT'):
                # Detached project services retain their own shared installation
                # lock after the chooser exits. Activation cannot race their writes.
                command = [sys.executable, str(Path(__file__).with_name('workspace_updates.py')),
                    '--installation', os.environ['RIEKE_INSTALLATION_ROOT'], 'hold', '--', *command]
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                _close_failed_native_start(directory)
                raise ValueError('Project could not start. See logs/workspace-launch.log in that project.')
            url = ready_url(directory, identity)
            if url:
                return remember_project_result(directory, {'url': url, 'project_uuid': identity}, set_last=True)
            time.sleep(0.2)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Do not stop SQL underneath a child that has not exited.
            raise ValueError('Project startup timed out and its process is still stopping. Check the launch log before retrying.') from None
        _close_failed_native_start(directory)
        raise ValueError('Project startup timed out. See logs/workspace-launch.log; retry after checking its database.')
