"""Load an explicitly selected list of original Symphony H5 files via the public API.

Run against a disposable project created in the browser. Original files are
read-only. This is a measurement tool, not a promise of unlimited project size.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def call(base, path, body=None, timeout=120):
    req=Request(base.rstrip('/')+path, data=None if body is None else json.dumps(body).encode(),
                headers={'Content-Type':'application/json','X-Workspace-Request':'1'})
    started=time.monotonic()
    try:
        with urlopen(req,timeout=timeout) as response:
            result=json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'{error.code}: {error.read().decode()}') from error
    return result, round(time.monotonic()-started,3)


def snapshot(base, project):
    overview, elapsed=call(base,'/api/overview')
    record=json.loads((project/'logs/workspace-server.json').read_text())
    rss=subprocess.check_output(['ps','-o','rss=','-p',str(record['pid'])],text=True).strip()
    return {'counts':overview['counts'],'overview_seconds':elapsed,'api_rss_mib':round(int(rss)/1024,1)},overview


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--project-dir',type=Path,required=True)
    parser.add_argument('--source-list',type=Path,required=True,help='JSON array of paths or objects with path')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sources=json.loads(args.source_list.read_text())
    paths=[Path(row['path'] if isinstance(row,dict) else row).resolve(strict=True) for row in sources]
    if any(p.suffix.lower()!='.h5' or p.name.lower().endswith('.auisql.h5') for p in paths):
        raise ValueError('Choose only original .h5 recordings; .auisql.h5 files are excluded')
    args.output.mkdir(parents=True,exist_ok=False)
    report={'imports':[],'samples':[],'failures':[],'source_bytes':sum(p.stat().st_size for p in paths)}
    def save():
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for index,path in enumerate(paths,1):
        print(f'Import {index}/{len(paths)}: {path.name}',flush=True)
        before=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
        started=time.monotonic()
        submitted,_=call(args.base_url,'/api/imports',{'source_path':str(path)})
        deadline=started+1200
        while time.monotonic()<deadline:
            result,_=call(args.base_url,'/api/jobs')
            job=next((r for r in result['jobs'] if r.get('job_uuid')==submitted['job_uuid']),None)
            if job and job['status'] in {'complete','completed','duplicate','failed','interrupted','complete_with_warnings'}:
                break
            time.sleep(1)
        else:raise TimeoutError(f'Import timeout for {path.name}')
        elapsed=round(time.monotonic()-started,2)
        after=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
        assert before==after,'Source recording changed'
        result={'filename':path.name,'bytes':path.stat().st_size,'status':job['status'],
                'seconds':elapsed,'source_unchanged':True}
        if job['status'] not in {'complete','completed','duplicate'}:
            result['error']=job.get('error') or job.get('message')
            report['failures'].append(result)
        report['imports'].append(result)
        sample,overview=snapshot(args.base_url,args.project_dir)
        sample['after_file']=index;report['samples'].append(sample);save()
        print(json.dumps({**result,**sample}),flush=True)
    sample,overview=snapshot(args.base_url,args.project_dir)
    protocols=overview['protocols']
    protocol=max(protocols,key=lambda r:r['counts']['epochs'])['protocol_uuid']
    paths=['/api/overview','/api/data-stores',f'/api/protocols/{protocol}/epochs?limit=80',
           f'/api/protocols/{protocol}/tree','/api/explore/predicate-fields']
    report['latency']={}
    for route in paths:
        durations=[]
        for _ in range(5):
            _,elapsed=call(args.base_url,route);durations.append(elapsed)
        report['latency'][route]={'median_seconds':round(statistics.median(durations),3),
                                 'max_seconds':max(durations),'samples':durations}
        print(route,report['latency'][route],flush=True);save()
    with ThreadPoolExecutor(max_workers=4) as pool:
        durations=list(pool.map(lambda _:call(args.base_url,f'/api/protocols/{protocol}/epochs?limit=80')[1],range(12)))
    report['concurrent_page_reads']={'requests':12,'concurrency':4,'max_seconds':max(durations),
                                     'median_seconds':statistics.median(durations)}
    report['final']=sample;report['status']='passed' if not report['failures'] else 'completed_with_import_failures'
    save();print('Complete:',args.output/'report.json',flush=True)

if __name__=='__main__':main()
