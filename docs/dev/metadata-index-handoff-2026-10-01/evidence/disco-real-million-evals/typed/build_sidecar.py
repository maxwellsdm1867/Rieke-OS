import argparse,json,resource,time
from pathlib import Path
from typed_sidecar import build
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--target',required=True);p.add_argument('--receipt',required=True)
p.add_argument('--max-seconds',type=float,default=300);p.add_argument('--min-free-gib',type=float,default=4);p.add_argument('--max-rss-gib',type=float,default=1)
a=p.parse_args();started=time.perf_counter()
try:
    result=build(a.source,a.target,max_seconds=a.max_seconds,min_free_gib=a.min_free_gib,max_rss_gib=a.max_rss_gib,
                 progress=lambda value:print(json.dumps(value),flush=True))
except Exception as error:
    result={'all_passed':False,'error':repr(error),'seconds':time.perf_counter()-started,'max_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
Path(a.receipt).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if not result['all_passed']:raise SystemExit(1)
