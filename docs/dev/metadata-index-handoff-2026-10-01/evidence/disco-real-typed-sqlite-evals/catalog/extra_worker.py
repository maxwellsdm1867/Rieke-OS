"""Attribution check: current full catalog on ANALYZE-only and typed DB clones."""
from pathlib import Path
import argparse
import gc
import hashlib
import json
import os
import resource
import shutil
import signal
import sqlite3
import statistics
import sys
import threading
import time

from catalog_worker import canonical,digest,file_digest,scopes

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
TYPED=Path('/private/tmp/disco-real-typed-sqlite-20261001/model/real-typed.sqlite')
NATIVE=Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')

def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['analyze-only','typed-current-catalog'],required=True);a=p.parse_args()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('90-second process cap')));signal.alarm(90)
    def cap():
        while True:
            if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>512*1024**2: os._exit(91)
            time.sleep(.2)
    threading.Thread(target=cap,daemon=True).start()
    sys.path.insert(0,str(NATIVE));sys.path.insert(0,str(TYPED.parent))
    import workspace_disk_index as module
    from typed_real import table_digest,ORIGINAL_TABLES
    source_hashes={str(path):file_digest(path) for path in [SOURCE,TYPED,NATIVE/'workspace_disk_index.py',NATIVE/'workspace_tree.py',NATIVE/'workspace_predicates.py']}
    prior=json.loads((ROOT/'current-measure.json').read_text())
    assert source_hashes[str(NATIVE/'workspace_disk_index.py')]==prior['sources']['workspace_disk_index.py']
    input_path=SOURCE if a.arm=='analyze-only' else TYPED
    target=ROOT/'inputs'/a.arm/'real.sqlite';target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists(),'Fresh attribution arm required'
    shutil.copyfile(input_path,target)
    connection=sqlite3.connect(target)
    if a.arm=='analyze-only': connection.execute('ANALYZE');connection.commit()
    stats=[list(r) for r in connection.execute('SELECT * FROM sqlite_stat1 ORDER BY 1,2')]
    expected=json.loads((TYPED.parent/'build-receipt.json').read_text())['original_tables']
    preservation={name:table_digest(connection,name) for name in ORIGINAL_TABLES}
    assert preservation==expected,'Original table content changed'
    known_fields=json.loads(connection.execute("SELECT value FROM meta WHERE key='catalog'").fetchone()[0])['fields']
    assert digest(known_fields)==prior['known_fields_sha256']
    selections=[x for x in scopes(connection) if x[0]['label'] in ('global','largest_cell')]
    connection.close()
    seal=json.loads(Path(str(SOURCE)+'.sha256.json').read_text());seal['sha256']=file_digest(target)
    Path(str(target)+'.sha256.json').write_text(json.dumps(seal)+'\n')
    index=module.DiskMetadataIndex.open(target,seal['generation'],seal['project_uuid'])
    report=dict(arm=a.arm,operation='Unmodified current full catalog plus JSON; auxiliary typed tables not queried by current code',input_path=str(input_path),input_sha256=source_hashes[str(input_path)],owned_path=str(target),owned_sha256=seal['sha256'],original_tables=preservation,sqlite_stat1_sha256=digest(stats),sqlite_stat1_rows=len(stats),source_hashes=source_hashes,scopes=[],sampling='One excluded full catalog warmup followed by five warm timed calls per scope; same explicit known_fields; global cache bypassed',limitations=['2781 actual epochs only','Catalog computation plus JSON, not full API preview or app','ANALYZE and typed model attribution on owned copies; no source or mounted changes'])
    by_label={s['label']:s for s in prior['scopes']}
    try:
        for scope,ids in selections:
            def call():
                index._catalog_cache=None
                return index.catalog(None if scope['label']=='global' else ids,known_fields=known_fields)
            expected_scope=by_label[scope['label']]
            assert scope['membership_sha256']==expected_scope['membership_sha256']
            assert digest(call())==expected_scope['output_sha256']
            samples=[]
            for _ in range(5):
                gc.collect();t=time.perf_counter();output=call();encoded=canonical(output);samples.append((time.perf_counter()-t)*1000)
                assert hashlib.sha256(encoded).hexdigest()==expected_scope['output_sha256']
            scope.update(samples_ms=samples,warm_median_ms=statistics.median(samples),warm_min_ms=min(samples),warm_max_ms=max(samples),field_count=len(output['fields']),output_sha256=hashlib.sha256(encoded).hexdigest(),exact_original_catalog_parity=True)
            report['scopes'].append(scope)
            print(json.dumps(dict(arm=a.arm,label=scope['label'],warm_median_ms=scope['warm_median_ms'])),flush=True)
        after={str(path):file_digest(path) for path in [SOURCE,TYPED,NATIVE/'workspace_disk_index.py',NATIVE/'workspace_tree.py',NATIVE/'workspace_predicates.py']}
        assert source_hashes==after
        assert file_digest(target)==seal['sha256']
        report.update(all_oracles_passed=True,source_hashes_after=after,owned_database_unchanged_during_catalog=True,process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2)
        (ROOT/('extra-'+a.arm+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    finally: index.close()

if __name__=='__main__': main()
