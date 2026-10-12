#!/usr/bin/env python3
"""Owned local overview experiment; real HTTP/React, synthetic admission/SQL.

Not a release gate. Launches only disposable fixtures. Compare identical scales
and this exact harness. No user project or installed runtime is used.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]

def serve(source,output,epochs):
    sys.path.insert(0,str(ROOT/'benchmarks/workflow'))
    from server import build
    from werkzeug.serving import make_server
    fixture=server=None
    try:
        fixture,app,meta=build(source,output,epochs,200)
        service=fixture.case.service
        from workspace_service import WorkspaceService
        from workspace_state_generation import GenerationToken
        from disco.workbench.recipes import checksum
        service.__class__=WorkspaceService
        service.Event=fixture.case.events
        class Authority:
            def token(self,protocol=None):
                saved=checksum(fixture.case.curation.rows)
                shared=checksum(json.dumps(app.extensions['shared_annotations'].Annotation.rows,sort_keys=True,default=str))
                return GenerationToken('overview-fixture',service.project['project_uuid'],'shared-epoch',int(shared[:12],16),protocol,'protocol-epoch' if protocol else None,int(saved[:12],16) if protocol else None)
            def assert_current_locked(self,expected):
                if self.token(expected.protocol_uuid)!=expected:raise ValueError('Changed fixture state')
        fixture.case.store.state_generation=Authority()
        # A separate, disjoint protocol supplies ambient metadata. The active
        # frozen cohort remains 180 epochs irrespective of total project size.
        ambient='00000000-0000-0000-0000-999999999999'
        entry=copy.deepcopy(service.protocols[service.protocol_id])
        entry['definition'].update(protocol_uuid=ambient,name='Ambient protocol')
        active=set(service.ids)
        members=[key for key in service.rows if key not in active]
        entry['result'].update(protocol_uuid=ambient,epochs=[{'uuid':key,'metadata_hash':service._fingerprints[key]} for key in members])
        service.protocols[ambient]=entry
        meta.update(ambient_protocol=ambient,admissions=meta['admissions']+['native generation token double'],active_count=180)
        server=make_server('127.0.0.1',0,app,threaded=True)
        meta['port']=server.server_port
        (output/'server.json').write_text(json.dumps(meta,indent=2))
        def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        server.serve_forever()
    finally:
        if server:server.server_close()
        if fixture:fixture.doCleanups()
        (output/'cleanup.json').write_text(json.dumps({'server_closed':server is not None,'fixture_closed':fixture is not None}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=10000)
    parser.add_argument('--serve',action='store_true')
    args=parser.parse_args()
    if not 1000<=args.epochs<=1000000:parser.error('Use 1000..1000000 epochs')
    args.output.mkdir(parents=True,exist_ok=False)
    if args.serve:return serve(args.source_root.resolve(),args.output.resolve(),args.epochs)
    import time
    server=None
    receipt={'status':'incomplete','source':str(args.source_root.resolve()),'epochs':args.epochs,'samples':5,
             'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.source_root,text=True).strip(),
             'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=args.source_root,text=True).strip()),
             'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()+(ROOT/'benchmarks/overview-browser.mjs').read_bytes()).hexdigest(),
             'limitations':['Owned synthetic SQL and metadata admission; real production HTTP and React browser views.','Development build and DOM/two RAF timings; not installed Electron or compositor qualification.']}
    try:
        with (args.output/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-B',__file__,'--serve','--source-root',str(args.source_root),'--output',str(args.output/'server'),'--epochs',str(args.epochs)],stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+180
            while not (args.output/'server/server.json').exists():
                if server.poll() is not None:raise RuntimeError('Owned fixture failed; inspect server.log')
                if time.monotonic()>deadline:raise TimeoutError('Owned fixture startup')
                time.sleep(.1)
            with (args.output/'browser.log').open('w') as browser_log:
                subprocess.run(['node',str(ROOT/'benchmarks/overview-browser.mjs'),'--source-root',str(args.source_root),'--server-json',str(args.output/'server/server.json'),'--output',str(args.output/'browser.json')],stdout=browser_log,stderr=subprocess.STDOUT,check=True,timeout=600)
            receipt['browser']=json.loads((args.output/'browser.json').read_text())
            receipt['status']='passed'
    finally:
        if server is not None:
            server.terminate()
            try:server.wait(timeout=20)
            except subprocess.TimeoutExpired:server.kill();server.wait();receipt['status']='cleanup-failed'
        receipt['cleanup']=json.loads((args.output/'server/cleanup.json').read_text()) if (args.output/'server/cleanup.json').exists() else {'missing':True}
        (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
