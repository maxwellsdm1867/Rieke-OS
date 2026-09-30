"""Authenticated production WSGI services for the immutable desktop runtime.

The Electron coordinator supplies the private capability through the environment.
This entry point never installs dependencies or terminates scientific workers.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
# Factories import this module by name. Share the process-local supervisor when
# the owned entry point was executed as a script rather than imported.
if __name__ == '__main__':
    sys.modules['workspace_desktop'] = sys.modules[__name__]

from flask import jsonify, request
from werkzeug.wrappers import Response
from werkzeug.wsgi import ClosingIterator

_CONTROL = '/api/desktop/'
_SERVICES = None


class DesktopProjectCompatibilityError(ValueError):
    """A source project requires an explicit copy before desktop activation."""
    code = 'legacy_project_requires_migration'

    def __init__(self):
        super().__init__('This project uses a source database. Create a desktop copy in a separate folder; the original project and database will remain unchanged.')


def acquire_project_session(project):
    """Exclude other app sessions before starting or changing a project DB."""
    project_lock = Path(project) / '.app-state-session.lock'
    if project_lock.is_symlink():
        raise ValueError('Project session lock cannot be a symbolic link')
    session_lock = project_lock.open('a')
    try:
        fcntl.flock(session_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        session_lock.close()
        raise ValueError('Another app or recovery owns this project; close it before opening') from None
    return session_lock


def _atomic_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Desktop state cannot be a symbolic link')
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as output:
            os.chmod(temporary, 0o600)
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class DesktopBoundary:
    """Authenticate before Flask; retain admission through response iteration.

    Every request is counted, including GETs that may write projection caches.
    Asynchronous producers supply explicit busy/pause callbacks; request counts
    alone never establish permission to stop a database.
    """
    def __init__(self, app, *, port, capability, identity, services=None, deadline=30):
        if not isinstance(capability, str) or len(capability) < 32:
            raise ValueError('A private desktop capability is required')
        self.app, self.capability, self.identity = app, capability, identity
        self.renderer_session = hashlib.sha256((capability + ':renderer').encode()).hexdigest()
        self.origin = f'http://127.0.0.1:{port}'
        self.condition = threading.Condition()
        self.active = 0
        self.draining = False
        self.drained = False
        self.deadline = deadline
        self.services = services
        self.stop_callback = None
        self.stop_scheduled = False
        self.operation_lock = threading.RLock()
        self._routes()

    def _busy(self):
        return (any(self.app.extensions.get(name, lambda: False)()
                    for name in ('app_active_writers', 'project_active_writers'))
                or bool(self.services and self.services.database_operation_records()))

    def _pause(self):
        inbox = self.app.extensions.get('h5_inbox')
        if inbox:
            inbox.stop()

    def resume(self):
        with self.operation_lock:
            if self.stop_scheduled:
                raise ValueError('Service shutdown was already acknowledged')
            with self.condition:
                self.draining = self.drained = False
            if self.services:
                with self.services.lock:
                    self.services.draining = False
            inbox = self.app.extensions.get('h5_inbox')
            if inbox:
                inbox.start()

    def drain(self):
        with self.operation_lock:
            with self.condition:
                if self.drained:
                    return True
                if self._busy():
                    return False
                self.draining = True
                if not self.condition.wait_for(lambda: self.active == 0, timeout=self.deadline):
                    self.draining = False
                    return False
            try:
                self._pause()
                if self._busy():
                    self.resume()
                    return False
                if self.services and not self.services.drain(self.deadline):
                    self.resume()
                    return False
            except Exception:
                self.resume()
                raise
            self.drained = True
            return True

    def _routes(self):
        @self.app.get(_CONTROL + 'health')
        def desktop_health():
            return jsonify(**self.identity, ready=not self.draining,
                           draining=self.draining,
                           services=self.services.records() if self.services else [])

        def empty_control():
            return not request.args and request.get_json(silent=True) == {}

        @self.app.post(_CONTROL + 'drain')
        def desktop_drain():
            if not empty_control():
                return jsonify(error='Drain requires an empty object'), 400
            try:
                if not self.drain():
                    return jsonify(ready=False, busy=True, error='Scientific operations are still active'), 409
            except Exception:
                self.app.logger.exception('Desktop drain could not be acknowledged')
                return jsonify(ready=False, error='Service drain could not be verified'), 409
            return jsonify(ready=True, drained=True)

        @self.app.post(_CONTROL + 'resume')
        def desktop_resume():
            if not empty_control() or self.stop_scheduled:
                return jsonify(error='Service cannot resume'), 409
            self.resume()
            return jsonify(ready=True)

        @self.app.post(_CONTROL + 'stop')
        def desktop_stop():
            if not empty_control() or not self.drained or self._busy() or not self.stop_callback:
                return jsonify(error='All writers must acknowledge drain before stop'), 409
            try:
                stop_database = self.app.extensions.get('desktop_stop_database')
                if stop_database:
                    stop_database()
                if self.services and self.services.records():
                    raise ValueError('Owned project services have not exited')
            except Exception:
                self.app.logger.exception('Desktop database shutdown was not acknowledged')
                return jsonify(error='Database shutdown could not be verified'), 409
            # Give Waitress the response before closing its sockets. The main
            # process awaits actual child exit, not this HTTP acknowledgement.
            self.stop_scheduled = True
            threading.Timer(.25, self.stop_callback).start()
            return jsonify(ready=True, stopped=True), 202

        @self.app.post(_CONTROL + 'open-project')
        def desktop_open():
            body = request.get_json(silent=True)
            if not self.services or request.args or not isinstance(body, dict) or set(body) != {'directory', 'project_uuid'}:
                return jsonify(error='Select an existing project directory and identity'), 400
            from workspace_projects import _project_record
            directory = Path(body['directory']).resolve(strict=True)
            record = _project_record(directory)
            if record['uuid'] != body['project_uuid']:
                return jsonify(error='Project identity changed'), 409
            return jsonify(self.services.open(directory, record['uuid'], None, 300))

        @self.app.post(_CONTROL + 'authorize-project')
        def desktop_authorize_project():
            body = request.get_json(silent=True)
            if (not self.services or request.args or not isinstance(body, dict)
                    or set(body) != {'port'} or type(body['port']) is not int):
                return jsonify(error='Project authorization requires a registered port'), 400
            record = next((item for item in self.services.records() if item['port'] == body['port']), None)
            if not record or record.get('bound') is not True or record.get('recovery_required'):
                return jsonify(error='Project service ownership is unavailable'), 409
            try:
                health = self.services.call(record, 'health')
                if health.get('ready') is not True:
                    raise ValueError('Project service is not ready')
            except Exception:
                return jsonify(error='Project process and listener ownership could not be verified'), 409
            return jsonify(record=record, health=health)

        @self.app.post(_CONTROL + 'database-operation/start')
        def desktop_database_start():
            body = request.get_json(silent=True)
            if not self.services or request.args or not isinstance(body, dict) or set(body) != {'project_path'}:
                return jsonify(error='Database operation requires an owned project path'), 400
            return jsonify(operation_id=self.services.begin_database_operation(body['project_path']))

        @self.app.post(_CONTROL + 'database-operation/finish')
        def desktop_database_finish():
            body = request.get_json(silent=True)
            if not self.services or request.args or not isinstance(body, dict) or set(body) != {'operation_id', 'failed'} or type(body['failed']) is not bool:
                return jsonify(error='Database completion requires an operation identity'), 400
            self.services.finish_database_operation(body['operation_id'], failed=body['failed'])
            return jsonify(ready=True)

        if 'desktop_stop_database' in self.app.extensions:
            @self.app.post('/api/project/close')
            def desktop_close_project():
                if not empty_control():
                    return jsonify(error='Close requires an empty object'), 400
                if not self.drain():
                    return jsonify(error='Scientific operations are still active'), 409
                result = desktop_stop()
                if isinstance(result, tuple) and result[1] == 202:
                    response = result[0]
                    response.set_data(json.dumps({**response.get_json(), 'state': 'closed',
                        'launcher_url': 'http://127.0.0.1:' + os.environ['RIEKE_DESKTOP_LAUNCHER_PORT'] + '/'}))
                return result

    def __call__(self, environ, start_response):
        host = environ.get('HTTP_HOST', '')
        origin = environ.get('HTTP_ORIGIN')
        supplied = environ.get('HTTP_X_RIEKE_DESKTOP_CAPABILITY', '')
        renderer_session = environ.get('HTTP_X_RIEKE_DESKTOP_SESSION', '')
        control_authorized = supplied.isascii() and secrets.compare_digest(supplied, self.capability)
        session_authorized = renderer_session.isascii() and secrets.compare_digest(renderer_session, self.renderer_session)
        if (environ.get('REMOTE_ADDR') != '127.0.0.1'
                or host != self.origin.removeprefix('http://')
                or origin not in (None, self.origin)
                or not (control_authorized or session_authorized)
                or (environ.get('PATH_INFO', '').startswith(_CONTROL) and not control_authorized)):
            return Response('Desktop session authorization required', status=403)(environ, start_response)
        control = environ.get('PATH_INFO', '') in {
            _CONTROL + name for name in ('health', 'drain', 'resume', 'stop')
        } or environ.get('PATH_INFO') == '/api/project/close'
        admitted = False
        if not control:
            with self.condition:
                if self.draining:
                    return Response('Desktop service is draining', status=503)(environ, start_response)
                self.active += 1
                admitted = True
        try:
            response = self.app(environ, start_response)
        except BaseException:
            if admitted:
                with self.condition:
                    self.active -= 1
                    self.condition.notify_all()
            raise
        def finished():
            if admitted:
                with self.condition:
                    self.active -= 1
                    self.condition.notify_all()
        return ClosingIterator(response, finished)


class DesktopServices:
    """Only supervise exact bundled children; never signal a reused PID."""
    def __init__(self, user_state, resources, manifest, session_id, capability, identity):
        self.user_state, self.resources = Path(user_state), Path(resources)
        self.manifest, self.session_id, self.capability = Path(manifest), session_id, capability
        self.identity = identity
        self.path = self.user_state / 'desktop-services.json'
        self.lock = threading.RLock()
        self.children = {}
        self.database_operations = {}
        self.draining = False
        if self.path.exists():
            if self.path.is_symlink() or self.path.stat().st_size > 1024 * 1024:
                raise ValueError('Desktop service registry is invalid')
            previous = json.loads(self.path.read_text())
            if not isinstance(previous, dict) or previous.get('version') != 1 or not isinstance(previous.get('services'), list):
                raise ValueError('Desktop service registry is invalid')
            import psutil
            for record in previous['services']:
                if not isinstance(record, dict) or type(record.get('pid')) is not int:
                    raise ValueError('Desktop service registry is invalid')
                try:
                    process = psutil.Process(record['pid'])
                    # PID existence alone neither authorizes shutdown nor proves
                    # prior scientific operations finished. Matching processes
                    # require recovery; foreign/reused PIDs are not our services.
                    # A zombie cannot serve HTTP, but its independent database
                    # or inherited import worker may still be active. It must
                    # satisfy the same clean receipt checks as any exited child.
                    if (process.status() != psutil.STATUS_ZOMBIE
                            and process.create_time() == record.get('created_at')
                            and str(Path(process.exe()).resolve()) == record.get('executable')):
                        raise ValueError('A previous desktop project service is still alive; recovery must close it before opening projects')
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    if psutil.pid_exists(record['pid']):
                        raise ValueError('A previous service cannot be inspected; preserve it for recovery')
                if not self._clean_database(record):
                    if self._rejected_legacy_preflight(record):
                        continue
                    raise ValueError('A previous project service has no clean database exit receipt; recovery is required before opening projects')
            operations = previous.get('database_operations', [])
            if not isinstance(operations, list):
                raise ValueError('Desktop database operation registry is invalid')
            for operation in operations:
                if not isinstance(operation, dict) or not self._clean_database(operation):
                    raise ValueError('A prior transfer database has no clean exit receipt; recovery is required before opening projects')
        self._save()

    @staticmethod
    def _clean_database(record):
        try:
            owner_path = Path(record['project_path']) / 'database/native-owner.json'
            if owner_path.is_symlink():
                return False
            owner = json.loads(owner_path.read_text())
            if ((Path(record['project_path']) / 'database/native-runtime.json').exists()
                    or (record.get('instance_uuid') is not None and owner.get('instance_uuid') != record['instance_uuid'])):
                return False
            return owner.get('clean_shutdown') is True and owner.get('project_uuid') == record['project_uuid']
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _save(self):
        _atomic_json(self.path, {'version': 1, 'services': [item['record'] for item in self.children.values()],
                                'database_operations': list(self.database_operations.values())})

    @staticmethod
    def _rejected_legacy_preflight(record):
        """Known entry-point legacy rejection happens before native startup."""
        try:
            if record.get('bound') is not False:
                return False
            root = Path(record['project_path'])
            database = root / 'database'
            if root.is_symlink() or database.is_symlink() or (database.exists() and not database.is_dir()):
                return False
            for name in ('native-owner.json', 'native-credentials.json', 'native-runtime.json', 'service.json'):
                artifact = database / name
                if artifact.exists() or artifact.is_symlink():
                    return False
            data = database / 'mysql'
            if data.is_symlink() or (data.exists() and (not data.is_dir() or any(data.iterdir()))):
                return False
            if (root / 'project.json').is_symlink() or (root / 'catalog.json').is_symlink():
                return False
            project = json.loads((root / 'project.json').read_text())
            catalog = json.loads((root / 'catalog.json').read_text())
            provider = catalog['connection']['credential_provider']
            identity = str(uuid.UUID(record['project_uuid']))
            return (project.get('format') == 'recording-project' and project.get('version') == 1
                    and catalog.get('format') == 'recording-catalog-reference' and catalog.get('version') == 1
                    and catalog.get('managed_database') is None
                    and project['project_uuid'] == identity
                    and catalog['project_uuid'] == record['project_uuid']
                    and provider['kind'] == 'docker-container-env'
                    and isinstance(provider.get('container'), str) and bool(provider['container'].strip()))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def begin_database_operation(self, project):
        from workspace_desktop_paths import require_external_data_path
        root = require_external_data_path(project)
        if root.is_relative_to(self.resources):
            raise ValueError('Database operations must remain outside application resources')
        from workspace_native_mysql import _configuration
        _, descriptor = _configuration(root)
        operation_id = str(uuid.uuid4())
        record = {'operation_id': operation_id, 'project_path': str(root), 'project_uuid': descriptor['project_uuid'],
                  'instance_uuid': descriptor['instance_uuid'], 'phase': 'running'}
        with self.lock:
            if self.draining or any(item['project_path'] == str(root) for item in self.database_operations.values()):
                raise ValueError('A database operation is unacknowledged or the desktop is draining')
            self.database_operations[operation_id] = record
            self._save()
        return operation_id

    def finish_database_operation(self, operation_id, *, failed=False):
        with self.lock:
            record = self.database_operations.get(operation_id)
            if record is None:
                raise ValueError('Database operation ownership is unavailable')
            if failed:
                record['phase'] = 'failed_shutdown'
                self._save()
                return
            if not self._clean_database(record):
                raise ValueError('Transfer database did not acknowledge a clean shutdown')
            del self.database_operations[operation_id]
            self._save()

    def database_operation_records(self):
        with self.lock:
            for identity, record in list(self.database_operations.items()):
                if record['phase'] == 'failed_shutdown' and self._clean_database(record):
                    del self.database_operations[identity]
                    self._save()
            return list(self.database_operations.values())

    def records(self):
        with self.lock:
            removed = [key for key, item in self.children.items()
                       if item['process'].poll() is not None and (self._clean_database(item['record'])
                                                                or self._rejected_legacy_preflight(item['record']))]
            for key in removed:
                del self.children[key]
            if removed:
                self._save()
            for item in self.children.values():
                if item['process'].poll() is not None:
                    item['record']['recovery_required'] = True
            return [dict(item['record']) for item in self.children.values()]

    def call(self, record, operation, body=None, timeout=5):
        if record.get('bound') is not True:
            raise ValueError('Owned child has not acknowledged binding its listener')
        import psutil
        process = psutil.Process(record['pid'])
        if (process.create_time() != record['created_at']
                or str(Path(process.exe()).resolve()) != record['executable']):
            raise ValueError('Desktop service process ownership changed')
        url = f"http://127.0.0.1:{record['port']}/api/desktop/{operation}"
        headers = {'X-Rieke-Desktop-Capability': self.capability}
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'X-Workspace-Request': '1'})
        with urlopen(Request(url, data=data, headers=headers), timeout=timeout) as response:
            payload = json.load(response)
        if operation == 'health':
            for key in ('pid', 'session_id', 'project_uuid', 'project_path', 'application_version', 'source_commit'):
                if payload.get(key) != record.get(key):
                    raise ValueError('Desktop service health identity changed')
        return payload

    def open(self, directory, identity, retinanalysis, timeout):
        from workspace_desktop_paths import require_external_data_path
        directory = require_external_data_path(directory)
        catalog = json.loads((directory / 'catalog.json').read_text())
        if catalog.get('connection', {}).get('credential_provider', {}).get('kind') != 'native-project':
            # Reject before spawning/registering a child or touching a source DB.
            raise DesktopProjectCompatibilityError()
        with self.lock:
            if self.draining:
                raise ValueError('Desktop services are draining')
            key = str(directory)
            self.records()
            if key in self.children:
                record = self.children[key]['record']
                if self.call(record, 'health').get('ready'):
                    from workspace_startup_registry import remember_project_path
                    remember_project_path(directory, identity, set_last=True)
                    return {'url': f"http://127.0.0.1:{record['port']}/", 'project_uuid': identity}
                raise ValueError('Project service startup or shutdown is still active')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            log_path = directory / 'logs' / 'workspace-launch.log'
            log_path.parent.mkdir(exist_ok=True)
            if log_path.is_symlink():
                raise ValueError('Project launch log cannot be a symbolic link')
            command = [sys.executable, str(Path(__file__).resolve()), '--resources', str(self.resources),
                       '--manifest', str(self.manifest), '--user-state', str(self.user_state),
                       '--session-id', self.session_id, '--port', str(port), '--project-dir', str(directory)]
            read_fd, ready_fd = os.pipe()
            command.extend(['--ready-fd', str(ready_fd)])
            try:
                with log_path.open('ab') as log:
                    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                               pass_fds=(ready_fd,))
            except BaseException:
                os.close(read_fd)
                raise
            finally:
                os.close(ready_fd)
            import psutil
            record = {**self.identity, 'pid': process.pid, 'port': port, 'session_id': self.session_id,
                      'project_uuid': identity, 'project_path': key,
                      'created_at': psutil.Process(process.pid).create_time(),
                      'executable': str(Path(sys.executable).resolve()), 'bound': False}
            self.children[key] = {'record': record, 'process': process}
            self._save()
            bound = threading.Event()
            packet = {}
            def read_bound_receipt():
                with os.fdopen(read_fd, 'r') as pipe:
                    line = pipe.readline(65537)
                    try:
                        if not line.startswith('RIEKE_DESKTOP_BOUND=') or len(line) > 65536:
                            raise ValueError('Malformed owned child bind receipt')
                        value = json.loads(line.split('=', 1)[1])
                        required = ('pid', 'session_id', 'port', 'project_uuid', 'project_path',
                                    'application_version', 'source_commit')
                        if any(value.get(name) != record.get(name) for name in required):
                            raise ValueError('Owned child bind receipt identity mismatch')
                        packet['valid'] = True
                    except (ValueError, TypeError):
                        packet['valid'] = False
                    finally:
                        bound.set()
            threading.Thread(target=read_bound_receipt, name='rieke-child-bind-receipt', daemon=True).start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                # A startup exception does not prove native database recovery.
                raise ValueError('Project startup failed; inspect its recovery log before retrying')
            if not bound.is_set():
                bound.wait(.2)
                continue
            if not packet.get('valid'):
                raise ValueError('Project listener ownership was not acknowledged; service retained')
            if not record['bound']:
                with self.lock:
                    record['bound'] = True
                    self._save()
            try:
                if self.call(record, 'health', timeout=.5).get('ready'):
                    from workspace_startup_registry import remember_project_path
                    remember_project_path(directory, identity, set_last=True)
                    return {'url': f'http://127.0.0.1:{port}/', 'project_uuid': identity}
            except (OSError, ValueError):
                pass
            time.sleep(.2)
        # Startup may hold a database write; neither terminate nor kill it.
        raise ValueError('Project startup timed out; its service was preserved for recovery')

    def drain(self, timeout):
        with self.lock:
            self.draining = True
            records = self.records()
        prepared = []
        try:
            # Prepare ALL services before permitting any to shut down.
            for record in records:
                if not self.call(record, 'drain', {}, timeout=timeout + 2).get('ready'):
                    raise ValueError('Project service did not acknowledge drain')
                prepared.append(record)
            for record in prepared:
                if not self.call(record, 'stop', {}, timeout=timeout + 2).get('stopped'):
                    raise ValueError('Project service did not acknowledge stop')
            deadline = time.monotonic() + timeout
            while self.records() and time.monotonic() < deadline:
                time.sleep(.1)
            if self.records():
                raise ValueError('Owned services have not exited')
            return True
        except Exception:
            for record in prepared:
                with contextlib.suppress(Exception):
                    self.call(record, 'resume', {}, timeout=2)
            with self.lock:
                self.draining = False
            return False


def desktop_open_project(project_dir, identity, retinanalysis_dir, *, timeout=300, managed=False):
    from workspace_projects import list_managed_projects, list_projects
    inventory = list_managed_projects(project_dir) if managed else list_projects(project_dir)
    selected_path = str(Path(project_dir).expanduser().resolve())
    project = next((row for row in inventory['projects'] if row['uuid'] == identity and row['available']
                    and (managed or row['path'] == selected_path)), None)
    if project is None:
        raise ValueError('Select an available registered project')
    if _SERVICES is None:
        port = int(os.environ['RIEKE_DESKTOP_LAUNCHER_PORT'])
        body = json.dumps({'directory': project['path'], 'project_uuid': identity}).encode()
        headers = {'X-Rieke-Desktop-Capability': os.environ['RIEKE_DESKTOP_CAPABILITY'],
                   'Content-Type': 'application/json', 'X-Workspace-Request': '1'}
        try:
            with urlopen(Request(f'http://127.0.0.1:{port}/api/desktop/open-project', data=body,
                                headers=headers), timeout=timeout + 5) as response:
                return json.load(response)
        except HTTPError as error:
            payload = json.load(error)
            if payload.get('code') == DesktopProjectCompatibilityError.code:
                raise DesktopProjectCompatibilityError() from None
            raise
    return _SERVICES.open(project['path'], identity, retinanalysis_dir, timeout)


def desktop_database_operation(project, operation_id=None, *, failed=False):
    """Register/ack transient native services with the same global supervisor."""
    if _SERVICES is not None:
        if operation_id is None:
            return _SERVICES.begin_database_operation(project)
        _SERVICES.finish_database_operation(operation_id, failed=failed)
        return operation_id
    port = int(os.environ['RIEKE_DESKTOP_LAUNCHER_PORT'])
    operation = 'start' if operation_id is None else 'finish'
    body = {'project_path': str(Path(project).resolve())} if operation_id is None else {'operation_id': operation_id, 'failed': failed}
    headers = {'X-Rieke-Desktop-Capability': os.environ['RIEKE_DESKTOP_CAPABILITY'],
               'X-Workspace-Request': '1', 'Content-Type': 'application/json'}
    with urlopen(Request(f'http://127.0.0.1:{port}/api/desktop/database-operation/{operation}',
                         data=json.dumps(body).encode(), headers=headers), timeout=15) as response:
        result = json.load(response)
    return result['operation_id'] if operation_id is None else operation_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--user-state', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1'])
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--project-dir', type=Path)
    parser.add_argument('--ready-fd', type=int)
    args = parser.parse_args(argv)
    session_id = str(uuid.UUID(args.session_id))
    if not 1024 <= args.port <= 65535:
        raise ValueError('Desktop port must be an unprivileged TCP port')
    capability = os.environ.get('RIEKE_DESKTOP_CAPABILITY', '')
    if len(capability) < 32:
        raise ValueError('Desktop capability is required')
    resources = args.resources.resolve(strict=True)
    runtime = resources / 'runtime'
    user_state = args.user_state.resolve()
    if user_state.is_relative_to(resources) or resources.is_relative_to(user_state):
        raise ValueError('Mutable desktop state must be outside the signed resources')
    user_state.mkdir(parents=True, exist_ok=True)
    os.environ.update(RIEKE_DESKTOP_MODE='1', RIEKE_DESKTOP_USER_STATE=str(user_state),
                      RIEKE_DESKTOP_RUNTIME=str(runtime), RIEKE_PARSER_CONFIG=str(user_state / 'parser/config.ini'),
                      RIEKE_DESKTOP_FRONTEND=str(runtime / 'frontend'), PYTHONDONTWRITEBYTECODE='1')
    os.environ.pop('RIEKE_INSTALLATION_ROOT', None)
    manifest_path = args.manifest.resolve(strict=True)
    if manifest_path != (runtime / 'runtime-manifest.json').resolve():
        raise ValueError('Desktop manifest must be the owned runtime manifest')
    from workspace_bootstrap import validate_desktop_runtime, prepare_desktop_parser_config
    manifest = validate_desktop_runtime(runtime, verify_hashes=True)
    prepare_desktop_parser_config(user_state)
    # Runtime validation checks the interpreter, resource hashes and installed
    # parser. Probe all native executables before exposing the chooser.
    from workspace_mysql_runtime import mysql_runtime
    mysql_runtime()
    from workspace_bootstrap import runtime_paths
    runtime_config = runtime_paths()
    preference = user_state / 'preferences/workspace-selection.json'
    if preference.exists():
        if preference.is_symlink() or preference.stat().st_size > 65536:
            raise ValueError('Desktop workspace preference is invalid')
        selected = json.loads(preference.read_text())
        if selected.get('version') != 1 or not isinstance(selected.get('managed_root'), str):
            raise ValueError('Desktop workspace preference is invalid')
        runtime_config['managed_root'] = selected['managed_root']
    retinanalysis = Path(runtime_config['retinanalysis'])
    from recording_workspace import load_parser
    load_parser(retinanalysis)
    identity = {'pid': os.getpid(), 'session_id': session_id,
                'application_version': manifest['application_version'],
                'source_commit': manifest['source_commit'],
                'workspace_formats': manifest['workspace_formats'],
                'database_compatibility': manifest['database_compatibility'],
                'project_uuid': None, 'project_path': None}
    global _SERVICES
    session_lock = None
    if args.project_dir:
        project = args.project_dir.resolve(strict=True)
        if project.is_relative_to(resources):
            raise ValueError('Projects must be outside the signed resources')
        catalog = json.loads((project / 'catalog.json').read_text())
        if catalog.get('connection', {}).get('credential_provider', {}).get('kind') != 'native-project':
            raise ValueError('Desktop requires a project-owned native database; migrate legacy projects before opening them')
        session_lock = acquire_project_session(project)
        from workspace_project_database import ensure_project_database
        ensure_project_database(project)
        from workspace_api import create_app
        app = create_app(project, retinanalysis, desktop_session_lock=session_lock)
        identity.update(project_uuid=app.extensions['workspace_service'].project['project_uuid'], project_path=str(project))
    else:
        lock_path = user_state / 'desktop-session.lock'
        if lock_path.is_symlink():
            raise ValueError('Desktop session lock cannot be a symbolic link')
        session_lock = lock_path.open('a')
        fcntl.flock(session_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _SERVICES = DesktopServices(user_state, resources, manifest_path, session_id, capability, identity)
        os.environ['RIEKE_DESKTOP_LAUNCHER_PORT'] = str(args.port)
        from workspace_launcher import create_launcher
        app = create_launcher(runtime_config['managed_root'], retinanalysis,
                              application_dir=runtime / 'application')
    boundary = DesktopBoundary(app, port=args.port, capability=capability, identity=identity, services=_SERVICES)
    from waitress import create_server
    server = create_server(boundary, host=args.host, port=args.port, threads=8,
                           clear_untrusted_proxy_headers=True, max_request_body_size=16 * 1024**3)
    stopped = threading.Event()
    def close_server():
        server.close()
        # Scientific WSGI requests already acknowledged completion. Close idle
        # connections so Waitress's event loop exits, then join its dispatcher.
        # No process signal or writer cancellation is involved.
        server.asyncore.close_all(map=server._map, ignore_all=True)
        server.task_dispatcher.shutdown(cancel_pending=False, timeout=30)
        stopped.set()
    # Schedule closure on the event-loop thread. Closing sockets from a timer
    # races select() and gives an otherwise orderly shutdown EBADF.
    def request_server_stop():
        server.trigger.pull_trigger(close_server)
    boundary.stop_callback = request_server_stop
    app.extensions['shutdown_project_server'] = request_server_stop
    inbox = app.extensions.get('h5_inbox')
    if inbox:
        inbox.start()
    # The private spawned-process channel proves this listener was successfully
    # bound before any supervisor sends a capability over loopback HTTP.
    receipt = 'RIEKE_DESKTOP_BOUND=' + json.dumps({**identity, 'port': args.port, 'ready': True}) + '\n'
    if args.ready_fd is None:
        print(receipt, end='', flush=True)
    else:
        if args.ready_fd < 3:
            raise ValueError('Desktop readiness descriptor must be a private pipe')
        with os.fdopen(args.ready_fd, 'w') as pipe:
            pipe.write(receipt)
            pipe.flush()
    try:
        server.run()
    finally:
        if inbox:
            inbox.stop()
        if session_lock:
            session_lock.close()


if __name__ == '__main__':
    main()
