"""Read-only real full catalog comparison; serial independent process per arm."""
from pathlib import Path
import argparse
import collections
import cProfile
import gc
import hashlib
import json
import platform
import pstats
import resource
import os
import shutil
import signal
import sqlite3
import statistics
import sys
import time
import threading

HERE = Path(__file__).resolve().parent

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def file_digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def scopes(sql):
    n = sql.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]
    selected = [('global', None, None)]
    for label, field in [('largest_protocol','protocol'), ('largest_cell','cell')]:
        value, _ = sql.execute('SELECT v.value_json,COUNT(*) FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? GROUP BY v.value_id ORDER BY COUNT(*) DESC,v.value_json LIMIT 1', [field]).fetchone()
        selected.append((label, field, value))
    candidates = []
    for field, raw, count in sql.execute('SELECT f.field_id,v.value_json,COUNT(*) FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id) GROUP BY f.field_no,v.value_id'):
        value=json.loads(raw)
        if 0<count<n and field.startswith(('parameters/','metadata/','properties/')): candidates.append((field,raw,count,value))
    for label, kind in [('numeric_value',(int,float)), ('text_value',str)]:
        candidate=min((x for x in candidates if isinstance(x[3],kind) and not isinstance(x[3],bool)), key=lambda x:abs(x[2]-n/2))
        selected.append((label,candidate[0],candidate[1]))
    missing=sql.execute('SELECT f.field_id,COUNT(ev.epoch_id) AS recorded FROM fields f LEFT JOIN epoch_values ev USING(field_no) GROUP BY f.field_no HAVING recorded>0 AND recorded<? ORDER BY ABS(recorded-?) LIMIT 1',[n,n/2]).fetchone()
    selected.append(('missing_field',missing[0],'__ABSENT__'))
    result=[]
    for label, field, raw in selected:
        if field is None: query,args='SELECT epoch_uuid FROM epochs ORDER BY epoch_id',[]
        elif raw=='__ABSENT__':
            query='SELECT e.epoch_uuid FROM epochs e WHERE NOT EXISTS(SELECT 1 FROM epoch_values ev JOIN fields f USING(field_no) WHERE ev.epoch_id=e.epoch_id AND f.field_id=?) ORDER BY e.epoch_id';args=[field]
        else:
            query='SELECT e.epoch_uuid FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? AND v.value_json=? ORDER BY e.epoch_id';args=[field,raw]
        ids=[x[0] for x in sql.execute(query,args)]
        result.append((dict(label=label,field=field,epochs=len(ids),membership_sha256=digest(ids),selection='absent' if raw=='__ABSENT__' else 'observed equality' if field else 'all'),ids))
    return result

def category(sql):
    s=sql.lower()
    if s.startswith('insert') and 'scope' in s: return 'scope_population'
    if s.startswith('create temp'): return 'scope_create'
    if 'row_json' in s: return 'row_json'
    if 'having count(distinct' in s: return 'within_cell_variation'
    if 'count(*)' in s and 'field_values' in s: return 'field_statistics'
    if 'select distinct field_id' in s: return 'present_fields'
    if 'epoch_values' in s and 'field_values' in s: return 'suggestion_or_joint_values'
    if 'from fields' in s: return 'field_definitions'
    if 'epochs' in s: return 'epoch_lookup'
    return 'other'

class SQLStats:
    def __init__(self): self.data=collections.defaultdict(lambda:dict(statements=0,trace_statements=0,execute_ms=0.0,fetch_ms=0.0));self.plans={}
    def record(self,cat,kind,elapsed): self.data[cat][kind]+=elapsed*1000

def install_sql_stats(stats):
    original=sqlite3.connect
    class Cursor:
        def __init__(self,raw,cat): self.raw=raw;self.cat=cat
        def __iter__(self): return self
        def __next__(self):
            t=time.perf_counter()
            try: return next(self.raw)
            finally: stats.record(self.cat,'fetch_ms',time.perf_counter()-t)
        def fetchone(self):
            t=time.perf_counter()
            try: return self.raw.fetchone()
            finally: stats.record(self.cat,'fetch_ms',time.perf_counter()-t)
        def fetchall(self):
            t=time.perf_counter()
            try: return self.raw.fetchall()
            finally: stats.record(self.cat,'fetch_ms',time.perf_counter()-t)
        def __getattr__(self,name): return getattr(self.raw,name)
    class Connection(sqlite3.Connection):
        def execute(self,sql,parameters=()):
            cat=category(sql);stats.data[cat]['statements']+=1
            if sql.lstrip().upper().startswith('SELECT') and cat not in stats.plans:
                stats.plans[cat]=[list(x) for x in super().execute('EXPLAIN QUERY PLAN '+sql,parameters)]
            t=time.perf_counter()
            try: return Cursor(super().execute(sql,parameters),cat)
            finally: stats.record(cat,'execute_ms',time.perf_counter()-t)
        def executemany(self,sql,parameters):
            cat=category(sql);stats.data[cat]['statements']+=1
            t=time.perf_counter()
            try: return Cursor(super().executemany(sql,parameters),cat)
            finally: stats.record(cat,'execute_ms',time.perf_counter()-t)
    def wrapped(*a,**kw):
        kw['factory']=Connection
        connection=original(*a,**kw)
        def trace(sql): stats.data[category(sql)]['trace_statements']+=1
        connection.set_trace_callback(trace)
        return connection
    sqlite3.connect=wrapped
    return original

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--index',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--arm',required=True)
    p.add_argument('--repeats',type=int,default=5);p.add_argument('--phase',choices=['prepare','measure','profile'],default='measure')
    a=p.parse_args();sys.path.insert(0,str(a.source_root/'python'))
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('120-second process cap')));signal.alarm(120)
    def memory_cap():
        while True:
            peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if platform.system()!='Darwin': peak*=1024
            if peak>512*1024**2: os._exit(91)
            time.sleep(.2)
    threading.Thread(target=memory_cap,daemon=True).start()
    import workspace_disk_index as module
    seal=json.loads(Path(str(a.index)+'.sha256.json').read_text())
    assert file_digest(a.index)==seal['sha256']
    origin=a.index.resolve()
    clone=HERE/'inputs'/a.arm/'real.sqlite';clone.parent.mkdir(parents=True,exist_ok=True)
    if not clone.exists(): shutil.copyfile(origin,clone)
    if not Path(str(clone)+'.sha256.json').exists(): shutil.copyfile(Path(str(origin)+'.sha256.json'),Path(str(clone)+'.sha256.json'))
    assert file_digest(clone)==seal['sha256'];a.index=clone
    sql=sqlite3.connect(a.index.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    known_fields=json.loads(sql.execute("SELECT value FROM meta WHERE key='catalog'").fetchone()[0])['fields']
    selected=scopes(sql)
    schema=[list(r) for r in sql.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
    report=dict(arm=a.arm,phase=a.phase,source_root=str(a.source_root),original_database=str(origin),worker_database=str(clone),database_sha256=seal['sha256'],schema_sha256=digest(schema),python=sys.version,sqlite=sqlite3.sqlite_version,known_fields_count=len(known_fields),known_fields_sha256=digest(known_fields),sources={name:file_digest(a.source_root/'python'/name) for name in ['workspace_disk_index.py','workspace_tree.py','workspace_predicates.py']},scopes=[],limitations=['Actual 2781 epochs only; not a million-epoch qualification','Full catalog plus JSON only; not full API preview or app','Explicit identical known_fields and global cache bypass; scope extraction/open excluded','Exact sealed database cloned per worker before timing; normal production lifecycle preserved'])
    sql.close()
    if a.phase=='prepare':
        report['scopes']=[x[0] for x in selected];a.output.write_text(json.dumps(report,indent=2)+'\n');return
    index=module.DiskMetadataIndex.open(a.index,seal['generation'],seal['project_uuid'])
    index._catalog_cache=None;index._predicate_cache=None
    try:
        if a.phase=='measure':
            for scope,ids in selected:
                samples=[];checksums=[]
                for _ in range(a.repeats):
                    gc.collect();index._catalog_cache=None
                    t=time.perf_counter();output=index.catalog(None if scope['label']=='global' else ids,known_fields=known_fields);encoded=canonical(output);samples.append((time.perf_counter()-t)*1000)
                    checksums.append(hashlib.sha256(encoded).hexdigest())
                assert len(set(checksums))==1
                scope.update(samples_ms=samples,first_ms=samples[0],warm_median_ms=statistics.median(samples[1:]),warm_max_ms=max(samples[1:]),median_ms=statistics.median(samples),output_sha256=checksums[0],output_bytes=len(encoded),field_count=len(output['fields']),field_ids_sha256=digest([f['id'] for f in output['fields']]),suggestions_sha256=digest(output['suggestions']),layout_sha256=digest(output['suggested_layout']))
                report['scopes'].append(scope);print(json.dumps(dict(arm=a.arm,label=scope['label'],epochs=scope['epochs'],median_ms=scope['median_ms'],field_count=scope['field_count'])),flush=True)
        else:
            for scope,ids in [x for x in selected if x[0]['label'] in ('global','largest_protocol')]:
                prof=cProfile.Profile()
                prof.enable();out=index.catalog(None if scope['label']=='global' else ids,known_fields=known_fields);canonical(out);prof.disable()
                path=HERE/(a.arm+'-'+scope['label']+'.prof');prof.dump_stats(path)
                view=pstats.Stats(prof)
                top=[]
                for (filename,line,name),(cc,nc,tt,ct,callers) in sorted(view.stats.items(),key=lambda x:x[1][3],reverse=True)[:40]: top.append(dict(file=filename,line=line,function=name,primitive_calls=cc,calls=nc,self_ms=tt*1000,cumulative_ms=ct*1000))
                stats=SQLStats();original=install_sql_stats(stats)
                try:
                    traced=index.catalog(None if scope['label']=='global' else ids,known_fields=known_fields)
                    assert digest(traced)==digest(out)
                finally: sqlite3.connect=original
                scope.update(output_sha256=digest(out),top_cumulative=top,sql_by_category=dict(stats.data),query_plans=stats.plans,profile_file=str(path))
                report['scopes'].append(scope)
        assert file_digest(a.index)==seal['sha256'];report['database_unchanged']=True
        report['process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024)
        a.output.write_text(json.dumps(report,indent=2)+'\n')
    finally: index.close()

if __name__=='__main__': main()
