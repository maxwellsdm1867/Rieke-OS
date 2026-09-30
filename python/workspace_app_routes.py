"""Installation status and offline transfer jobs shared by chooser and projects."""
from pathlib import Path
import os
import secrets
import threading
import uuid
from flask import jsonify, request


def register_app_routes(app, *, application_dir=None):
    root = Path(application_dir or Path(__file__).resolve().parents[1]).resolve()
    jobs = {}
    lock = threading.Lock()
    update_token = secrets.token_urlsafe(32)
    update_job = {'state': 'idle'}

    def active_writers():
        with lock:
            return any(job['state'] == 'running' for job in jobs.values()) or update_job['state'] == 'running'
    app.extensions['app_active_writers'] = active_writers

    def start_update(version=None, *, automatic=False):
        if os.environ.get('RIEKE_DESKTOP_MODE') == '1':
            raise ValueError('Desktop updates are owned by the application coordinator.')
        from workspace_updates import stage_release
        with lock:
            if update_job['state'] == 'running':
                return False
            if automatic and update_job.get('version') == version:
                return False  # One automatic attempt per version; manual retry remains available.
            update_job.clear()
            update_job.update(state='running', version=version)
        def run():
            try:
                result = stage_release(os.environ['RIEKE_INSTALLATION_ROOT'], root=root)
                with lock:
                    update_job.update(state='complete', version=result.get('version'), result=result)
            except Exception as error:
                app.logger.exception('Update staging failed')
                with lock:
                    update_job.update(state='failed', error=str(error) if isinstance(error, ValueError) else 'Update download failed. Check the launcher log; the active release was not changed.')
        threading.Thread(target=run, name='rieke-update-download', daemon=False).start()
        return True

    def update_payload(value):
        with lock:
            return {**value, 'update_token': update_token, 'download': dict(update_job)}

    def local_request():
        if (request.remote_addr not in {'127.0.0.1', '::1'}
                or request.host.split(':', 1)[0] not in {'127.0.0.1', 'localhost'}):
            return jsonify(error='App operations require a local connection.'), 403
        if request.method == 'POST':
            if (request.headers.get('X-Workspace-Request') != '1'
                    or request.headers.get('Origin', request.host_url.rstrip('/')) != request.host_url.rstrip('/')):
                return jsonify(error='App operations require a same-origin workspace request.'), 403

    @app.before_request
    def app_operation_boundary():
        if os.environ.get('RIEKE_DESKTOP_MODE') == '1' and request.path.startswith('/api/app/updates'):
            return jsonify(error='Desktop updates are owned by the application coordinator.', desktop=True), 409
        if request.path.startswith(('/api/app/', '/api/projects/transfers/',
                                    '/api/projects/prepare-transfer', '/api/projects/restore-transfer', '/api/projects/migrate-source', '/api/projects/relocate')):
            return local_request()

    @app.get('/api/app/updates')
    def update_status():
        from workspace_updates import installation_status
        return jsonify(update_payload(installation_status(root=root)))

    @app.post('/api/app/updates/check')
    def check_updates():
        body = request.get_json(silent=True)
        if request.args or body not in ({}, {'force': True}):
            return jsonify(error='Update check accepts an empty object or force: true.'), 400
        from workspace_updates import check_for_updates
        result = check_for_updates(root=root, force=bool(body.get('force')))
        if (result.get('state') == 'update_available' and result.get('can_stage')
                and not result.get('check_error') and os.environ.get('RIEKE_INSTALLATION_ROOT')
                and result.get('staged_version') != result.get('available')):
            start_update(result.get('available'), automatic=True)
        return jsonify(update_payload(result))

    @app.post('/api/app/updates/stage')
    def stage_update():
        if (request.args or request.get_json(silent=True) != {}
                or not secrets.compare_digest(request.headers.get('X-Rieke-Update-Token', ''), update_token)):
            return jsonify(error='Reopen the updates panel before downloading an update.'), 403
        from workspace_updates import installation_status
        if not installation_status(root=root).get('can_stage') or not os.environ.get('RIEKE_INSTALLATION_ROOT'):
            return jsonify(error='Verified downloads require a managed installation with a trusted release key.'), 409
        if not start_update():
            return jsonify(error='An update download is already running.'), 409
        return jsonify(state='running'), 202

    @app.get('/api/app/updates/download')
    def update_download():
        with lock:
            return jsonify(update_job)

    def transfer(operation):
        body = request.get_json(silent=True)
        if (request.args or not isinstance(body, dict) or set(body) != {'directory', 'destination'}
                or any(not isinstance(value, str) or not value.strip() or not Path(value).expanduser().is_absolute()
                       for value in body.values())):
            return jsonify(error='Choose absolute source and destination folder paths.'), 400
        with lock:
            if any(job['state'] == 'running' for job in jobs.values()):
                return jsonify(error='A project transfer is already running. Wait for it to finish.'), 409
            # Bound local job history without losing the current operation.
            while len(jobs) >= 30:
                del jobs[next(iter(jobs))]
            identity = str(uuid.uuid4())
            jobs[identity] = {'job_id': identity, 'state': 'running'}

        def run():
            try:
                from workspace_portability import prepare_project, restore_project
                if operation == 'migrate-source':
                    from workspace_migration import migrate_source_project
                    function = migrate_source_project
                else:
                    function = prepare_project if operation == 'prepare' else restore_project
                result = function(body['directory'].strip(), body['destination'].strip())
                if operation == 'restore':
                    from workspace_startup_registry import remember_project_result
                    result = remember_project_result(result['directory'], result)
                with lock:
                    jobs[identity] = {'job_id': identity, 'state': 'complete', 'result': result}
            except Exception as error:
                app.logger.exception('Project transfer failed')
                message = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else 'Project transfer failed. Check the launcher log; no success was recorded.'
                with lock:
                    jobs[identity] = {'job_id': identity, 'state': 'failed', 'error': message}
        # A normal process shutdown waits for a transfer rather than killing its writer.
        threading.Thread(target=run, name='rieke-project-transfer', daemon=False).start()
        return jsonify(job_id=identity, state='running'), 202

    @app.post('/api/projects/prepare-transfer')
    def prepare_transfer():
        return transfer('prepare')

    @app.post('/api/projects/restore-transfer')
    def restore_transfer():
        return transfer('restore')

    @app.post('/api/projects/migrate-source')
    def migrate_source():
        if os.environ.get('RIEKE_DESKTOP_MODE') != '1':
            return jsonify(error='Create source copies through the desktop application.'), 409
        return transfer('migrate-source')

    @app.post('/api/projects/relocate')
    def relocate_project_folder():
        body = request.get_json(silent=True)
        if (request.args or not isinstance(body, dict) or set(body) != {'directory', 'destination'}
                or any(not isinstance(value, str) or not value.strip() or not Path(value.strip()).expanduser().is_absolute()
                       for value in body.values())):
            return jsonify(error='Choose absolute source and destination project folder paths.'), 400
        with lock:
            if any(job['state'] == 'running' for job in jobs.values()):
                return jsonify(error='A project transfer is active; wait before moving a folder.'), 409
            try:
                from workspace_portability import relocate_project
                result = relocate_project(body['directory'].strip(), body['destination'].strip())
                from workspace_startup_registry import remember_project_result
                result = remember_project_result(result['directory'], result, previous_directory=body['directory'].strip())
            except (ValueError, OSError) as error:
                return jsonify(error=str(error)), 400
        return jsonify(result)

    @app.get('/api/projects/transfers/<identity>')
    def transfer_status(identity):
        with lock:
            job = jobs.get(identity)
            if job is None:
                return jsonify(error='Transfer status is unavailable. Inspect the destination before retrying.'), 404
            return jsonify(job)
