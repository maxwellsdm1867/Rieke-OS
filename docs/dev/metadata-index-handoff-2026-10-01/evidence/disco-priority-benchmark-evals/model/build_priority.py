import argparse,json
from pathlib import Path
from priority_sidecar import build
p=argparse.ArgumentParser();p.add_argument('--full',required=True);p.add_argument('--target',required=True);p.add_argument('--fields',required=True);p.add_argument('--receipt',required=True);p.add_argument('--max-seconds',type=float,default=180)
a=p.parse_args();raw=json.loads(Path(a.fields).read_text());fields=raw if isinstance(raw,list) else raw['hot_fields']
try:r=build(a.full,a.target,fields,a.max_seconds)
except Exception as e:
 r=dict(all_passed=False,error_type=type(e).__name__,error=str(e));Path(a.receipt).write_text(json.dumps(r,indent=2)+'\n');raise
Path(a.receipt).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
