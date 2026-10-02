import collections,hashlib,json,sqlite3,time
from pathlib import Path
from scoped_full import FullScopedSidecar,TypedBoundedSidecar
from typed_real_previous import predicates,canonical
ROOT=Path('/private/tmp/disco-priority-benchmark-20261001/model');SOURCE=Path('/private/tmp/disco-real-million-20261001/fixture.sqlite');FULL=Path('/private/tmp/disco-real-million-20261001/typed/fixture-sidecar.sqlite')
def file_identity(path):
 s=path.stat();return [s.st_ino,s.st_size,s.st_mtime_ns]
source_before=file_identity(SOURCE);core_before=file_identity(FULL)
start=time.perf_counter();con=sqlite3.connect(SOURCE.as_uri()+'?mode=ro&immutable=1',uri=True)
rows={identity:json.loads(raw) for identity,raw in con.execute('SELECT epoch_uuid,row_json FROM epochs')};order=sorted(rows,key=lambda i:(rows[i]['date'],rows[i]['start_time'],i));values={i:{} for i in order}
for identity,field,raw in con.execute('SELECT e.epoch_uuid,f.field_id,v.value_json FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id)'):values[identity][field]=json.loads(raw)
a=TypedBoundedSidecar(FULL);b=FullScopedSidecar(FULL)
fields=list(a.fields);checks=[];count=0;rejections=[]
for field in fields:
 identity=next(i for i in order if field in values[i]);value=values[identity][field];scope={'cell':rows[identity]['cell_uuid']}
 cases=[dict(field=field,operator='eq',value=value),dict(field=field,operator='ne',value=value),dict(field=field,operator='in',value=[value]),dict(field=field,operator='not_in',value=[value]),dict(field=field,operator='missing'),dict(field=field,operator='exists'),dict(field=field,operator='is_null')]
 kind=predicates.kind(value)
 if kind=='number':cases.extend([dict(field=field,operator='gte',value=value),dict(field=field,operator='lt',value=value)])
 if kind=='array' and value:cases.append(dict(field=field,operator='contains',value=value[0]))
 if kind=='string' and value:cases.append(dict(field=field,operator='contains',value=value[:1]))
 for predicate in cases:
  outcomes=[]
  for candidate in [a,b]:
   try:outcomes.append(('ok',candidate._validate(predicate)))
   except ValueError as error:outcomes.append(('error',str(error)))
  assert outcomes[0]==outcomes[1],('validation',predicate,outcomes)
  if outcomes[0][0]=='error':rejections.append(dict(field=field,predicate=predicate,error=outcomes[0][1]));continue
  truth=[i for i in order if rows[i]['cell_uuid']==scope['cell'] and predicates.matches(predicate,values[i])]
  assert a.membership(predicate,scope)==truth,('control',field,predicate)
  assert b.membership(predicate,scope)==truth,('scoped',field,predicate)
  assert a.preview(predicate,scope)==b.preview(predicate,scope),(field,predicate)
  count+=1
 checks.append(dict(field=field,cases=len(cases),scope=scope))
# All fields' exact summaries remain available, not only the preferred metadata.
scopes=[]
for name in ['cell','block','group']:
 counts=collections.Counter(row[name+'_uuid'] for row in rows.values());scopes.append({name:max(counts,key=counts.get)})
for scope in scopes:assert a.preview(scope=scope,facet_fields=fields)==b.preview(scope=scope,facet_fields=fields),scope
leaves=[{'field':'parameters/lightPath','operator':'eq','value':'DLP'},{'field':'parameters/currentSpotSize','operator':'missing'},{'field':'properties/frameTimesMs','operator':'is_null'}]
# Choose actual text to avoid making assumptions about the mounted corpus.
leaves[0]['value']=next(v['parameters/lightPath'] for v in values.values() if 'parameters/lightPath' in v)
compounds=[{'all':leaves},{'any':leaves},{'not':{'any':leaves}},{'all':[]},{'any':[]}]
for scope in scopes:
 for predicate in compounds:
  truth=[i for i in order if rows[i][next(iter(scope))+'_uuid']==next(iter(scope.values())) and predicates.matches(predicate,values[i])]
  assert b.membership(predicate,scope)==truth,(predicate,scope)
  assert a.preview(predicate,scope,facet_fields=fields[:4])==b.preview(predicate,scope,facet_fields=fields[:4]),(predicate,scope)
# Global and protocol-only plans and values are untouched.
for scope in [None,{'protocol':rows[order[0]]['protocol_name']}]:
 for predicate in leaves+compounds:
  assert a._where(predicate,scope)==b._where(predicate,scope)
  assert a.preview(predicate,scope)==b.preview(predicate,scope)
assert file_identity(SOURCE)==source_before and file_identity(FULL)==core_before
report=dict(all_passed=True,validation_rejections_equivalent=len(rejections),source_identity_before=source_before,source_identity_after=file_identity(SOURCE),core_identity_unchanged=file_identity(FULL)==core_before,field_count=len(fields),field_predicate_cases=count,field_checks=checks,full_field_facet_scopes=scopes,compound_cases=len(compounds)*len(scopes),global_protocol_sql_unchanged=True,rows=len(rows),seconds=time.perf_counter()-start,source_identity_unchanged=True,code_sha256=hashlib.sha256((ROOT/'scoped_full.py').read_bytes()).hexdigest())
(ROOT/'scoped-fixture-smoke.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in {'field_checks','full_field_facet_scopes'}}),flush=True)
a.close();b.close();con.close()
