"""Persistent localhost entry point: project chooser works before any H5 or SQL."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from workspace_projects import create_project, create_project_at, list_managed_projects, list_projects, managed_root
from workspace_project_servers import open_project
from workspace_startup_registry import remember_project_result


def register_project_routes(app, *, retinanalysis_dir, project_dir=None, root=None):
    """Used by both the launcher and an opened project's API."""
    from workspace_app_routes import register_app_routes
    register_app_routes(app)
    from workspace_folder_browser import register_folder_browser_routes
    register_folder_browser_routes(app, project_dir=project_dir)
    current = Path(project_dir).resolve() if project_dir else None
    root_provider = root if callable(root) else lambda: managed_root(root or current.parent)
    @app.get('/api/projects')
    def project_inventory():
        result = list_projects(current) if current else list_managed_projects(root_provider())
        return jsonify({**result, 'launcher': current is None})

    @app.post('/api/projects/order')
    def project_order():
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) != {'paths'}:
            raise ValueError('Project order requires the complete project folder list')
        paths = body['paths']
        if not isinstance(paths, list) or len(paths) > 1000 or any(not isinstance(path, str) or len(path) > 4096 for path in paths):
            raise ValueError('Project order must contain validated project folders')
        inventory = list_projects(current) if current else list_managed_projects(root_provider())
        available = {project['path'] for project in inventory['projects']}
        if len(paths) != len(available) or len(set(paths)) != len(paths) or set(paths) != available:
            raise ValueError('Project list changed; refresh it before rearranging projects')
        from workspace_startup_registry import remember_project_paths_order
        remember_project_paths_order(paths)
        return project_inventory()

    @app.post('/api/projects')
    def project_create():
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) - {'name','directory','root_directory','project_directory'}:
            raise ValueError('Project creation accepts a name, optional root directory and project folder')
        if 'project_directory' in body:
            if set(body) - {'name', 'project_directory'}:
                raise ValueError('Choose one exact project folder; do not combine it with a parent root')
            project = create_project_at(body['project_directory'], body.get('name'))
            return jsonify(remember_project_result(project['path'], {'project': project, 'database_status': 'not_started',
                'message': 'Project created in the selected folder. Opening it prepares its database.'})), 201
        selected_root = body.get('root_directory')
        if selected_root is not None:
            if not isinstance(selected_root, str) or not selected_root.strip() or not Path(selected_root.strip()).expanduser().is_absolute():
                raise ValueError('Choose an absolute root folder for the new project')
            selected_root = managed_root(selected_root.strip())
        project = create_project(selected_root or root_provider(), body.get('name'), directory=body.get('directory'))
        return jsonify(remember_project_result(project['path'], {'project': project, 'database_status': 'not_started',
            'message': 'Empty project created. Opening it prepares its own database; no recording is required.'})), 201

    @app.post('/api/projects/inspect-folder')
    def project_inspect_folder():
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) != {'directory'}:
            raise ValueError('Choose an existing project folder')
        from workspace_project_validation import inspect_project_folder
        return jsonify(inspect_project_folder(body['directory']))

    @app.post('/api/projects/open-folder')
    def project_open_folder():
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) != {'directory'} or not isinstance(body['directory'], str) or not body['directory'].strip():
            raise ValueError('Choose an existing project folder by its absolute path')
        directory = Path(body['directory'].strip()).expanduser()
        if not directory.is_absolute() or directory.is_symlink():
            raise ValueError('Choose an absolute project folder path, not a symbolic link')
        if not directory.is_dir():
            raise ValueError('Project folder does not exist; choose an existing project')
        directory = directory.resolve()
        from workspace_portability import MANIFEST
        if (directory / MANIFEST).exists() or (directory / MANIFEST).is_symlink():
            raise ValueError('This is a prepared project copy. Add it through project setup and choose a new project folder to restore it.')
        if not (directory / 'project.json').is_file() or not (directory / 'catalog.json').is_file():
            raise ValueError('Choose the project folder containing project.json and catalog.json, not its parent workspace')
        from workspace_project_validation import validate_project_folder
        project = validate_project_folder(str(directory))['project']
        if not project['available']:
            raise ValueError('Project manifests are invalid: ' + project['unavailable_reason'])
        if current:
            current_record = next(row for row in list_projects(current)['projects'] if row['current'])
            if directory == current:
                return jsonify(remember_project_result(directory, {'url': request.host_url, 'project_uuid': project['uuid']}, set_last=True))
            if project['uuid'] == current_record['uuid']:
                import uuid
                from workspace_projects import _read_manifest
                def restored_instance(path):
                    catalog = _read_manifest(path / 'catalog.json')
                    owned = catalog.get('managed_database') or {}
                    value = owned.get('instance_uuid')
                    if not value:
                        return None
                    instance = str(uuid.UUID(value))
                    expected = 'rieke-os-' + project['uuid'].replace('-', '') + '-' + instance.replace('-', '')
                    if (owned.get('project_uuid') != project['uuid']
                            or (owned.get('kind') != 'native-mysql' and owned.get('container') != expected)
                            or _read_manifest(path / 'database/service.json') != owned):
                        raise ValueError('Restored project runtime identity is invalid')
                    return instance + ':' + str(path.resolve()) if owned.get('kind') == 'native-mysql' else instance
                other_instance = restored_instance(directory)
                if not other_instance or other_instance == restored_instance(current):
                    raise ValueError('This folder duplicates the current project identity; use its original folder')
        result = open_project(directory, project['uuid'], retinanalysis_dir)
        return jsonify(remember_project_result(directory, result, set_last=True))

    @app.post('/api/projects/<project_uuid>/open')
    def project_open(project_uuid):
        body = request.get_json(silent=True)
        if request.args or body not in ({}, None):
            raise ValueError('Open project accepts an empty request')
        inventory = list_projects(current) if current else list_managed_projects(root_provider())
        if sum(project['uuid'] == project_uuid for project in inventory['projects']) > 1:
            raise ValueError('Several folders share this project identity. Select the exact project folder to open.')
        if current:
            record = next((p for p in list_projects(current)['projects'] if p['current']), None)
            if record and record['uuid'] == project_uuid:
                return jsonify(remember_project_result(current, {'url': request.host_url, 'project_uuid': project_uuid}, set_last=True))
        project = next((project for project in inventory['projects']
                        if project['uuid'] == project_uuid and project['available']), None)
        if project is None:
            raise ValueError('Select an available registered project')
        result = open_project(Path(project['path']), project_uuid, retinanalysis_dir)
        return jsonify(remember_project_result(project['path'], result, set_last=True))


def create_launcher(root, retinanalysis_dir, *, application_dir=None):
    root = managed_root(root)
    selected_root = [root]
    application = Path(application_dir or Path(__file__).resolve().parents[1]).resolve()
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=64*1024)
    frontend = (Path(os.environ['RIEKE_DESKTOP_FRONTEND']) if os.environ.get('RIEKE_DESKTOP_MODE') == '1'
                else Path(__file__).resolve().parents[1] / 'workspace-app/dist')
    @app.before_request
    def local_only():
        host = request.host.split(':',1)[0]
        if request.remote_addr not in {'127.0.0.1','::1'} or host not in {'127.0.0.1','localhost'}:
            return jsonify(error='This launcher accepts loopback requests only.'), 403
        if request.method in {'POST','PUT','PATCH','DELETE'}:
            if request.headers.get('X-Workspace-Request') != '1':
                return jsonify(error='Missing workspace request header.'),403
            origin = request.headers.get('Origin')
            if origin and origin not in {request.host_url.rstrip('/'),'http://127.0.0.1:5173','http://localhost:5173'}:
                return jsonify(error='Unrecognized request origin.'),403
    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    @app.errorhandler(Exception)
    def error(error):
        if isinstance(error,HTTPException):
            return jsonify(error=error.description),error.code
        if os.environ.get('RIEKE_DESKTOP_MODE') == '1':
            from workspace_desktop import DesktopProjectCompatibilityError
            if isinstance(error, DesktopProjectCompatibilityError):
                return jsonify(error=str(error), code=error.code, requires_migration=True,
                               migration_endpoint='/api/projects/migrate-source'), 409
        if isinstance(error,(ValueError,KeyError,FileNotFoundError)):
            return jsonify(error=str(error)),400
        app.logger.exception('Project launcher operation failed')
        return jsonify(error='Project operation could not finish. Check the launcher log before retrying.'),500
    @app.get('/api/health')
    def health():
        from workspace_updates import release_metadata
        return jsonify(status='ready',launcher=True,project_uuid=None,app_release=release_metadata()['version'])
    @app.post('/api/workspace')
    def choose_workspace():
        from workspace_installation import select_workspace
        body = request.get_json(silent=True)
        if request.args or not isinstance(body,dict) or set(body) != {'directory'} or not isinstance(body['directory'],str) or not body['directory'].strip():
            raise ValueError('Choose a workspace root directory')
        selected = select_workspace(body['directory'].strip(),application)
        result = list_managed_projects(selected)
        selected_root[0] = selected
        return jsonify({**result,'launcher':True,'message':'Workspace selected. Existing projects and files are preserved.'})
    register_project_routes(app, retinanalysis_dir=retinanalysis_dir, root=lambda: selected_root[0])
    @app.get('/')
    @app.get('/<path:path>')
    def frontend_page(path='index.html'):
        if path.startswith('api/'):
            return jsonify(error='Open a project before using project operations.'),404
        from workspace_frontend import project_frontend_response
        return project_frontend_response(frontend, path, lambda: {**list_managed_projects(selected_root[0]), 'launcher': True})
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--managed-root',type=Path,default=Path.home()/'Documents/RecordingWorkspace')
    parser.add_argument('--retinanalysis',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    create_launcher(args.managed_root,args.retinanalysis).run(host='127.0.0.1',port=args.port,debug=False,threaded=True,use_reloader=False)

if __name__=='__main__':
    main()
