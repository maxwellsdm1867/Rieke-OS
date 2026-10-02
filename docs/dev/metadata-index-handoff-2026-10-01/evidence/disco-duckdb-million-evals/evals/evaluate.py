"""Serial-worker typed SQLite/DuckDB build and read comparison, not app qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import statistics
import sys
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode',choices=['fixture','sqlite','duckdb'],required=True)
parser.add_argument('--epochs',type=int,required=True)
parser.add_argument('--csv',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--samples',type=int,default=10)
parser.add_argument('--reuse-database',type=Path)
parser.add_argument('--cap',type=int,default=300)
args=parser.parse_args()
if args.out.exists():parser.error('Use a fresh owned output directory')
args.out.mkdir(parents=True)
sys.dont_write_bytecode=True
sys.path[:0]=[str(Path(__file__).parent/'readmodel'),'/private/tmp/disco-duckdb-deps-20261001']
from projection import AnalyticalProjection,generate_csv,identity
receipt={'epochs':args.epochs,'engine':args.mode,'scope':__doc__,'operations':[],
         'module_sha256':hashlib.sha256((Path(__file__).parent/'readmodel/projection.py').read_bytes()).hexdigest(),
         'samples':args.samples,'phases':{},'passed':False}
start=time.perf_counter();projection=None
def save():
    receipt['seconds']=time.perf_counter()-start
    receipt['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
    (args.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
def log(stage):print(json.dumps({'stage':stage,'seconds':time.perf_counter()-start}),flush=True);save()
def cap(signum,frame):signal.alarm(0);raise TimeoutError('Owned engine evaluation exceeded declared cap')
signal.signal(signal.SIGALRM,cap);signal.alarm(args.cap)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def measure(name,call,oracle):
    log(name);samples=[];hashes=[];value=None
    for _ in range(args.samples):
        began=time.perf_counter();value=call();encoded=json.dumps(value,separators=(',',':')).encode();samples.append(time.perf_counter()-began)
        assert oracle(value),name
        hashes.append(digest(value))
    assert len(set(hashes))==1,name+' unstable'
    receipt['operations'].append({'name':name,'samples_seconds':samples,'first_seconds':samples[0],
          'median_seconds':statistics.median(samples),'warm_median_seconds':statistics.median(samples[1:]) if len(samples)>1 else samples[0],
          'maximum_seconds':max(samples),'json_bytes':len(encoded),'result_sha256':hashes[0],'oracle_passed':True})
    save();return value
try:
    if args.mode=='fixture':
        receipt['fixture']=generate_csv(args.csv,args.epochs,progress=lambda n:log('generated_'+str(n)) if n%100000==0 else None)
        receipt['passed']=True
    else:
        began=time.perf_counter();csv_hash=hashlib.sha256()
        with args.csv.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):csv_hash.update(chunk)
        receipt['csv_sha256']=csv_hash.hexdigest();receipt['phases']['csv_verify']=time.perf_counter()-began
        db=args.reuse_database or args.out/('metadata.sqlite' if args.mode=='sqlite' else 'metadata.duckdb')
        projection=AnalyticalProjection(args.mode,db,temp_directory=args.out/'spill')
        if args.reuse_database:
            receipt['reused_database']=str(args.reuse_database)
        else:
            log('build');receipt['phases'].update(projection.build(args.csv))
        projection.close();projection=None
        began=time.perf_counter();projection=AnalyticalProjection(args.mode,db,temp_directory=args.out/'spill')
        receipt['phases']['reopen_seconds']=time.perf_counter()-began
        assert projection.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]==args.epochs
        if args.mode=='duckdb':
            import duckdb
            receipt['duckdb_version']=duckdb.__version__
        else:
            import sqlite3
            receipt['sqlite_version']=sqlite3.sqlite_version
        first=measure('epoch_first_60',lambda:projection.page(),lambda v:[r['epoch_uuid'] for r in v['items']]==[identity(i) for i in range(60)])
        measure('epoch_next_60',lambda:projection.page(cursor=first['next_cursor']),lambda v:[r['epoch_uuid'] for r in v['items']]==[identity(i) for i in range(60,120)])
        cells=sorted((identity(args.epochs+i),i) for i in range((args.epochs+99)//100))
        root=measure('tree_cells_first_60',lambda:projection.tree_children('cell'),lambda v:v['total']==len(cells) and [r['key'] for r in v['items']]==[c[0] for c in cells[:60]])
        measure('tree_cells_next_60',lambda:projection.tree_children('cell',cursor=root['next_cursor']),lambda v:[r['key'] for r in v['items']]==[c[0] for c in cells[60:120]])
        cell,number=cells[0];begin=number*100
        blocks=measure('tree_expand_cell',lambda:projection.tree_children('block',parent={'cell_uuid':cell}),lambda v:v['total']==5 and [r['key'] for r in v['items']]==[identity(2*args.epochs+begin//20+i) for i in range(5)])
        block=blocks['items'][0]['key']
        measure('tree_expand_block',lambda:projection.page(parent={'block_uuid':block}),lambda v:[r['epoch_uuid'] for r in v['items']]==[identity(i) for i in range(begin,begin+20)])
        measure('epoch_details',lambda:projection.detail(identity(3)),lambda v:v['parameters']=={'contrast':.3,'seed':3,'stimTime':1000,'currentMean':0})
        measure('bounded_filter_preview',lambda:projection.preview({'contrast':.3}),lambda v:v['count']==args.epochs//5 and [r['synthetic_index'] for r in v['items']]==list(range(3,303,5)))
        measure('high_cardinality_seed_facet',lambda:projection.facets('seed',{'contrast':.3}),lambda v:v['has_more'] and [r['value'] for r in v['items']]==list(range(3,303,5)))
        ids=[identity(i) for i in range(20)]
        measure('tag_membership_20_metadata_join',lambda:projection.tag_page(ids),lambda v:[r['epoch_uuid'] for r in v['items']]==ids)
        receipt['passed']=True
except Exception as error:
    receipt['error']=str(error)
    import traceback
    receipt['traceback']=traceback.format_exc();print(receipt['traceback'],flush=True)
finally:
    signal.alarm(0)
    if projection:projection.close()
    receipt['module_sha256_after']=hashlib.sha256((Path(__file__).parent/'readmodel/projection.py').read_bytes()).hexdigest()
    if receipt['module_sha256_after']!=receipt['module_sha256']:
        receipt['passed']=False;receipt['error']='Source changed during measurement'
    save();print(json.dumps({'passed':receipt['passed'],'seconds':receipt['seconds'],'peak_mib':receipt['peak_rss_bytes']/2**20}),flush=True)
raise SystemExit(0 if receipt['passed'] else 1)
