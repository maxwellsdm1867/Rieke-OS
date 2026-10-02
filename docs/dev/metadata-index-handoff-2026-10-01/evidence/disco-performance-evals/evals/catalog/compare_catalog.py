"""Compare exact catalog and matching output on the same sealed metadata index.

The baseline implementation is read from Git, never checked out over the running
candidate. This microbenchmark excludes HTTP, MySQL and browser rendering.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-ref',default='a8fac2c293ccf4fa73a4eb5e93673b41620b1d13')
    parser.add_argument('--repeats',type=int,default=4)
    args=parser.parse_args()
    if args.repeats<2:parser.error('--repeats needs first plus at least one warm observation')
    source=Path(__file__).resolve().parents[4]
    sys.path.insert(0,str(source/'python'))
    from workspace_disk_index import DiskMetadataIndex
    baseline_source=subprocess.check_output(['git','show',args.baseline_ref+':python/workspace_disk_index.py'],cwd=source)
    seal=json.loads(Path(str(args.index)+'.sha256.json').read_text())
    report={'scope':'Existing complete scoped catalog and exact predicate matching, same immutable generation. Excludes Flask serialization, MySQL, memberships and browser paint.',
        'baseline_ref':args.baseline_ref,'baseline_module_sha256':hashlib.sha256(baseline_source).hexdigest(),
        'candidate_module_sha256':hashlib.sha256((source/'python/workspace_disk_index.py').read_bytes()).hexdigest(),
        'database_sha256':seal['sha256'],'generation':seal['generation'],'implementations':{}}
    predicate={'field':'parameters/contrast','operator':'eq','value':.3}
    with tempfile.TemporaryDirectory(prefix='disco-catalog-baseline-') as temporary:
        baseline_file=Path(temporary)/'baseline_disk_index.py';baseline_file.write_bytes(baseline_source)
        spec=importlib.util.spec_from_file_location('baseline_disk_index',baseline_file)
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        for name,cls in [('baseline',baseline.DiskMetadataIndex),('candidate',DiskMetadataIndex)]:
            index=cls.open(args.index,seal['generation'],seal['project_uuid'])
            try:
                fields=index.catalog()['fields'];_,ids=index.match(predicate)
                report['matched_count']=len(ids);report['epoch_count']=index._epoch_count
                records=[]
                for action,call in [('scoped_catalog',lambda:index.catalog(ids,fields)),
                                    ('predicate_match',lambda:index.match(predicate))]:
                    samples=[]
                    for _ in range(args.repeats):
                        gc.collect();start=time.perf_counter();result=call();samples.append(time.perf_counter()-start)
                    records.append({'action':action,'samples_seconds':samples,'first_seconds':samples[0],
                        'warm_median_seconds':statistics.median(samples[1:]),'warm_maximum_seconds':max(samples[1:]),
                        'result_sha256':digest(result)})
                    print(json.dumps({'implementation':name,**records[-1]}),flush=True)
                report['implementations'][name]=records
            finally:index.close()
    for old,new in zip(report['implementations']['baseline'],report['implementations']['candidate']):
        assert old['action']==new['action'] and old['result_sha256']==new['result_sha256'],'Complete result changed'
    report['exact_parity']=True
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
