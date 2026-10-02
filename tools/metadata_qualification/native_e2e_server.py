"""Own a real native API process for isolated E2E qualification, no mocks.

Copy a cleanly stopped project and its credentials before invoking this runner.
Never point this at an original project. Runtime dependencies must already exist.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--retinanalysis', required=True, type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_relative_to(Path('/tmp').resolve()):
        raise ValueError('E2E runner requires an isolated project below /tmp')
    owner = json.loads((project / 'database/native-owner.json').read_text())
    if owner.get('clean_shutdown') is not True:
        raise ValueError('Start with an existing clean project copy')
    credentials = project / 'database/native-credentials.json'
    if credentials.stat().st_mode & 0o777 != 0o600:
        raise ValueError('Existing copied credentials must retain private mode')
    os.environ['RIEKE_PREFERENCES_DIR'] = str(project.parent / 'preferences')
    os.environ['RIEKE_PROJECT_INDEX'] = str(project.parent / 'project-index.json')
    from workspace_native_mysql import ensure_native_database, stop_native_database
    from workspace_api import create_app
    from werkzeug.serving import make_server
    server = None
    try:
        runtime = ensure_native_database(project)
        print(json.dumps({'phase': 'native_ready', 'api_port': args.port,
                          'sql_port': runtime['port'], 'isolated': True}), flush=True)
        app = create_app(project, args.retinanalysis)
        service = app.extensions['workspace_service']
        print(json.dumps({'phase':'native_index_receipt',
                          'native_index_present':getattr(service,'disk_index',None) is not None,
                          'typed_index_present':getattr(service,'typed_index',None) is not None,
                          'last_refresh':service.last_refresh}), flush=True)
        server = make_server('127.0.0.1', args.port, app, threaded=True)
        app.extensions['shutdown_project_server'] = server.shutdown
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        print(json.dumps({'phase': 'api_ready', 'port': args.port,
                          'native_epochs': len(app.extensions['workspace_service'].rows)}), flush=True)
        server.serve_forever()
    finally:
        if server:
            server.server_close()
        stop_native_database(project)


if __name__ == '__main__':
    main()
