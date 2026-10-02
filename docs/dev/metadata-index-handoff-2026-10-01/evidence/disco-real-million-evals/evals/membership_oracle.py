"""Verify every returned member against independent real-source lineage truth."""
import hashlib,json,resource,sqlite3,sys,time
from pathlib import Path
ROOT=Path('/private/tmp/disco-real-million-20261001')
sys.path[:0]=[str(ROOT/'typed'),str(ROOT/'evals')]
import compare_million as bench
from typed_bounded import TypedBoundedSidecar
ids,rows,_,values,_,_=bench.old.load_truth()
source=sqlite3.connect(f'file:{bench.REAL}?mode=ro&immutable=1',uri=True)
origin=dict(source.execute('SELECT epoch_uuid,epoch_id FROM epochs'));source.close()
plan=json.loads((ROOT/'evals'/'plan.json').read_text());typed=TypedBoundedSidecar(ROOT/'typed'/'sidecar.sqlite')
receipts=[];started=time.perf_counter()
for case in plan['cases']:
    truth_case=dict(case,scope=case.get('original_scope',case['scope']))
    expected={origin[identity] for identity in bench.old.truth_membership(truth_case,ids,values)}
    where,args=typed._where(case['predicate'],case['scope']);count=0;sha=hashlib.sha256()
    verify_facets=case['label'] in ('largest_cell','largest_block','largest_protocol','global')
    original_values={origin[identity]:value for identity,value in values.items()}
    facet_buckets={field:{} for field in plan['facet_fields']};present={field:0 for field in plan['facet_fields']}
    for number,identity in typed.connection.execute('SELECT c.epoch_id,c.epoch_uuid FROM typed_core c WHERE '+where+' ORDER BY c.sort_rank',args):
        original=(number-1)%2781+1
        assert original in expected,(case['label'],number,original)
        if 'original_scope' in case:assert number<=2781,'Structural scope leaked to a different replay acquisition'
        count+=1;sha.update(identity.encode()+b'\n')
        if verify_facets:
            current=original_values[original]
            for field in plan['facet_fields']:
                if field not in current:continue
                present[field]+=1;value=current[field];key=bench.predicates.equality_key(value)
                bucket=facet_buckets[field].setdefault(key,dict(value=value,type=bench.predicates.kind(value),count=0))
                bucket['count']+=1
    assert count==case['expected_count'],(case['label'],count,case['expected_count'])
    entry=dict(label=case['label'],count=count,ordered_membership_sha256=sha.hexdigest(),all_members_checked=True)
    if verify_facets:
        expected_facets={field:dict(values=list(facet_buckets[field].values())[:60],missing_count=count-present[field],present_count=present[field],values_truncated=len(facet_buckets[field])>60) for field in plan['facet_fields']}
        actual=typed.preview(case['predicate'],case['scope'],facet_fields=plan['facet_fields'])
        assert bench.canonical(actual['facets'])==bench.canonical(expected_facets),case['label']+' facets'
        entry.update(facets_oracle_passed=True,facets_sha256=bench.digest(expected_facets),preview_sha256=bench.digest(actual))
    receipts.append(entry)
    print(json.dumps(dict(label=case['label'],count=count,passed=True)),flush=True)
result=dict(all_passed=True,checks=receipts,seconds=time.perf_counter()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,oracle='Unchanged original real EAV values interpreted in Python; every returned epoch ID checked against source lineage membership, expected replay count proves completeness; core UUID equivalence proved at sidecar build.')
bench.save(ROOT/'evals'/'membership-oracle.json',result);typed.close()
