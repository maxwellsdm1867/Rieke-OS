import hashlib,json,time,uuid
from pathlib import Path
from types import SimpleNamespace
from test_workspace_state_generation import NativeGenerationTests as T
from workspace_recovery_generation import RecoveryTracker
from workspace_curation_vocabulary import CurationVocabulary
paths=[Path('python')/name for name in ('workspace_curation_vocabulary.py','workspace_shared_tag_index.py','workspace_recovery_generation.py')]
hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
report={'epochs':100000,'protocols':2,'tags_per_record':5,'scope':'Isolated native vocabulary: canonical JSON curation, generation triggers and derived SQLite; excludes metadata/shared/recovery mirror workloads','hashes_before':hashes()}
T.setUpClass();index=None
try:
 c=T.connection;p=str(uuid.uuid4());protocols=[str(uuid.uuid4()) for _ in range(2)];epochs=[str(uuid.UUID(int=i+1)) for i in range(100000)]
 started=time.perf_counter()
 with c._conn.cursor() as cur:
  for position,protocol in enumerate(protocols):
   tags=json.dumps([f'dataset:{position}']+[f'dataset-tag:{i}' for i in range(1,5)])
   for offset in range(0,len(epochs),1000):
    cur.executemany('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',[(p,protocol,e,tags) for e in epochs[offset:offset+1000]])
 report['seed_seconds']=time.perf_counter()-started
 tracker=RecoveryTracker(c,p).bootstrap();assert tracker.ready,tracker.reason
 index=CurationVocabulary(SimpleNamespace(project_uuid=p,dj=SimpleNamespace(conn=lambda:c)),tracker)
 def status():return dict(c.query("SHOW SESSION STATUS WHERE Variable_name IN ('Handler_read_next','Handler_read_key','Rows_sent','Bytes_sent')").fetchall())
 def measure(label):
  before=status();t=time.perf_counter();result=index.suggestions('dataset',30);elapsed=time.perf_counter()-t;after=status()
  report[label]={'seconds':elapsed,'sql':{k:int(after[k])-int(before[k]) for k in before},'stats':dict(index.stats)}
  assert len(result['tags'])==6 and all(x['count']==100000 for x in result['tags']),result
 measure('cold');measure('warm')
 c.query('UPDATE recording_workspace.curation SET tags=JSON_ARRAY_APPEND(tags,%s,%s) WHERE project_uuid=%s AND protocol_uuid=%s AND epoch_uuid=%s',('$','edited',p,protocols[0],epochs[0]))
 measure('after_edit')
 assert index.suggestions('edited',30)['tags']==[{'tag':'edited','count':1}]
 report['storage']=index.storage_stats();report['hashes_after']=hashes();report['passed']=report['hashes_before']==report['hashes_after']
 print(json.dumps(report,indent=2),flush=True)
 Path('docs/dev/scale-audit-2026-09-29/curation-vocabulary-200000-scalar-keyset.json').write_text(json.dumps(report,indent=2)+'\n')
finally:
 if index:index.close()
 T.tearDownClass()
