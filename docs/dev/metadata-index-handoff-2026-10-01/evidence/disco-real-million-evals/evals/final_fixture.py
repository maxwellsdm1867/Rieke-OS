"""Run all prior smoke checks and exact selective facets for every native field."""
import json,runpy,sqlite3,sys,time
from pathlib import Path
ROOT=Path('/private/tmp/disco-real-million-20261001');REPO=Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
sys.path[:0]=[str(ROOT/'typed'),str(ROOT/'evals'),str(REPO),'/private/tmp/disco-real-typed-sqlite-20261001/evals']
import typed_sidecar
from typed_bounded import TypedBoundedSidecar
from workspace_disk_index import DiskMetadataIndex
import compare_preview as old
started=time.perf_counter()
typed_sidecar.TypedRealSidecar=TypedBoundedSidecar
sys.argv=['smoke_sidecar.py','--source',str(ROOT/'fixture.sqlite'),'--target',str(ROOT/'typed'/'fixture-sidecar.sqlite'),'--receipt',str(ROOT/'evals'/'final-fixture-smoke.json')]
runpy.run_path(str(ROOT/'typed'/'smoke_sidecar.py'),run_name='__main__')
source=ROOT/'fixture.sqlite';seal=json.loads(Path(str(source)+'.sha256.json').read_text());native=DiskMetadataIndex.open(source,seal['generation'],seal['project_uuid'])
con=sqlite3.connect(source);rows={uuid:json.loads(raw) for uuid,raw in con.execute('SELECT epoch_uuid,row_json FROM epochs')};con.close()
ids=sorted(rows,key=lambda uuid:(rows[uuid]['date'],rows[uuid]['start_time'],uuid));rank={uuid:i for i,uuid in enumerate(ids,1)}
current=old.NativePreview(native,rank);candidate=TypedBoundedSidecar(ROOT/'typed'/'fixture-sidecar.sqlite')
fields=list(candidate.fields);checks=[]
row=rows[ids[0]]
for scope in [dict(cell=row['cell_uuid']),dict(block=row['block_uuid'])]:
    for at in range(0,len(fields),2):
        selected=fields[at:at+2];a=current.preview(scope=scope,facet_fields=selected);b=candidate.preview(scope=scope,facet_fields=selected)
        assert old.canonical(a)==old.canonical(b),(scope,selected)
        checks.append(dict(scope=scope,fields=selected,sha256=old.digest(a)))
result=dict(all_passed=True,all_fields=len(fields),scopes=['cell','block'],comparisons=len(checks),checks=checks,seconds=time.perf_counter()-started)
(ROOT/'evals'/'final-selective-facets.json').write_text(json.dumps(result,indent=2)+'\n')
current.close();candidate.close();print(json.dumps(dict(final_field_oracles_passed=True,fields=len(fields),comparisons=len(checks),seconds=result['seconds'])),flush=True)
