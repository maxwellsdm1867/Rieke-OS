import hashlib,json,sqlite3,time,sys
from pathlib import Path
from priority_sidecar import PrioritySidecar,build,predicates
from typed_bounded import TypedBoundedSidecar
ROOT=Path('/private/tmp/disco-priority-benchmark-20261001/model')
SOURCE=Path('/private/tmp/disco-real-million-20261001/fixture.sqlite')
FULL=Path('/private/tmp/disco-real-million-20261001/typed/fixture-sidecar.sqlite')
TARGET=ROOT/'fixture-priority.sqlite'
receipt=build(FULL,TARGET,['protocol','parameters/currentSpotSize'])
(ROOT/'fixture-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
con=sqlite3.connect(SOURCE.as_uri()+'?mode=ro&immutable=1',uri=True)
rows={identity:json.loads(raw) for identity,raw in con.execute('SELECT epoch_uuid,row_json FROM epochs')}
order=sorted(rows,key=lambda i:(rows[i]['date'],rows[i]['start_time'],i))
values={i:{} for i in order}
for identity,field,raw in con.execute('SELECT e.epoch_uuid,f.field_id,v.value_json FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id)'):
 values[identity][field]=json.loads(raw)
a=TypedBoundedSidecar(FULL);b=PrioritySidecar(TARGET)
fields=['parameters/useRandomSeed','parameters/currentSpotSize','metadata/block/parameters/spotSizes','metadata/block/parameters/spotIntensity','properties/frameTimesMs','metadata/experiment/attributes/purpose']
cases=[]
for field in fields:
 observed=next(v[field] for v in values.values() if field in v)
 cases.extend([dict(field=field,operator='eq',value=observed),dict(field=field,operator='missing'),dict(field=field,operator='exists'),dict(field=field,operator='is_null')])
 if predicates.kind(observed)=='number':cases.append(dict(field=field,operator='gte',value=observed))
 if predicates.kind(observed)=='array' and observed:cases.append(dict(field=field,operator='contains',value=observed[0]))
cases.extend([dict(field='parameters/useRandomSeed',operator='eq',value=1.0),dict(field='epoch',operator='eq',value=order[0]),{'all':[cases[0],cases[4]]},{'any':[cases[0],cases[4]]},{'not':cases[0]}])
checks=[]
for predicate in cases:
 truth=[i for i in order if predicates.matches(predicate,values[i])]
 assert b.membership(predicate)==truth,predicate
 assert a.preview(predicate,facet_fields=fields)==b.preview(predicate,facet_fields=fields),predicate
 checks.append(dict(predicate=predicate,count=len(truth)))
for scope in [None,{'cell':rows[order[0]]['cell_uuid']},{'block':rows[order[0]]['block_uuid']},order[:90]]:
 one=a.preview(scope=scope,facet_fields=fields);two=b.preview(scope=scope,facet_fields=fields);assert one==two
 if one['cursor']:assert a.preview(scope=scope,facet_fields=fields,cursor=one['cursor'])==b.preview(scope=scope,facet_fields=fields,cursor=one['cursor'])
for kind in ['cell','block']:assert a.groups(kind)==b.groups(kind)
for identity in order[:3]:assert a.detail(identity)==b.detail(identity)
# New instance UUID equality must bypass deferred million-cardinality dictionary.
c=PrioritySidecar(TARGET);assert c.preview(dict(field='epoch',operator='eq',value=order[0]))==a.preview(dict(field='epoch',operator='eq',value=order[0]));assert c.materializations==[]
report=dict(all_passed=True,cases=checks,cold_materializations=b.materializations,uuid_lookup_materializations=c.materializations,rows=len(rows))
(ROOT/'fixture-smoke.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(all_passed=True,checks=len(checks),rows=len(rows),added_bytes=receipt['added_bytes'])))
a.close();b.close();c.close();con.close()
