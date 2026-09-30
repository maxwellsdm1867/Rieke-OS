#!/usr/bin/env python3
"""Exercise the real bundled WSGI/Python/MySQL boundary under fresh user state.

This is local unsigned evidence, not clean-machine or signed-update qualification.
Never kill children on failure: an unacknowledged scientific service is retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import uuid


def inventory(runtime):
    # Hash paths as well as bytes so new bytecode/config files cannot hide.
    files = {}
    for path in sorted(runtime.rglob('*')):
        if path.is_symlink():
            files[str(path.relative_to(runtime))] = {'symlink': os.readlink(path)}
        elif path.is_file():
            with path.open('rb') as stream:
                files[str(path.relative_to(runtime))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return files


def run(resources, output, project=True, recording=None):
    resources = Path(resources).resolve(strict=True)
    runtime = resources / 'runtime'
    before = inventory(runtime)
    state = Path(tempfile.mkdtemp(prefix='rieke-desktop-smoke-'))
    capability = secrets.token_hex(32)
    session_id = str(uuid.uuid4())
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    def call(path, body=None, headers=None, timeout=10, base=origin):
        auth = {'X-Rieke-Desktop-Capability': capability, 'X-Workspace-Request': '1', 'Content-Type': 'application/json'}
        auth.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        with urlopen(Request(base + path, data=data, headers=auth), timeout=timeout) as response:
            return json.load(response)
    log = (state / 'backend.log').open('wb')
    env = {'HOME': str(state / 'home'), 'PATH': '/usr/bin:/bin', 'LANG': 'en_US.UTF-8',
           'TMPDIR': os.environ.get('TMPDIR', '/tmp'), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
           'RIEKE_DESKTOP_CAPABILITY': capability, 'RECORDING_WORKSPACE_ROOT': str(state / 'projects')}
    Path(env['HOME']).mkdir()
    command = [str(runtime / 'python/bin/python3.11'), '-B', str(runtime / 'application/python/workspace_desktop.py'),
               '--resources', str(resources), '--manifest', str(runtime / 'runtime-manifest.json'),
               '--user-state', str(state / 'user-state'), '--session-id', session_id, '--port', str(port)]
    process = subprocess.Popen(command, cwd=state, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log)
    bound = threading.Event()
    packet = {}
    def read_bound():
        for line in iter(process.stdout.readline, b''):
            log.write(line)
            log.flush()
            if line.startswith(b'RIEKE_DESKTOP_BOUND='):
                try:
                    packet.update(json.loads(line.split(b'=', 1)[1]))
                finally:
                    bound.set()
                break
    threading.Thread(target=read_bound, daemon=True).start()
    result = {'format': 'rieke-desktop-backend-smoke', 'version': 1, 'production_ready': False,
              'checks': [], 'limitations': ['Unsigned developer host', 'No installer or old-to-new update exercised',
                                           'No recording import/query/export/source-user migration exercised']}
    started = time.monotonic()
    error = None
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError(f'Bundled backend exited with {process.returncode}; private logs retained')
            if not bound.is_set():
                bound.wait(.2)
                continue
            if packet.get('pid') != process.pid or packet.get('session_id') != session_id or packet.get('port') != port:
                raise ValueError('Private listener bind receipt identity mismatch')
            try:
                health = call('/api/desktop/health', timeout=2)
                break
            except OSError:
                time.sleep(.2)
        else:
            raise ValueError('Bundled backend readiness timeout; service retained')
        manifest = json.loads((runtime / 'runtime-manifest.json').read_text())
        result['runtime_manifest_sha256'] = hashlib.sha256((runtime / 'runtime-manifest.json').read_bytes()).hexdigest()
        result['runtime_resource_count'] = len(manifest['resources'])
        result['runtime_identity'] = {key: manifest[key] for key in ('application_version', 'source_commit',
                                    'parser_commit', 'platform', 'architecture', 'python_version', 'mysql_version')}
        expected = {'pid': process.pid, 'session_id': session_id, 'application_version': manifest['application_version'],
                    'source_commit': manifest['source_commit'], 'workspace_formats': manifest['workspace_formats'],
                    'database_compatibility': manifest['database_compatibility']}
        if not health.get('ready') or any(health.get(k) != v for k, v in expected.items()):
            raise ValueError('Health identity mismatch')
        result['checks'].append('exact bundled readiness/session/release')
        result['readiness_seconds'] = round(time.monotonic() - started, 3)
        for headers in ({'X-Rieke-Desktop-Capability': 'wrong'}, {'Origin': 'https://foreign.invalid'},
                        {'Host': f'localhost:{port}'}):
            try:
                call('/api/desktop/health', headers=headers)
            except HTTPError as response:
                if response.code != 403:
                    raise
            else:
                raise ValueError('Authorization fault was accepted')
        result['checks'].append('wrong capability/origin/host rejected')
        try:
            call('/api/app/updates/stage', {})
        except HTTPError as response:
            if response.code != 409:
                raise
        else:
            raise ValueError('Source updater remained enabled')
        result['checks'].append('source updater disabled')
        scientific_project = None
        if project:
            created = call('/api/projects', {'name': 'Desktop smoke project', 'project_directory': str(state / 'project')})
            scientific_project = created['project']
            opened = call('/api/projects/open-folder', {'directory': scientific_project['path']}, timeout=180)
            project_origin = opened['url'].rstrip('/')
            authorization = call('/api/desktop/authorize-project', {'port': urlsplit(project_origin).port})
            if authorization['record'].get('bound') is not True:
                raise ValueError('Project listener ownership was not bound before authorization')
            child = authorization['health']
            result['checks'].append('main-only authorization validates live bound project before navigation')
            if child.get('project_uuid') != scientific_project['uuid'] or child.get('project_path') != scientific_project['path']:
                raise ValueError('Project service identity mismatch')
            result['checks'].append('native project created/opened using bundled runtime')
            registry = call('/api/desktop/health')['services']
            if len(registry) != 1 or registry[0]['pid'] != child['pid']:
                raise ValueError('Project registry did not own service')
            result['checks'].append('global service registry owns project process')
            if recording:
                recording = Path(recording).resolve(strict=True)
                with recording.open('rb') as stream:
                    original_checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
                import_started = time.monotonic()
                submitted = call('/api/imports', {'source_path': str(recording)}, base=project_origin)
                try:
                    call('/api/desktop/drain', {}, timeout=35)
                except HTTPError as response:
                    if response.code != 409:
                        raise
                else:
                    raise ValueError('Active recording import did not defer update drain')
                result['checks'].append('real import writer defers global update drain')
                deadline = time.monotonic() + 900
                while time.monotonic() < deadline:
                    jobs = call('/api/jobs', base=project_origin)['jobs']
                    job = next(item for item in jobs if item['job_uuid'] == submitted['job_uuid'])
                    if job['status'] in ('complete', 'complete_with_warnings'):
                        if job.get('requires_reconciliation'):
                            raise ValueError('Real import requires reconciliation')
                        break
                    if job['status'] in ('failed', 'interrupted'):
                        raise ValueError('Real recording import failed: ' + job.get('error', 'unknown'))
                    time.sleep(1)
                else:
                    raise ValueError('Real recording import timed out; workers retained')
                result['import_seconds'] = round(time.monotonic() - import_started, 3)
                overview = call('/api/overview', base=project_origin, timeout=45)
                if overview['counts']['epochs'] < 1 or not overview['protocols']:
                    raise ValueError('Real recording import produced no epochs/protocols')
                result['scientific_counts'] = {key: overview['counts'][key] for key in ('sources', 'cells', 'epochs', 'protocols')}
                protocol_uuid = overview['protocols'][0]['protocol_uuid']
                page = call('/api/protocols/' + protocol_uuid + '/epochs?limit=1', base=project_origin)
                epoch_uuid = page['epochs'][0]['epoch_uuid']
                profile = call('/api/annotation-profiles', {'display_name': 'Desktop qualification'}, base=project_origin)
                call('/api/annotation-profiles/selected', {'profile_uuid': profile['profile_uuid']}, base=project_origin)
                tag = 'desktop-qualification'
                call('/api/annotations', {'target_kind': 'epoch', 'target_uuids': [epoch_uuid],
                     'profile_uuid': profile['profile_uuid'], 'tags_add': [tag],
                     'expected_revisions': {epoch_uuid: 0}}, base=project_origin)
                query = call('/api/explore/run', {'predicate': {'field': 'annotations/epoch/tags',
                             'operator': 'contains', 'value': tag}, 'splits': 'date,protocol,cell'},
                             base=project_origin, timeout=45)
                if query['matched_count'] != 1:
                    raise ValueError('Tagged query did not preserve exact epoch membership')
                protocol = call('/api/protocols/' + protocol_uuid, base=project_origin)
                exported = call('/api/protocols/' + protocol_uuid + '/exports',
                    {'format': 'reference-json', 'query_revision': protocol['query_revision'],
                     'filters': {'epoch_uuid': epoch_uuid}, 'name': 'Desktop qualification'},
                    base=project_origin, timeout=60)
                artifact = Path(exported['artifact_path'])
                exported_package = json.loads(artifact.read_text())
                if [row['epoch_uuid'] for row in exported_package['epochs']] != [epoch_uuid]:
                    raise ValueError('Export epoch identity changed')
                if tag not in [item['tag'] for item in exported_package['epochs'][0]['annotations']['epoch_tags']]:
                    raise ValueError('Export did not retain shared annotation')
                with artifact.open('rb') as stream:
                    export_checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
                result['checks'].append('real import/tag/exact tagged query/reference export')
                call('/api/project/close', {}, base=project_origin, timeout=45)
                deadline = time.monotonic() + 35
                while call('/api/desktop/health')['services'] and time.monotonic() < deadline:
                    time.sleep(.2)
                reopened = call('/api/projects/open-folder', {'directory': scientific_project['path']}, timeout=180)
                project_origin = reopened['url'].rstrip('/')
                authorization = call('/api/desktop/authorize-project', {'port': urlsplit(project_origin).port})
                if authorization['health']['project_uuid'] != scientific_project['uuid']:
                    raise ValueError('Restarted project authorization changed identity')
                annotation = call('/api/annotations/read', {'target_kind': 'epoch', 'target_uuids': [epoch_uuid]}, base=project_origin)
                if tag not in [item['tag'] for item in annotation['targets'][epoch_uuid]['tags']]:
                    raise ValueError('Restart lost shared annotation')
                restarted_query = call('/api/explore/run', {'predicate': {'field': 'annotations/epoch/tags',
                                       'operator': 'contains', 'value': tag}, 'splits': 'date,protocol,cell'}, base=project_origin)
                if restarted_query['matched_count'] != 1:
                    raise ValueError('Restart changed saved scientific query membership')
                with artifact.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != export_checksum:
                        raise ValueError('Restart changed export artifact')
                with recording.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != original_checksum:
                        raise ValueError('Original recording changed')
                result['checks'].append('restart preserves tags/query/export and original H5 checksum')
                result['limitations'][-1] = 'Source-user migration and real signed update not exercised'
        if call('/api/desktop/drain', {}, timeout=65).get('ready') is not True:
            raise ValueError('Drain was not acknowledged')
        if scientific_project:
            owner = json.loads((Path(scientific_project['path']) / 'database/native-owner.json').read_text())
            if owner.get('clean_shutdown') is not True:
                raise ValueError('Native database clean shutdown missing')
            if call('/api/desktop/health')['services']:
                raise ValueError('Project services did not exit')
            result['checks'].append('registered project/MySQL drained and exited with clean receipt')
        call('/api/desktop/stop', {})
        process.wait(timeout=35)
        if process.returncode != 0:
            raise ValueError('Bundled backend shutdown was not clean')
        result['checks'].append('root WSGI process graceful exit')
    except Exception as failure:
        error = failure
        result['error'] = str(failure)
        # Retrying orderly drain is permitted; no signals or force cancellation.
        try:
            if process.poll() is None and call('/api/desktop/drain', {}, timeout=65).get('ready'):
                call('/api/desktop/stop', {})
                process.wait(timeout=35)
        except Exception:
            pass
    finally:
        log.close()
        after = inventory(runtime)
        result['packaged_resources_unchanged'] = before == after
        if before != after:
            result['changed_resource_paths'] = [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
            error = error or ValueError('Bundled resources changed after launch')
        result['passed'] = error is None
        # Public receipt contains no local paths, capabilities or credentials.
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        if error:
            print('Private test data/logs retained:', state)
    if error:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, default=Path(__file__).resolve().parents[1] / 'desktop/build')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/dev/desktop-backend-smoke.json')
    parser.add_argument('--launcher-only', action='store_true')
    parser.add_argument('--recording', type=Path, help='External Symphony H5; never copied into the app')
    args = parser.parse_args()
    run(args.resources, args.output, project=not args.launcher_only, recording=args.recording)
