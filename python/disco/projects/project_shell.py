"""Project navigation stays available before scientific data is requested.

The shell never opens SQL, scans recordings, or prepares indexes. An activation
request creates the scientific application once; failures belong to that
action and leave the shell available for switching projects and retrying.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import threading

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response


def session_receipt(user_state, session_id, pid):
    import uuid
    return Path(user_state) / 'project-sessions' / f'{uuid.UUID(session_id)}-{int(pid)}.json'


def unused_session(user_state, record):
    """Positive evidence that an exited shell never attempted database access."""
    return _session_phase(user_state, record) == 'unused'


def released_session(user_state, record):
    """The shell confirmed that a failed data load left no owned database running.

    This is a clean-exit receipt for the service, not for the data: the native
    per-project gate still decides whether unclean data may be opened. Callers
    recheck the project's runtime state before relying on it.
    """
    return _session_phase(user_state, record) == 'database_released'


def _session_phase(user_state, record):
    try:
        path = session_receipt(user_state, record['session_id'], record['pid'])
        if (path.is_symlink() or path.parent.is_symlink() or not path.is_file()
                or path.stat().st_size > 16384
                or not path.resolve().is_relative_to(Path(user_state).resolve())):
            return None
        value = json.loads(path.read_text())
        if all(value.get(key) == record.get(key) for key in
               ('session_id', 'pid', 'project_uuid', 'project_path', 'source_commit')):
            return value.get('phase')
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return None


class ProjectData:
    def __init__(self, shell, build, cleanup_failed, receipt, identity):
        self.shell, self.build, self.cleanup_failed = shell, build, cleanup_failed
        self.receipt, self.identity = receipt, identity
        self.lock = threading.RLock()
        self.application = self.partial = None
        self.loading = self.attempted = False
        self.error = self.cleanup_error = None
        self._record('unused')

    def _record(self, phase):
        from workspace_desktop import _atomic_json
        self.receipt.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.receipt, {**self.identity, 'phase': phase})

    def begin_database(self):
        # This durable write must precede any database effect. A crashed shell
        # can only be dismissed as unused if this transition never happened.
        self._record('database_attempted')
        self.attempted = True

    def capture(self, application):
        self.partial = application

    def status(self):
        return {'status': 'ready' if self.application else 'loading' if self.loading else
                'failed' if self.error else 'not_loaded', 'error': self.error,
                'cleanup_error': self.cleanup_error}

    def busy(self):
        app = self.application or self.partial
        return self.loading or bool(app and any(app.extensions.get(name, lambda: False)()
            for name in ('project_active_writers', 'app_active_writers')))

    def activate(self, *, retry=False):
        with self.lock:
            if self.application is not None:
                return
            if self.error and not retry:
                raise ValueError(self.error)
            if self.cleanup_error:
                raise ValueError('The previous load could not close its database. Close the project before retrying.')
            self.loading = True
            self.error = None
            try:
                app = self.build(self.capture, self.begin_database)
                # Lifecycle consumers always use the gateway's extensions.
                # Keep its busy/stop wrappers, but publish lazily created workers.
                self.shell.extensions.update({key: value for key, value in app.extensions.items()
                    if key not in {'project_active_writers', 'app_active_writers',
                                   'desktop_stop_database', 'shutdown_project_server'}})
                app.extensions['shutdown_project_server'] = self.shell.extensions.get('shutdown_project_server')
                self.application = app
                inbox = app.extensions.get('h5_inbox')
                if inbox:
                    inbox.start()
            except Exception as error:
                self.application = None
                self.error = str(error)
                try:
                    self._cleanup_partial()
                except Exception as cleanup_error:
                    self.cleanup_error = str(cleanup_error)
                    self.shell.logger.exception('Project data load cleanup requires recovery')
                raise
            finally:
                self.loading = False

    def _cleanup_partial(self):
        app = self.partial
        if app:
            try:
                inbox = app.extensions.get('h5_inbox')
                if inbox:
                    inbox.stop()
                close_traces = app.extensions.get('close_trace_workers')
                if close_traces:
                    close_traces()
                scheduler = app.extensions.get('backup_scheduler')
                if scheduler:
                    scheduler.close(flush=False)
                service = app.extensions.get('workspace_service')
                if service:
                    with contextlib.suppress(Exception):
                        service.dj.conn().close()
            finally:
                close_heap = app.extensions.get('close_project_heap')
                if close_heap:
                    close_heap()
        if self.attempted:
            self.cleanup_failed()
            # No owned database remains: record a clean service-exit receipt
            # so this project alone carries any data recovery obligation.
            self._record('database_released')
            self.attempted = False
        self.partial = None
        self.cleanup_error = None

    def stop(self):
        with self.lock:
            if self.application:
                self.application.extensions['desktop_stop_database']()
            else:
                self._cleanup_partial()


def create_project_shell(project_dir, retinanalysis_dir, *, user_state, identity,
                         build, cleanup_failed):
    from workspace_launcher import register_project_routes
    from disco.projects.project_inventory import project_inventory
    from workspace_frontend import project_frontend_response

    project_dir = Path(project_dir).resolve()
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024**3)
    data = ProjectData(app, build, cleanup_failed,
        session_receipt(user_state, identity['session_id'], identity['pid']), identity)
    app.extensions.update(project_data=data, project_active_writers=data.busy,
                          desktop_stop_database=data.stop)

    def inventory():
        return {**project_inventory(app).current(project_dir), 'project_data': data.status()}

    @app.before_request
    def local_boundary():
        if request.host.split(':', 1)[0] not in {'127.0.0.1', 'localhost'}:
            return jsonify(error='This workspace accepts local connections only.'), 403
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('X-Workspace-Request') != '1':
                return jsonify(error='Missing workspace request header.'), 403
            if request.headers.get('Origin') not in (None, request.host_url.rstrip('/')):
                return jsonify(error='Unrecognized request origin.'), 403

    @app.after_request
    def response_headers(response):
        if request.path == '/api/projects' and response.status_code == 200:
            response.set_data(app.json.dumps({**response.get_json(), 'project_data': data.status()}))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.errorhandler(Exception)
    def error_response(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        if isinstance(error, (ValueError, KeyError, OSError)):
            return jsonify(error=str(error)), 400
        app.logger.exception('Project operation failed')
        return jsonify(error='Project data could not load. You can retry or choose another project.'), 500

    register_project_routes(app, retinanalysis_dir=retinanalysis_dir, project_dir=project_dir)

    @app.get('/api/health')
    def health():
        return jsonify(status='ready', project_uuid=identity['project_uuid'],
                       project_path=str(project_dir), project_data=data.status())

    @app.get('/api/project/presentation')
    def presentation():
        from disco.projects.presentation_cache import load_overview
        if request.args:
            raise ValueError('Project presentation accepts no parameters')
        return jsonify(load_overview(project_dir, user_state=user_state,
                                     expected_uuid=identity['project_uuid']))

    @app.get('/api/project/data-status')
    def data_status():
        return jsonify(data.status())

    @app.post('/api/project/activate')
    def activate():
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) - {'retry'} or type(body.get('retry', False)) is not bool:
            raise ValueError('Open data accepts an optional retry flag')
        data.activate(retry=body.get('retry', False))
        return jsonify(data.status())

    @app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    def scientific_operation(path):
        if data.application is None:
            return jsonify(error=data.error or 'Choose a data action to load this project.',
                           code='project_not_loaded', project_data=data.status()), 409
        return Response.from_app(data.application, request.environ)

    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path='index.html'):
        if path.startswith('api/'):
            return jsonify(error='Unknown API endpoint'), 404
        return project_frontend_response(Path(os.environ['RIEKE_DESKTOP_FRONTEND']), path, inventory,
            unavailable={'projects': [], 'current_project_uuid': identity['project_uuid'],
                         'launcher': False, 'project_data': data.status()})

    return app
