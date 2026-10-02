"""Small-fixture runner only; never opens private real-million corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--adapter',choices=['native','typed'],default='native')
    parser.add_argument('--implementation-root',type=Path)
    parser.add_argument('--expected-commit')
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    repository=args.implementation_root or Path(__file__).resolve().parents[2]
    run_git=lambda *command:subprocess.check_output(['git','-C',str(repository),*command],text=True).strip()
    commit=run_git('rev-parse','HEAD')
    if args.implementation_root:
        if not args.expected_commit or args.expected_commit!=commit:
            parser.error('External implementation requires its exact committed HEAD')
    if run_git('status','--porcelain','--','python'):
        parser.error('Application implementation has uncommitted changes')
    sys.path.insert(0,str(repository/'python'))
    from truth import Truth
    from checks import qualify
    from storage import physical_assets,sqlite_components,normalized
    truth=Truth();started=time.perf_counter()
    if args.adapter=='native':
        from native import NativeAdapter as Adapter
    else:
        from core_adapter import CoreAdapter as Adapter
    with tempfile.TemporaryDirectory(prefix='rieke-qualification-') as folder:
        path=Path(folder)/('typed.sqlite' if args.adapter=='typed' else 'native.sqlite')
        adapter=Adapter(path,truth.fixture())
        try:
            receipt=qualify(adapter,truth)
            receipt.update(adapter=args.adapter,implementation_commit=commit,
                runtime=dict(python=sys.version,sqlite=sqlite3.sqlite_version,platform=platform.platform()),
                source_hashes={str(p.relative_to(repository)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (repository/'python').glob('workspace_*') if p.is_file() and p.suffix=='.py'},
                wall_seconds=time.perf_counter()-started,
                harness_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in Path(__file__).parent.iterdir() if p.is_file() and p.suffix=='.py'})
            dbs=sorted(Path(folder).glob('*.sqlite'))
            assets=[dict(path=p,role=('incremental-index' if p.name=='typed.sqlite' else 'base-metadata') if p.suffix=='.sqlite' else 'seal-or-build-receipt',generation='qualification-v1') for p in sorted(Path(folder).iterdir()) if p.is_file()]
            physical=physical_assets(assets)
            total=normalized(physical,12,sum(len(v) for v in truth.values.values()),
                             base_bytes=sum(p.stat().st_size for p in dbs if p.name=='native.sqlite'),
                             added_bytes=sum(p.stat().st_size for p in dbs if p.name=='typed.sqlite'))
            receipt['storage']=dict(physical=physical,normalized=total,
                                   components={p.name:sqlite_components(p) for p in dbs},
                                   growth={'status':'unrun'},incremental_import={'status':'unrun'},
                                   rebuild_highwater={'status':'unrun'})
        finally:adapter.close()
    if args.adapter=='typed':
        from core_faults import qualify_faults
        receipt['core_faults']=qualify_faults(truth)
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('status','adapter','fields','checks','predicate_scenarios','real_million','wall_seconds')}))


if __name__=='__main__':main()
