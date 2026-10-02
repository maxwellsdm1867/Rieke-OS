"""Full-scope old/new parity, latency and isolated-process RSS diagnostic."""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time


def worker(args,source):
    import psutil
    sys.path.insert(0,str(source/'python'))
    if args.module:
        spec=importlib.util.spec_from_file_location('baseline_full_catalog',args.module)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls=module.DiskMetadataIndex
    else:
        from workspace_disk_index import DiskMetadataIndex
        cls=DiskMetadataIndex
    path=args.index.resolve();seal=json.loads(Path(str(path)+'.sha256.json').read_text())
    index=cls.open(path,seal['generation'],seal['project_uuid'])
    try:
        fields=index.catalog()['fields']
        with index._connect([]) as connection:
            ids=[row[0] for row in connection.execute('SELECT epoch_uuid FROM epochs ORDER BY epoch_id')]
        process=psutil.Process();gc.collect();rss_before=process.memory_info().rss/1024**2
        samples=[];rss=[]
        for _ in range(args.repeats):
            gc.collect();beg=time.perf_counter()
            if args.mode=='uncached-global':
                index._catalog_cache=None;result=index.catalog()
            else:result=index.catalog(ids,fields)
            samples.append(time.perf_counter()-beg);rss.append(process.memory_info().rss/1024**2)
        receipt={'mode':args.mode,'epochs':len(ids),'samples_seconds':samples,
            'first_seconds':samples[0],'warm_median_seconds':statistics.median(samples[1:]),
            'warm_maximum_seconds':max(samples[1:]),'rss_before_mib':rss_before,'rss_after_each_mib':rss,
            'process_peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),
            'result_sha256':hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()}
        args.output.write_text(json.dumps(receipt,indent=2))
        print(json.dumps(receipt),flush=True)
    finally:index.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-ref',default='a8fac2c293ccf4fa73a4eb5e93673b41620b1d13')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--mode',choices=['explicit-full-scope','uncached-global'],default='explicit-full-scope')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--module',type=Path)
    args=parser.parse_args()
    if args.repeats<2:parser.error('Need first and at least one warm observation')
    source=Path(__file__).resolve().parents[4]
    if args.worker:return worker(args,source)
    baseline=subprocess.check_output(['git','show',args.baseline_ref+':python/workspace_disk_index.py'],cwd=source)
    seal=json.loads(Path(str(args.index)+'.sha256.json').read_text())
    report={'scope':'Read-only full-generation catalog on same sealed index. Independent serial workers for honest process peak RSS; first and two warm observations. Excludes index build, MySQL, API and browser.',
        'mode':args.mode,'baseline_ref':args.baseline_ref,'baseline_module_sha256':hashlib.sha256(baseline).hexdigest(),
        'candidate_module_sha256':hashlib.sha256((source/'python/workspace_disk_index.py').read_bytes()).hexdigest(),
        'database_sha256':seal['sha256'],'implementations':{},'wall_time_cap_seconds':90}
    deadline=time.monotonic()+90
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='disco-full-catalog-') as temporary:
        file=Path(temporary)/'baseline.py';file.write_bytes(baseline)
        for name in ('baseline','candidate'):
            output=Path(temporary)/(name+'.json')
            command=[sys.executable,'-B',str(Path(__file__).resolve()),'--worker','--index',str(args.index),
                     '--output',str(output),'--repeats',str(args.repeats),'--mode',args.mode]
            if name=='baseline':command.extend(['--module',str(file)])
            try:
                result=subprocess.run(command,timeout=max(.1,deadline-time.monotonic()),check=True,capture_output=True,text=True)
                report['implementations'][name]=json.loads(output.read_text())
                print(json.dumps({'implementation':name,**report['implementations'][name]}),flush=True)
                args.output.write_text(json.dumps(report,indent=2))
            except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as error:
                report.update(status='bounded_diagnostic_failed',failure=str(error));args.output.write_text(json.dumps(report,indent=2));raise
    assert report['implementations']['baseline']['result_sha256']==report['implementations']['candidate']['result_sha256'],'Full catalog changed'
    report.update(status='complete',exact_parity=True)
    args.output.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
