"""Metadata-only navigation/details and guarded full native catalog check."""
from pathlib import Path
import argparse,collections,json,os,resource,signal,sqlite3,statistics,sys,threading,time
ROOT=Path('/private/tmp/disco-real-million-20261001');BASE=ROOT/'base.sqlite'
sys.path[:0]=[str(ROOT/'typed'),'/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python',str(ROOT/'evals')]
from typed_bounded import TypedBoundedSidecar
import workspace_disk_index as module
from compare_million import save,canonical,digest

def native(candidate):
    prior=json.loads((ROOT/'evals'/'native-page-slow5.json').read_text())
    assert prior['source_stat_unchanged'] and prior['native_open_seconds']>0
    assert prior['input_stat']==[BASE.stat().st_ino,BASE.stat().st_size,BASE.stat().st_mtime_ns]
    seal=json.loads(Path(str(BASE)+'.sha256.json').read_text())
    n=module.DiskMetadataIndex();n.path=BASE;n.generation=seal['generation'];n.project_uuid=seal['project_uuid']
    n._closed=False;n._lease=None;n._signature=module._signature(BASE);n._definitions=candidate.definitions
    n._catalog_cache=None;n._predicate_cache=None;n._epoch_count=1000000
    n._detail_cache=collections.OrderedDict();n._detail_lock=threading.RLock();n._details_reference=None
    n._detail_cache_costs={};n._detail_cache_bytes=0;n._metadata_decoder=module.MetadataDecoder()
    return n

def timed(call,repeats=5):
    times=[];sha=None
    for _ in range(repeats):
        begin=time.perf_counter();value=call();raw=canonical(value);times.append((time.perf_counter()-begin)*1000)
        current=digest(value)
        if sha is not None:assert current==sha
        sha=current
    return dict(first_ms=times[0],warm_median_ms=statistics.median(times[1:]),max_ms=max(times),samples_ms=times,sha256=sha,payload_bytes=len(raw))

p=argparse.ArgumentParser();p.add_argument('--catalog',action='store_true');a=p.parse_args()
path=ROOT/'evals'/('full-catalog.json' if a.catalog else 'extra-actions.json')
result=dict(pid=os.getpid(),status='running',results={},cap_rss_bytes=1024**3,cap_seconds=47)
save(path,result);deadline=[time.monotonic()+47]
def watcher():
    while True:
        reason=None
        if time.monotonic()>deadline[0]:reason='45 second operation deadline'
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>1024**3:reason='1 GiB peak RSS cap'
        if reason:
            result.update(status='guard_stop',reason=reason,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            save(path,result);os._exit(91)
        time.sleep(.1)
threading.Thread(target=watcher,daemon=True).start()
typed=TypedBoundedSidecar(ROOT/'typed'/'sidecar.sqlite');current=native(typed);started=time.perf_counter()
try:
    if a.catalog:
        # Exact unchanged original all-field/global catalog; no warmed catalog
        # persisted on this experimental corpus. Keep its eager cost visible.
        result['operation']='Original global catalog: all 140 stored fields plus derived joint, field stats/grouping/suggestions/layout'
        save(path,result)
        begin=time.perf_counter();catalog=current.catalog();result['results']['global']=dict(milliseconds=(time.perf_counter()-begin)*1000,total=catalog['total'],fields=len(catalog['fields']),sha256=digest(catalog))
    else:
        cell=next(c['scope'] for c in json.loads((ROOT/'evals'/'plan.json').read_text())['cases'] if c['label']=='largest_cell')
        begin=time.perf_counter();first=typed.groups('cell');second=typed.groups('cell',cursor=first['cursor'])
        # Independent structural membership aggregation on native EAV tables.
        number=typed.fields['cell']
        oracle=[dict(uuid=json.loads(raw),count=count) for raw,count in typed.connection.execute('SELECT v.value_json,COUNT(*) FROM native.epoch_values ev JOIN native.field_values v USING(value_id) WHERE ev.field_no=? GROUP BY ev.value_id ORDER BY v.value_json LIMIT 120',(number,))]
        assert first['groups']+second['groups']==oracle
        result['navigation_oracle_seconds']=time.perf_counter()-begin
        result['results']['first_60_cells']=timed(lambda:typed.groups('cell'))
        result['results']['next_60_cells']=timed(lambda:typed.groups('cell',cursor=first['cursor']))
        result['results']['blocks_in_loaded_cell']=timed(lambda:typed.groups('block',scope=cell))
        row=typed.preview(scope=cell)['rows'][0];identity=row['epoch_uuid']
        n=current.details[identity];t=typed.detail(identity);assert canonical(n)==canonical(t)
        result['details_equal']=True;result['detail_payload_bytes']=len(canonical(n))
        result['results']['current_cached_detail']=timed(lambda:current.details[identity])
        result['results']['typed_detail']=timed(lambda:typed.detail(identity))
        # Scoped original complete catalog also sees the million base dictionary.
        identities=list(typed.iter_membership(scope=cell))
        deadline[0]=time.monotonic()+47
        result['current_operation']='full native 687-epoch catalog';save(path,result)
        begin=time.perf_counter();catalog=current.catalog(ids=identities,known_fields=typed.definitions)
        result['results']['full_cell_catalog']=dict(milliseconds=(time.perf_counter()-begin)*1000,total=catalog['total'],fields=len(catalog['fields']),sha256=digest(catalog))
    result['status']='complete'
finally:
    result.update(wall_seconds=time.perf_counter()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(path,result);typed.close();current.close()
    print(json.dumps(result),flush=True)
