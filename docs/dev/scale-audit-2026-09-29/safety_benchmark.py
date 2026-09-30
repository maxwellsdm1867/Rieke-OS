import sys,contextlib,copy,datetime as dt,json,platform,statistics,tempfile,time,uuid
from pathlib import Path
from types import SimpleNamespace
sys.path[:0]=['python','python/tests']
from test_workspace_curation import Table
from workspace_annotations import SharedAnnotations
from workspace_state_snapshot import save,TABLES

def uid(i):return str(uuid.UUID(int=i))
class Result:
 def __init__(self,rows):self.rows=rows
 def fetchall(self):return self.rows
 def fetchone(self):return self.rows[0] if self.rows else None
class Connection:
 in_transaction=False
 def __init__(self,state):self.state=state;self.sql_reads=[]
 @property
 def transaction(self):return contextlib.nullcontext()
 def query(self,sql,args=None,as_dict=False):
  self.sql_reads.append(sql)
  if 'GET_LOCK' in sql or 'RELEASE_LOCK' in sql:return Result([(1,)])
  if 'information_schema.tables' in sql:return Result([(x,) for x in self.state]+[('source',)])
  if sql.startswith('SHOW COLUMNS'):return Result([('tags','json')] if 'shared_annotation' in sql else [('recipe','json'),('summary','json')])
  if sql.startswith('SELECT source_sha256,manifest'):return Result([('a'*64,{'source_path':'synthetic.h5','metadata_sha256':'b'*64})])
  for key,rows in self.state.items():
   if f'`{key}`' in sql:return Result(rows)
  raise ValueError(sql)

def measure(fn,repetitions=3):
 values=[]
 for _ in range(repetitions):
  start=time.perf_counter();out=fn();values.append((time.perf_counter()-start)*1000)
 return {'median_ms':round(statistics.median(values),3),'runs_ms':[round(x,3) for x in values]},out

results={'date':'2026-09-29','method':'Synthetic metadata and annotation tables; actual SharedAnnotations.apply_batch, change_revision, suggestions, state snapshot capture/compact/save functions. SQL double, no network/real SQL latency, no transaction copying. Snapshot writes/fsync are real into TemporaryDirectory. Dataset contains one annotation per epoch, one author, two tags, one source and 100 epochs per cell. Single tag mutation only. Three runs per operation; project fully resident before measurement.','python':platform.python_version(),'platform':platform.platform(),'cases':[]}
for n in (1000,10000,50000,100000):
 project=uid(1);author=uid(2);now=dt.datetime(2026,9,29)
 rows={uid(1000+i):{'epoch_uuid':uid(1000+i),'cell_uuid':uid(1000000+i//100),'source_sha256':'a'*64} for i in range(n)}
 annotations=[{'project_uuid':project,'target_kind':'epoch','target_uuid':key,'profile_uuid':author,'tags':['QC','reviewed'],'author_name':'Synthetic author','revision':1,'updated_at':now} for key in rows]
 state={'shared_annotation':annotations,'annotation_profile':[{'project_uuid':project,'profile_uuid':author,'display_name':'Synthetic author','created_at':now,'created_by':'actor'}]}
 connection=Connection(state);dj=SimpleNamespace(conn=lambda:connection)
 service=SimpleNamespace(project={'project_uuid':project},dj=dj,rows=rows,cells={r['cell_uuid']:{} for r in rows.values()},_fingerprints={key:'b'*64 for key in rows},match_predicate=lambda predicate,eligible:(predicate,eligible,None))
 table=Table(('project_uuid','target_kind','target_uuid','profile_uuid'),annotations)
 profiles=Table(('project_uuid','profile_uuid'),state['annotation_profile']);events=Table(('event_uuid',))
 store=SharedAnnotations(service,(profiles,table,events));key=next(iter(rows));counter=[1]
 def update():
  result=store.apply_batch([{'target_kind':'epoch','target_uuid':key,'profile_uuid':author,'tags_add':['hot' if counter[0]%2 else 'cold'],'tags_remove':['cold' if counter[0]%2 else 'hot'],'expected_revision':counter[0]}],'actor');counter[0]+=1;return result
 mutation,_=measure(update)
 full_annotation_reads=[len(annotations) for r in table.read_log if all(not isinstance(x,list) for x in r['restrictions'])]
 revision,_=measure(store.change_revision)
 def suggestions():store._vocabulary=None;return store.suggestions('r',12)
 vocabulary,_=measure(suggestions)
 case={'epochs':n,'annotation_rows':n,'single_annotation_apply_batch':mutation,'full_annotation_rows_loaded_per_write':full_annotation_reads[:3],'cross_process_change_revision':revision,'suggestions_rebuild':vocabulary,'snapshots':[]}
 with tempfile.TemporaryDirectory(prefix='rieke-safety-') as directory:
  root=Path(directory);(root/'protocols').mkdir();(root/'project.json').write_text(json.dumps({'project_uuid':project,'format':'recording-project','version':1,'name':'Synthetic'}))
  for pin_count in (0,1,10):
   members=[{'uuid':key,'metadata_hash':'b'*64} for key in sorted(rows)]
   state['explorer_revision']=[{'project_uuid':project,'revision_uuid':uid(500000+i),'parent_revision_uuid':None,'summary':{},'recipe':{'revision_uuid':uid(500000+i),'epochs':members,'predicate':{'all':[]},'source_revisions':['a'*64],'diff':{},'content_sha256':'c'*64}} for i in range(pin_count)]
   state['protocol_binding']=[{'project_uuid':project,'protocol_uuid':uid(600000+i),'revision_uuid':uid(500000+i)} for i in range(pin_count)]
   def snapshot():return save(root,connection,day='2026-09-29',service=service)
   timings,out=measure(snapshot)
   case['snapshots'].append({'active_pins':pin_count,'save':timings,'state_bytes':out['bytes'],'changed_last_run':out['changed']})
 results['cases'].append(case)
 print(json.dumps(case),flush=True)
Path('docs/dev/scale-audit-2026-09-29/safety-benchmark.json').write_text(json.dumps(results,indent=2)+'\n')
