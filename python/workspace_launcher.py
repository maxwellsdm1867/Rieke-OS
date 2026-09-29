"""Persistent localhost entry point: project chooser works before any H5 or SQL."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from workspace_projects import create_project, list_managed_projects, list_projects, managed_root
from workspace_project_servers import open_project
from workspace_startup_registry import remember_project


def register_project_routes(app, *, retinanalysis_dir, project_dir=None, root=None):
    """Used by both the launcher and an opened project's API."""
    current = Path(project_dir).resolve() if project_dir else None
    root_provider = root if callable(root) else lambda: managed_root(root or current.parent)
    @app.get('/api/projects')
    def project_inventory():
        result = list_projects(current) if current else list_managed_projects(root_provider())
        return jsonify({**result, 'launcher': current is None})

    @app.post('/api/projects')
    def project_create():
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) - {'name','directory'}:
            raise ValueError('Project creation accepts a name and optional managed folder')
        project = create_project(root_provider(), body.get('name'), directory=body.get('directory'))
        return jsonify(project=project, database_status='not_started',
            message='Empty project created. Opening it prepares its own database; no recording is required.'), 201

    @app.post('/api/projects/<project_uuid>/open')
    def project_open(project_uuid):
        body = request.get_json(silent=True)
        if request.args or body not in ({}, None):
            raise ValueError('Open project accepts an empty request')
        if current:
            record = next((p for p in list_projects(current)['projects'] if p['current']), None)
            if record and record['uuid'] == project_uuid:
                remember_project(root_provider(), project_uuid)
                return jsonify(url=request.host_url, project_uuid=project_uuid)
        return jsonify(open_project(root_provider(), project_uuid, retinanalysis_dir, managed=True))


def create_launcher(root, retinanalysis_dir, *, application_dir=None):
    root = managed_root(root)
    selected_root = [root]
    application = Path(application_dir or Path(__file__).resolve().parents[1]).resolve()
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=64*1024)
    frontend = Path(__file__).resolve().parents[1] / 'workspace-app/dist'
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
        if isinstance(error,(ValueError,KeyError,FileNotFoundError)):
            return jsonify(error=str(error)),400
        app.logger.exception('Project launcher operation failed')
        return jsonify(error='Project operation could not finish. Check the launcher log before retrying.'),500
    @app.get('/api/health')
    def health():
        return jsonify(status='ready',launcher=True,project_uuid=None)
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
        return send_from_directory(frontend,path)
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
