"""Private native MySQL benchmark. Only a disposable project is touched."""
import json, os, statistics, sys, tempfile, time, uuid
from pathlib import Path
from types import SimpleNamespace
import datajoint as dj
import workspace_native_mysql as native
from workspace_project_database import ensure_project_database
from workspace_annotations import SharedAnnotations
from workspace_curation import CurationStore

# The reviewed application runtime is read-only; every DB write is under temp.
native.ROOT=Path(os.environ['RIEKE_BENCH_RUNTIME_ROOT']).resolve()
def summary(values):
    ordered=sorted(values)
    return {'median_ms':round(statistics.median(ordered),4),'p95_ms':round(ordered[int(len(ordered)*.95)-1],4)}

def run():
 with tempfile.TemporaryDirectory(prefix='rieke-undo-native-') as temporary:
  root=Path(temporary)/'project';root.mkdir();(root/'database').mkdir()
  identity=str(uuid.uuid4());catalog=native.native_catalog(identity)
  (root/'project.json').write_text(json.dumps({'format':'recording-project','version':1,'project_uuid':identity,'name':'Disposable undo benchmark'}))
  (root/'catalog.json').write_text(json.dumps(catalog));(root/'database/service.json').write_text(json.dumps(catalog['managed_database']))
  ensure_project_database(root)
  connection=None
  try:
   connection=dj.Connection(**native.connection_parameters(root))
   wrapper=SimpleNamespace(conn=lambda:connection,Schema=lambda name:dj.Schema(name,connection=connection),Manual=dj.Manual)
   ids=[str(uuid.uuid4()) for _ in range(5000)];cells={str(uuid.uuid4()):{}}
   import random
   results=[];randomizer=random.Random(19)
   for family in ('annotations','curation'):
    for count,repeats in ((1,200),(500,30),(1000,20)):
      project=str(uuid.uuid4());protocol=str(uuid.uuid4());scope=ids[:count]
      service=SimpleNamespace(dj=wrapper,project={'project_uuid':project},rows={key:{} for key in ids},cells=cells)
      store=SharedAnnotations(service) if family=='annotations' else CurationStore(wrapper,project)
      if family=='annotations':
       author=store.default_profile['profile_uuid'];store.update('epoch',scope,author,{'tags_add':['warmup']},{key:0 for key in scope},'Benchmark')
      else:store.update(protocol,scope,{'tags_add':['warmup']},{key:0 for key in scope},{key:'a'*64 for key in scope},'Benchmark')
      revision=1;measures={enabled:{'latencies':[],'bytes':[],'sql':[],'inverse':[],'inverse_bytes':[],'serialize':[]} for enabled in (False,True)}
      original=connection.query
      orders=[[False,True],[True,False]]*(repeats//2);randomizer.shuffle(orders)
      for order in orders:
       for enabled in order:
        calls=[0]
        def measured(*args,**kwargs):calls[0]+=1;return original(*args,**kwargs)
        connection.query=measured
        changes={'tags_add':['tag']} if revision%2 else {'tags_remove':['tag']}
        if family=='curation':changes['included']=revision%2==1
        started=time.perf_counter()
        if family=='annotations':result=store.update('epoch',scope,author,changes,{key:revision for key in scope},'Benchmark',include_undo=enabled)
        else:result=store.update(protocol,scope,changes,{key:revision for key in scope},{key:'a'*64 for key in scope},'Benchmark',include_undo=enabled)
        serialize_start=time.perf_counter();encoded=json.dumps(result,default=str).encode();serialize_ms=(time.perf_counter()-serialize_start)*1000;m=measures[enabled]
        m['serialize'].append(serialize_ms);m['inverse_bytes'].append(len(json.dumps(result.get('undo',{})).encode()) if enabled else 0)
        m['latencies'].append((time.perf_counter()-started)*1000);m['bytes'].append(len(encoded));m['sql'].append(calls[0]);m['inverse'].append(result.get('undo',{}).get('kind'));revision+=1
        connection.query=original
      rows=(store.Annotation if family=='annotations' else store.Curation)&{'project_uuid':project}
      events=store.Event&{'project_uuid':project};persisted=events.to_dicts()
      assert all('undo' not in json.dumps(row['payload']) for row in persisted)
      for enabled,m in measures.items():
       results.append({'family':family,'targets':count,'enabled':enabled,'repeats':repeats,**summary(m['latencies']),
        'median_serialization_ms':round(statistics.median(m['serialize']),4),'median_inverse_bytes':statistics.median(m['inverse_bytes']),'sql_per_edit':sorted(set(m['sql'])),'median_response_bytes':statistics.median(m['bytes']),
        'persisted_rows_combined':len(rows),'event_rows_combined':len(events),'inverse_kinds':sorted(set(value for value in m['inverse'] if value))})
   print('RESULT_JSON='+json.dumps(results))
   if os.environ.get('RIEKE_BENCH_OUTPUT'):Path(os.environ['RIEKE_BENCH_OUTPUT']).write_text(json.dumps(results,indent=2))
  finally:
   if connection is not None:connection.close()
   native.stop_native_database(root)
if __name__=='__main__':run()
