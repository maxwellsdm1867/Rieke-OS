#!/usr/bin/env python3
"""Exercise a read-only desktop candidate with Docker execution/socket access denied.

Fresh project/test state only. Never stops or queries the user's Docker daemon.
Negative-control attempts are recorded separately from the scientific workload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from desktop_artifact_e2e import NETWORK_GUARD
from desktop_backend_smoke import run as backend_run


DOCKER_GUARD = r'''
import json,os,shlex,shutil,socket,subprocess
def _record(kind,**fields):
    entry=json.dumps(dict(kind=kind,pid=os.getpid(),**fields))+'\n'
    fd=os.open(os.environ['RIEKE_NO_DOCKER_AUDIT'],os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:os.write(fd,entry.encode())
    finally:os.close(fd)
_record('guard_loaded',docker_cli_unavailable=shutil.which('docker') is None,
        sanitized_path=os.environ.get('PATH')=='/usr/bin:/bin')
_connect=socket.socket.connect
_connect_ex=socket.socket.connect_ex
def _unix_allowed(sock,address):
    if sock.family!=socket.AF_UNIX:return
    value=os.fsdecode(address)
    # The only Unix transport needed by the tested production backend is its
    # owned native MySQL socket. All other Unix sockets, including Docker aliases,
    # are unavailable to Python and its import workers in this test.
    if os.path.basename(value)=='mysql.sock' and os.path.basename(os.path.dirname(value)).startswith('rieke-mysql-'):
        _record('native_mysql_socket_allowed');return
    _record('unix_socket_denied',docker_socket=('docker' in value.lower()))
    raise OSError('No-Docker test denies non-MySQL Unix socket access')
def connect(sock,address):
    _unix_allowed(sock,address);return _connect(sock,address)
def connect_ex(sock,address):
    _unix_allowed(sock,address);return _connect_ex(sock,address)
socket.socket.connect=connect
socket.socket.connect_ex=connect_ex
_popen=subprocess.Popen
def popen(args,*positional,**options):
    tokens=shlex.split(args) if isinstance(args,str) else [os.fsdecode(a) for a in args]
    candidates=tokens if options.get('shell') else tokens[:1]
    if any(os.path.basename(token) in {'docker','docker-compose','compose','podman'} for token in candidates):
        _record('docker_process_denied');raise OSError('No-Docker test denies container CLI execution')
    if tokens:_record('process_allowed',executable=os.path.basename(tokens[0]))
    return _popen(args,*positional,**options)
subprocess.Popen=popen
'''


CONTROLS = r'''
import socket,subprocess,shutil
assert shutil.which('docker') is None
for operation in ('connect','connect_ex'):
    with socket.socket(socket.AF_UNIX) as client:
        try:getattr(client,operation)('/var/run/docker.sock')
        except OSError:pass
        else:raise AssertionError('Docker socket guard inactive')
for command in (['docker','version'],['docker-compose','version'],['compose','version']):
    try:subprocess.run(command,check=True,capture_output=True)
    except OSError:pass
    else:raise AssertionError('Container command guard inactive')
'''


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def counts(items):
    kinds={entry['kind'] for entry in items}
    return {kind:sum(entry['kind']==kind for entry in items) for kind in sorted(kinds)}


def run(args):
    resources=args.resources.resolve(strict=True)
    runtime=resources/'runtime'
    manifest_path=runtime/'runtime-manifest.json'
    manifest=json.loads(manifest_path.read_text())
    scratch=Path(tempfile.mkdtemp(prefix='rieke-no-docker-'))
    guard=scratch/'guard';guard.mkdir()
    (guard/'sitecustomize.py').write_text(NETWORK_GUARD+'\n'+DOCKER_GUARD)
    control_log=scratch/'control.jsonl';work_log=scratch/'workload.jsonl'
    home=scratch/'control-home';home.mkdir()
    env={'HOME':str(home),'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','PYTHONPATH':str(guard),
         'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','RIEKE_NO_DOCKER_AUDIT':str(control_log)}
    subprocess.run([str(runtime/'python/bin/python3.11'),'-B','-c',CONTROLS],env=env,cwd=home,
                   check=True,capture_output=True,timeout=20)
    original=subprocess.Popen
    owned_states=set()
    def guarded_spawn(command,*positional,**options):
        child_env=dict(options.get('env') or os.environ)
        child_env.update(PYTHONPATH=str(guard),RIEKE_NO_DOCKER_AUDIT=str(work_log),
                         HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9',
                         NO_PROXY='localhost,127.0.0.1,::1')
        options['env']=child_env
        if '--user-state' in command:
            state=Path(command[command.index('--user-state')+1]).parent
            if state.name.startswith('rieke-desktop-smoke-'):owned_states.add(state)
        return original(command,*positional,**options)
    backend_output=scratch/'backend.json'
    error=None
    try:
        subprocess.Popen=guarded_spawn
        backend_run(resources,backend_output,recording=args.recording.resolve(strict=True))
    except (Exception,SystemExit) as failure:
        error=type(failure).__name__
    finally:subprocess.Popen=original
    controls=events(control_log);work=events(work_log)
    backend=json.loads(backend_output.read_text()) if backend_output.exists() else {}
    denied=[entry for entry in work if entry['kind'] in {'docker_process_denied','unix_socket_denied'}]
    loaded=[entry for entry in work if entry['kind']=='guard_loaded']
    control_ok=(counts(controls).get('docker_process_denied')==3 and counts(controls).get('unix_socket_denied')==2)
    passed=bool(control_ok and backend.get('passed') and loaded and not denied and not error
                and all(e['docker_cli_unavailable'] and e['sanitized_path'] for e in loaded))
    report={'format':'rieke-desktop-no-docker-e2e','version':1,'passed':passed,
            'production_ready':False,'local_host_only':True,'user_app_untouched':True,
            'host_docker_untouched':True,'resources_reference_kind':'built-candidate',
            'runtime_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'runtime_identity':{k:manifest[k] for k in ('application_version','platform','architecture','python_version','mysql_version')},
            'negative_controls':{'passed':control_ok,'counters':counts(controls),
                                 'denied_before_actual_exec_or_connect':True},
            'workload':{'counters':counts(work),'docker_or_other_unix_attempts':len(denied),
                        'all_guarded_python_processes_hide_docker_cli':bool(loaded) and all(e['docker_cli_unavailable'] for e in loaded),
                        'non_mysql_unix_sockets_denied':True,'external_network_denied':True,
                        'fresh_home_and_sanitized_path':bool(loaded) and all(e['sanitized_path'] for e in loaded)},
            'scientific_backend':backend,
            'limits':['Local host only; this does not replace clean-machine or signed-release qualification.',
                      'Python process/socket interception plus exact native MySQL binary path; no kernel sandbox claim.']}
    if error:report['error_type']=error
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if passed:
        for state in owned_states:shutil.rmtree(state)
        shutil.rmtree(scratch)
    else:print('Private diagnostics retained:',scratch)
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources',type=Path,default=Path(__file__).resolve().parents[1]/'desktop/dist/mac-arm64/Rieke OS.app/Contents/Resources')
    parser.add_argument('--recording',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/dev/desktop-no-docker-e2e.json')
    raise SystemExit(run(parser.parse_args()))
