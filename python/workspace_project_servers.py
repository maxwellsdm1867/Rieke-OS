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
    write_json(server_record(project_dir), {'project_uuid': identity, 'port': port, 'pid': os.getpid()})


def ready_url(project_dir, identity):
    try:
        record = json.loads(server_record(project_dir).read_text())
        if not isinstance(record, dict):
            return None
        port = record.get('port')
        if record.get('project_uuid') != identity or type(port) is not int or not 1024 <= port <= 65535:
            return None
        url = f'http://127.0.0.1:{port}'
        with urlopen(url + '/api/health', timeout=0.4) as response:
            value = json.load(response)
        if isinstance(value, dict) and value.get('status') == 'ready' and value.get('project_uuid') == identity:
            return url + '/'
    except (OSError, ValueError):
        pass
    return None


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
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
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
