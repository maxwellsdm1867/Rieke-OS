#!/usr/bin/env python3
"""Serve current source against an owned, donor-free native Workbench fixture.

This is source integration evidence, not packaged/release qualification. The
runtime is read-only; all scientific state and preferences live in a fresh
temporary directory. Stop with SIGTERM to close the owned database cleanly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--port', default=0, type=int)
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    state = Path(tempfile.mkdtemp(prefix='disco-workbench-replacement-e2e-')).resolve()
    home = state / 'home'
    home.mkdir()
    os.environ.update(HOME=str(home), RIEKE_DESKTOP_RUNTIME=str(runtime),
                      RIEKE_INSTALLATION_ROOT=str(state / 'installation'),
                      RIEKE_PREFERENCES_DIR=str(state / 'preferences'),
                      RIEKE_PROJECT_INDEX=str(state / 'project-index.json'),
                      MPLCONFIGDIR=str(state / 'mplconfig'))
    sys.path.insert(0, str(ROOT / 'python'))
    from workspace_bootstrap import prepare_desktop_parser_config
    prepare_desktop_parser_config(state / 'installation')
    from workspace_projects import create_project
    from workspace_native_mysql import ensure_native_database, stop_native_database
    from workspace_api import create_app
    from werkzeug.serving import make_server
    receipt = {'format': 'disco-workbench-replacement-native-source', 'state': str(state), 'pid': os.getpid(),
               'source_root': str(ROOT), 'runtime': str(runtime), 'status': 'preparing'}
    project = None
    app = server = None
    try:
        for index in range(2):
            target = state / f'h5-{index}'
            target.mkdir(mode=0o700)
            import h5py
            import numpy as np
            from organization_e2e_fixture import specification, generate, verify_raw, parse_preflight, write_new, sha
            oracle = specification(str(uuid.uuid4()))
            write_new(target / 'oracle.json', oracle)
            source = target / 'synthetic.h5'
            generate(source, oracle, np, h5py)
            # The parser requires a dataFileName even for a self-contained
            # synthetic response. This is descriptive metadata, not a donor.
            with h5py.File(source, 'r+') as h5:
                for cell in oracle['cells']:
                    h5[cell['block_path'] + '/properties'].attrs['dataFileName'] = np.bytes_(r'synthetic\fixture.bin')
            verify_raw(source, oracle, np, h5py)
            preflight = parse_preflight(source, target / 'parsed.json',
                runtime / 'python/lib/python3.11/site-packages/retinanalysis/utils/parse_data.py', oracle)
            write_new(target / 'fixture-receipt.json', dict(status='passed', parser_preflight=preflight,
                h5_sha256=sha(source), oracle_sha256=sha(target / 'oracle.json')))
            source.chmod(0o400)
        created = create_project(state / 'projects', 'Owned Workbench review E2E', code_root=ROOT)
        project = Path(created['path'])
        receipt['project'] = str(project)
        ensure_native_database(project)
        app = create_app(project, runtime / 'parser')
        server = make_server('127.0.0.1', args.port, app, threaded=True)
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        tracked_roots = [ROOT / 'python', ROOT / 'workspace-app/src', ROOT / 'workspace-app/dist']
        hashes = {str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest()
                  for root in tracked_roots for file in root.rglob('*')
                  if file.is_file() and file.suffix in ('.py', '.js', '.jsx', '.json', '.css', '.html')}
        receipt.update(status='ready', port=server.server_port, project_uuid=created['uuid'],
            git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            source_sha256=hashes,
            runtime_manifest_sha256=hashlib.sha256((runtime / 'runtime-manifest.json').read_bytes()).hexdigest())
        (state / 'server-receipt.json').write_text(json.dumps(receipt, indent=2))
        print('WORKBENCH_E2E=' + json.dumps({key: value for key, value in receipt.items()
                                           if key != 'source_sha256'}), flush=True)
        server.serve_forever()
    except BaseException as error:
        receipt.update(status='failed', error=repr(error))
        raise
    finally:
        if server:
            server.server_close()
        if app and app.extensions.get('close_trace_workers'):
            app.extensions['close_trace_workers']()
        if project:
            stop_native_database(project)
            owner = json.loads((project / 'database/native-owner.json').read_text())
            receipt['clean_shutdown'] = owner.get('clean_shutdown') is True
        if receipt.get('source_sha256'):
            receipt['source_changed_paths'] = [name for name, digest in receipt['source_sha256'].items()
                if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
            receipt['source_unchanged'] = not receipt['source_changed_paths']
            receipt['final_git_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if receipt['status'] == 'ready':
            receipt['status'] = 'stopped'
        (state / 'server-receipt.json').write_text(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
