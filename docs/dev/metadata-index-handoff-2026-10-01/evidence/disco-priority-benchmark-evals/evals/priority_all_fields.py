"""Rare fields remain queryable: full140 fixture payload comparison."""
import json,sqlite3,time
import compare as h
from priority_sidecar import PrioritySidecar
from typed_bounded import TypedBoundedSidecar
def main():
    start=time.monotonic()
    full=TypedBoundedSidecar(h.PRE/'typed'/'fixture-sidecar.sqlite')
    priority=PrioritySidecar(h.ROOT/'model'/'fixture-priority.sqlite')
    source=sqlite3.connect('file:'+str(h.PRE/'fixture.sqlite')+'?mode=ro&immutable=1',uri=True)
    identity,raw=source.execute('SELECT epoch_uuid,row_json FROM epochs LIMIT 1').fetchone()
    scope={'cell':json.loads(raw)['cell_uuid']};checks=[]
    for field,number in full.fields.items():
        raw=source.execute('SELECT value_json FROM field_values WHERE field_no=? LIMIT 1',[number]).fetchone()[0]
        predicate={'field':field,'operator':'eq','value':json.loads(raw)}
        # Native validation rejects literals above its size limit in both arms.
        outputs=[]
        for arm in (full,priority):
            try:outputs.append(('value',arm.preview(predicate,scope,facet_fields=[field])))
            except ValueError as exc:outputs.append(('error',str(exc)))
        assert outputs[0]==outputs[1],field
        checks.append({'field':field,'outcome':outputs[0][0]})
    assert full.preview(scope=scope,facet_fields=list(full.fields))==priority.preview(scope=scope,facet_fields=list(full.fields))
    result={'all_passed':True,'fields':len(checks),'cases':checks,'all140_facet_payload_equal':True,'wall_seconds':time.monotonic()-start,'materializations':priority.materializations}
    h.save(h.ROOT/'evals'/'priority-all-fields.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','materializations')}))
    full.close();priority.close();source.close()
if __name__=='__main__':main()
