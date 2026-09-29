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
from workspace_startup_registry import remember_project


def server_record(project_dir):
    return Path(project_dir) / 'logs' / 'workspace-server.json'


def write_server_record(project_dir, identity, port):
    write_json(server_record(project_dir), {'project_uuid': identity, 'project_path': str(Path(project_dir).resolve()), 'port': port, 'pid': os.getpid()})


def ready_url(project_dir, identity):
    try:
        record = json.loads(server_record(project_dir).read_text())
        if not isinstance(record, dict):
            return None
        physical_root = str(Path(project_dir).resolve())
        if record.get('project_path', physical_root) != physical_root:
            return None
        port = record.get('port')
        if record.get('project_uuid') != identity or type(port) is not int or not 1024 <= port <= 65535:
            return None
        url = f'http://127.0.0.1:{port}'
        with urlopen(url + '/api/health', timeout=0.4) as response:
            value = json.load(response)
    except (OSError, ValueError):
        return None
    if isinstance(value, dict) and value.get('status') == 'ready' and value.get('project_uuid') == identity:
        if 'project_path' not in value:
            raise ValueError('An older server for this project is still running, but its project folder cannot be verified. '
                             'Stop the existing project server and reopen the project with the updated application. '
                             'No second server was started.')
        if value.get('project_path') == physical_root:
            return url + '/'
    return None


def choose_project_port(project_dir, identity):
    """Reuse this project's browser origin across restarts when available.

    localStorage is scoped to an origin, so choosing a new random port each time
    loses author and device preferences even though the project UUID is stable.
    A busy or untrusted saved port falls back to a fresh loopback-only port.
    """
    preferred = 0
    try:
        record = json.loads(server_record(project_dir).read_text())
        candidate = record.get('port') if isinstance(record, dict) else None
        if record.get('project_uuid') == identity and type(candidate) is int and 1024 <= candidate <= 65535:
            preferred = candidate
    except (OSError, ValueError, AttributeError):
        pass
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(('127.0.0.1', preferred))
        except OSError:
            if not preferred:
                raise
            listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def open_project(project_dir, identity, retinanalysis_dir, *, timeout=300, managed=False):
    registry = list_managed_projects(project_dir) if managed else list_projects(project_dir)
    project = next((row for row in registry['projects'] if row['uuid'] == identity and row['available']), None)
    if project is None:
        raise ValueError('Select an available registered project')
    directory = Path(project['path'])
    logs = directory / 'logs'
    logs.mkdir(exist_ok=True)
    with (logs / 'workspace-server.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = ready_url(directory, identity)
        if existing:
            remember_project(directory.parent, identity)
            return {'url': existing, 'project_uuid': identity}
        from workspace_project_database import ensure_project_database
        ensure_project_database(directory)
        port = choose_project_port(directory, identity)
        with (logs / 'workspace-launch.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('workspace_api.py')),
                '--project-dir', str(directory), '--retinanalysis', str(Path(retinanalysis_dir).resolve()),
                '--port', str(port)], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError('Project could not start. See logs/workspace-launch.log in that project.')
            url = ready_url(directory, identity)
            if url:
                remember_project(directory.parent, identity)
                return {'url': url, 'project_uuid': identity}
            time.sleep(0.2)
        process.terminate()
        raise ValueError('Project startup timed out. See logs/workspace-launch.log; retry after checking its database.')
