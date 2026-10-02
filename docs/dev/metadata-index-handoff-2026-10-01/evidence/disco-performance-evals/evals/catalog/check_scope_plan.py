"""Bounded read-only diagnostic: automatic versus scope-first catalog plans."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def cap(*ignored):raise TimeoutError('90 second owned scope-plan check cap')
    signal.signal(signal.SIGALRM,cap);signal.alarm(90)
    repo=Path(__file__).resolve().parents[4];sys.path.insert(0,str(repo/'python'))
    path=args.index.resolve();seal=json.loads(Path(str(path)+'.sha256.json').read_text())
    connection=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    ids=[row[0] for row in connection.execute('SELECT epoch_uuid FROM epochs ORDER BY epoch_id')];connection.close()
    source=(repo/'python/workspace_disk_index.py').read_text()
    condition="len(rows)<getattr(self,'_epoch_count',float('inf'))"
    assert condition in source,'Candidate plan selection changed; update this diagnostic explicitly'
    report={'scope':'Candidate-only plan diagnostic: first plus one warm observation. Excludes API/database annotations/browser. Same sealed index, complete catalog hash required.',
            'database_sha256':seal['sha256'],'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'operations':[]}
    with tempfile.TemporaryDirectory(prefix='disco-catalog-plan-') as temporary:
        for name,condition_value in [('automatic','False'),('scope-first','True')]:
            file=Path(temporary)/(name+'.py');file.write_text(source.replace(condition,condition_value))
            spec=importlib.util.spec_from_file_location('plan_'+name,file)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            index=module.DiskMetadataIndex.open(path,seal['generation'],seal['project_uuid'])
            try:
                fields=index.catalog()['fields']
                for subset in (ids[:60],ids):
                    samples=[]
                    for _ in range(2):
                        beg=time.perf_counter();result=index.catalog(subset,fields);samples.append(time.perf_counter()-beg)
                    receipt={'implementation':name,'epochs':len(subset),'seconds':samples,
                             'hash':hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
                    report['operations'].append(receipt);print(json.dumps(receipt),flush=True)
            finally:index.close()
    assert all(report['operations'][i]['hash']==report['operations'][i+2]['hash'] for i in range(2))
    report['exact_parity']=True
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
