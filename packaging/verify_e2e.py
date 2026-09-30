"""Real HTTP/native-MySQL/recording smoke test after ./install.sh.

Usage: .rieke-runtime/venv/bin/python packaging/verify_e2e.py --source /path/to/recording.h5
Creates an isolated workspace, rejects Docker invocations and preserves a receipt.
The H5 is read-only and is never included in the release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from workspace_installation import initialize_workspace
from workspace_native_mysql import stop_native_database


def request(base, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(base+path, data=body, headers={'Content-Type':'application/json','X-Workspace-Request':'1'})
    with urlopen(req, timeout=360) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve(strict=True)
    before=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
    output=Path(tempfile.mkdtemp(prefix='rieke-e2e-'))
    workspace=initialize_workspace(output/'workspace',ROOT)
    trap=output/'tools';trap.mkdir();docker=trap/'docker'
    docker.write_text('#!/bin/sh\necho invoked >> "'+str(output/'docker-invoked')+'"\nexit 99\n');docker.chmod(0o755)
    env={**os.environ,'PATH':str(trap)+os.pathsep+os.environ.get('PATH','')}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    projects=[]
    log=(output/'launcher.log').open('w')
    launcher=subprocess.Popen([str(ROOT/'start.sh'),'--workspace',str(workspace),'--port',str(port)],env=env,stdout=log,stderr=log)
    proof={'platform':sys.platform,'checks':[], 'source_sha256':before}
    def passed(name):
        proof['checks'].append(name);print('PASS:',name,flush=True)
    try:
        for _ in range(300):
            try:
                assert request(base,'/api/health')['status']=='ready';break
            except (OSError,AssertionError):
                if launcher.poll() is not None:raise RuntimeError((output/'launcher.log').read_text())
                time.sleep(.2)
        else:raise TimeoutError('Launcher did not become ready')
        passed('clean-runtime launcher health')
        with urlopen(base) as response:assert b'<title>Disco</title>' in response.read()
        passed('built browser app served')
        assert request(base,'/api/projects')['projects']==[]
        created=request(base,'/api/projects',{'name':'End-to-end verification'})
        print('Created:',json.dumps(created),flush=True)
        project=created.get('project',created);projects.append(project)
        opened=request(base,f"/api/projects/{project['uuid']}/open",{})
        project_base=opened['url'].rstrip('/')
        assert request(project_base,'/api/overview')['counts']['epochs']==0
        assert request(project_base,'/api/storage')['database']['status']=='running'
        passed('create and open native project without Docker')
        job=request(project_base,'/api/imports',{'source_path':str(source)})
        print('Import:',json.dumps(job),flush=True)
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            jobs=request(project_base,'/api/jobs')['jobs']
            if jobs and jobs[0]['status'] in ('complete','completed','failed','interrupted','complete_with_warnings'):
                assert jobs[0]['status'] in ('complete','completed'), jobs[0]
                break
            time.sleep(.5)
        else:raise TimeoutError('Import did not complete')
        request(project_base,'/api/metadata/refresh',{})
        for _ in range(120):
            overview=request(project_base,'/api/overview')
            if overview['counts']['epochs']>0:break
            time.sleep(.5)
        assert overview['counts']['epochs']>0, overview
        proof['counts']=overview['counts'];passed('real H5 parsed and committed to native SQL')
        protocol=overview['protocols'][0]['protocol_uuid']
        page=request(project_base,f'/api/protocols/{protocol}/epochs?limit=1')
        epoch=page['epochs'][0]['epoch_uuid']
        detail=request(project_base,f'/api/epochs/{epoch}')
        print('Epoch keys:',list(detail),flush=True)
        response=next(row for row in detail['streams'] if row['kind']=='responses')
        stream=response['uuid']
        trace=request(project_base,f'/api/epochs/{epoch}/trace?stream_uuid={stream}&count=100')
        import h5py
        import numpy as np
        with h5py.File(source, 'r') as h5:
            expected=h5[response['data_path']][:100]['quantity'].astype(float)
        np.testing.assert_array_equal(trace['values'],expected)
        assert trace['decimated'] is False
        passed('HTTP trace samples match independent raw H5 read')
        details=request(project_base,f'/api/protocols/{protocol}')
        exported=request(project_base,f'/api/protocols/{protocol}/exports',
            {'format':'wheeler-sqlite','query_revision':details['query_revision']})
        assert exported
        passed('Wheeler SQLite export published from native SQL')
        # Reopen the same project after cleanly stopping its server and SQL.
        record=json.loads((Path(project['path'])/'logs/workspace-server.json').read_text())
        os.kill(record['pid'],signal.SIGTERM);time.sleep(.5)
        stop_native_database(project['path'])
        reopened=request(base,f"/api/projects/{project['uuid']}/open",{})
        again=request(reopened['url'].rstrip('/'),'/api/overview')
        assert again['counts']['epochs']==overview['counts']['epochs']
        passed('database stop/restart preserves imported epoch count')
        assert hashlib.file_digest(source.open('rb'),'sha256').hexdigest()==before
        assert not (output/'docker-invoked').exists()
        passed('source bytes unchanged; zero Docker invocations')
        proof['status']='passed'
    finally:
        for project in projects:
            try:
                record=json.loads((Path(project['path'])/'logs/workspace-server.json').read_text())
                os.kill(record['pid'],signal.SIGTERM)
            except (OSError,ValueError):pass
            try:stop_native_database(project['path'])
            except Exception as error:print('Cleanup:',error)
        launcher.terminate();launcher.wait(timeout=15);log.close()
        (output/'receipt.json').write_text(json.dumps(proof,indent=2)+'\n')
        print('Evidence:',output,flush=True)

if __name__=='__main__':main()
