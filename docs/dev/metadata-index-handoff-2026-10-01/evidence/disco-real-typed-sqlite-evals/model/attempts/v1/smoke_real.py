from pathlib import Path
import hashlib,json,sqlite3,time
from typed_real import TypedReal,canonical,predicates,file_sha
from workspace_metadata_objects import Decoder
ROOT=Path('/private/tmp/disco-real-typed-sqlite-20261001/model')
SOURCE=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
start=time.perf_counter()
source=sqlite3.connect(SOURCE.as_uri()+'?mode=ro&immutable=1',uri=True)
candidate=TypedReal(ROOT/'real-typed.sqlite')
rows={identity:json.loads(raw) for identity,raw in source.execute('SELECT epoch_uuid,row_json FROM epochs')}
order=sorted(rows,key=lambda identity:(rows[identity]['date'],rows[identity]['start_time'],identity))
values={identity:{} for identity in order}
fields=['protocol','cell','parameters/useRandomSeed','parameters/contrast','parameters/centerOffset','parameters/amp','parameters/lightPath','parameters/seed']
for identity,field,raw in source.execute('SELECT e.epoch_uuid,f.field_id,v.value_json FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id IN ('+','.join('?' for _ in fields)+')',fields):
    values[identity][field]=json.loads(raw)
cases=[]
for field in fields:
    observed=list(dict.fromkeys(canonical(current[field]) for current in values.values() if field in current))
    literal=json.loads(observed[0])
    cases.append({'field':field,'operator':'eq','value':literal})
    if predicates.kind(literal)=='number':
        cases.append({'field':field,'operator':'gte','value':literal})
    cases.append({'field':field,'operator':'missing'})
cases.append({'field':'parameters/useRandomSeed','operator':'eq','value':1.0})
cases.append({'all':[cases[0],cases[5]]})
cases.append({'any':[cases[3],cases[7]]})
checks=[]
for case in cases:
    truth=[identity for identity in order if predicates.matches(case,values[identity])]
    actual=candidate.membership(case)
    assert actual==truth,(case,len(actual),len(truth))
    first=candidate.preview(case,facet_fields=['parameters/useRandomSeed'],limit=60)
    assert first['count']==len(truth)
    assert first['rows']==[rows[identity] for identity in truth[:60]]
    checks.append({'predicate':case,'count':len(truth),'plan':candidate.explain(case)})
# Two pages are bounded and cursor ranks cross source insertion ordering.
page=candidate.page(limit=60)
page2=candidate.page(cursor=page['cursor'],limit=60)
assert page['rows']+page2['rows']==[rows[i] for i in order[:120]]
# Full native DTO uses exact existing production decoder against both databases.
for identity in [order[0],order[len(order)//2],order[-1]]:
    raw,blob=source.execute('SELECT row_json,detail_blob FROM epochs WHERE epoch_uuid=?',[identity]).fetchone()
    assert candidate.detail(identity)==Decoder().decode(source,json.loads(raw),blob)
# Independent groups counts from unchanged row JSON.
for kind in ['cell','block']:
    expected={}
    for row in rows.values():
        key=row[kind+'_uuid']; expected[key]=expected.get(key,0)+1
    all_groups=[];cursor=None
    while True:
        page=candidate.groups(kind=kind,cursor=cursor)
        all_groups+=page['groups'];cursor=page['cursor']
        if cursor is None:break
    assert all_groups==[{'uuid':k,'count':v} for k,v in sorted(expected.items())]
receipt={'all_checks_passed':True,'predicates':checks,'page_count':2,'detail_count':3,'group_kinds':['cell','block'],'seconds':time.perf_counter()-start,'source_sha256_unchanged':file_sha(SOURCE)}
(ROOT/'smoke-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'checks':len(checks),'seconds':receipt['seconds'],'all_passed':True}),flush=True)
candidate.close();source.close()
