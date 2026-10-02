"""Read-only real metadata oracle + bounded same-payload query comparison.

No live service, annotations, MySQL, waveform reads or mounted-project writes.
The baseline uses the unchanged production DiskMetadataIndex methods.
"""
from pathlib import Path
import argparse, collections, hashlib, json, os, resource, signal, sqlite3
import statistics, sys, threading, time

ROOT=Path('/private/tmp/disco-real-typed-sqlite-20261001')
SOURCE=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
REPO=Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
PROJECT=Path('/PATH/TO/LOCAL_HOME/Documents/RecordingWorkspace/LOCAL_NATIVE_PROJECT')
sys.path[:0]=[str(REPO),str(ROOT/'model')]
from workspace_disk_index import DiskMetadataIndex
import workspace_predicates as predicates

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def file_digest(path):
    result=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()
def protected_inputs():
    paths=[SOURCE,Path(str(SOURCE)+'.sha256.json'), REPO/'workspace_disk_index.py',REPO/'workspace_predicates.py',
        REPO/'workspace_metadata_objects.py',ROOT/'model'/'typed_real.py',Path(__file__).resolve()]
    for kind in ('source-projections','metadata'):
        directory=PROJECT/'cache'/kind
        manifest=directory/'.current-generations.json'
        paths.append(manifest)
        for name in json.loads(manifest.read_bytes())['keep']:
            paths.append(directory/name)
            seal=Path(str(directory/name)+('.sha256.json' if kind=='metadata' else ''))
            if kind=='source-projections':seal=(directory/name).with_suffix('.sha256')
            paths.append(seal)
    return {str(path):file_digest(path) for path in paths}
def open_native():
    seal=json.loads(Path(str(SOURCE)+'.sha256.json').read_bytes())
    return DiskMetadataIndex.open(SOURCE,seal['generation'],seal['project_uuid'])
def facets(values,identities,fields):
    result={}
    for field in fields:
        indexed={};buckets=[];present=0
        for identity in identities:
            current=values[identity]
            if field not in current:continue
            present+=1;value=current[field];key=predicates.equality_key(value)
            if key not in indexed:
                indexed[key]=dict(value=value,type=predicates.kind(value),count=0)
                buckets.append(indexed[key])
            indexed[key]['count']+=1
        result[field]=dict(values=buckets[:60],missing_count=len(identities)-present,
            present_count=present,values_truncated=len(buckets)>60)
    return result
class NativePreview:
    def __init__(self,native,ordinals): self.native=native;self.ordinals=ordinals
    def membership(self,predicate=None,scope=None):
        if isinstance(scope,dict):
            scope_predicate={'all':[{'field':field,'operator':'eq','value':value} for field,value in scope.items()]}
            _,ids=self.native.match(scope_predicate)
        else:ids=scope
        if predicate is not None:matched=self.native.match(predicate,ids=ids)[1]
        elif ids is not None:matched=list(ids)
        else:
            with self.native._connect() as con:matched=[identity for identity, in con.execute('SELECT epoch_uuid FROM epochs ORDER BY epoch_id')]
        # Production WorkspaceService preloads rows and sorts metadata query rows.
        return sorted(matched,key=self.ordinals.__getitem__)
    def preview(self,predicate=None,scope=None,facet_fields=(),limit=60,cursor=None):
        ids=self.membership(predicate,scope)
        eligible=[identity for identity in ids if self.ordinals[identity]>(cursor or 0)]
        with self.native._connect(eligible[:limit]) as con:
            rows=[json.loads(raw) for raw, in con.execute('SELECT e.row_json FROM scope s JOIN epochs e USING(epoch_id) ORDER BY s.ordinal')]
        next_cursor=self.ordinals[eligible[limit-1]] if len(eligible)>limit else None
        values=dict(self.native.values(ids=ids,fields=facet_fields).items()) if facet_fields else {}
        return dict(count=len(ids),rows=rows,cursor=next_cursor,facets=facets(values,ids,facet_fields))
    def close(self):self.native.close()
def load_truth():
    con=sqlite3.connect(f'file:{SOURCE}?mode=ro&immutable=1',uri=True)
    ids=[];rows={};ordinals={}
    for number,identity,raw in con.execute('SELECT epoch_id,epoch_uuid,row_json FROM epochs ORDER BY epoch_id'):
        ids.append(identity);rows[identity]=json.loads(raw);ordinals[identity]=number
    values={identity:{} for identity in ids}
    query='SELECT e.epoch_uuid,f.field_id,v.value_json FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) ORDER BY e.epoch_id,f.field_no'
    for identity,field,raw in con.execute(query):values[identity][field]=json.loads(raw)
    fields=[field for field, in con.execute('SELECT field_id FROM fields ORDER BY field_no')]
    sources=[source for source, in con.execute('SELECT source_sha FROM sources ORDER BY source_sha')]
    ids.sort(key=lambda identity:(rows[identity]['date'],rows[identity]['start_time'],identity))
    ordinals={identity:rank for rank,identity in enumerate(ids,1)}
    con.close();return ids,rows,ordinals,values,fields,sources
def select_scenarios(ids,values,fields):
    byfield={field:collections.Counter() for field in fields};examples={}
    for current in values.values():
        for field,value in current.items():
            key=predicates.equality_key(value);byfield[field][key]+=1;examples[(field,key)]=value
    selected={}
    for kind in ('number','string','array','null','boolean'):
        candidates=[(abs(count-len(ids)/2),field,key,count) for field,buckets in byfield.items()
            for key,count in buckets.items() if key[0]==kind and field.startswith(('metadata/','parameters/','properties/'))]
        if candidates:
            _,field,key,count=min(candidates,key=lambda item:(item[0],item[1],repr(item[2])))
            selected[kind]=(field,examples[(field,key)])
    missing=min((field for field in fields if 0<sum(byfield[field].values())<len(ids)),key=lambda field:abs(sum(byfield[field].values())-len(ids)/2))
    base=[dict(label='global',predicate=None,scope=None)]
    for field in ('protocol','cell','block'):
        key,count=byfield[field].most_common(1)[0]
        base.append(dict(label='largest_'+field,predicate=None,scope={field:examples[(field,key)]}))
    for kind,(field,value) in selected.items():
        base.append(dict(label=kind+'_eq',predicate={'field':field,'operator':'eq','value':value},scope=None))
        if kind=='number':base.append(dict(label='numeric_order',predicate={'field':field,'operator':'gte','value':value},scope=None))
        if kind=='string' and value:base.append(dict(label='text_contains',predicate={'field':field,'operator':'contains','value':value[:min(5,len(value))]},scope=None))
        if kind=='array' and value:base.append(dict(label='array_contains',predicate={'field':field,'operator':'contains','value':value[0]},scope=None))
    base.extend([dict(label='missing',predicate={'field':missing,'operator':'missing'},scope=None),dict(label='exists',predicate={'field':missing,'operator':'exists'},scope=None)])
    if 'null' in selected:base.append(dict(label='recorded_null',predicate={'field':selected['null'][0],'operator':'is_null'},scope=None))
    pair=[case['predicate'] for case in base if case['label'] in ('number_eq','string_eq')]
    if len(pair)==2:
        base.extend([dict(label='compound_all',predicate={'all':pair},scope=None),dict(label='compound_any',predicate={'any':pair},scope=None),dict(label='compound_not',predicate={'not':{'any':pair}},scope=None)])
    for field,buckets in byfield.items():
        types={key[0] for key in buckets}
        if len(types)>1:
            key=next(key for key in buckets if key[0]!='null')
            base.append(dict(label='mixed_types',predicate={'field':field,'operator':'eq','value':examples[(field,key)]},scope=None));break
    base.append(dict(label='empty_result',predicate={'field':'epoch','operator':'eq','value':'not-a-recorded-epoch'},scope=None))
    return base,dict(observed_selected=selected,missing_field=missing,mixed_type_fields=[field for field,buckets in byfield.items() if len({key[0] for key in buckets})>1])
def truth_membership(case,ids,values):
    scope=case.get('scope');predicate=case.get('predicate')
    return [identity for identity in ids if (scope is None or (identity in scope if isinstance(scope,list) else all(field in values[identity] and predicates.equal(values[identity][field],value) for field,value in scope.items()))) and (predicate is None or predicates.matches(predicate,values[identity]))]
def truth_preview(case,ids,rows,ordinals,values,facet_fields,limit=60,cursor=None):
    matched=truth_membership(case,ids,values)
    eligible=[identity for identity in matched if ordinals[identity]>(cursor or 0)]
    return dict(count=len(matched),rows=[rows[identity] for identity in eligible[:limit]],
        cursor=ordinals[eligible[limit-1]] if len(eligible)>limit else None,facets=facets(values,matched,facet_fields))
def timed(call,repeats):
    times=[];expected=None
    for _ in range(repeats):
        begin=time.perf_counter();result=call();raw=canonical(result);times.append((time.perf_counter()-begin)*1000)
        checksum=hashlib.sha256(raw).hexdigest()
        if expected is None:expected=checksum
        assert checksum==expected,'Repeated output changed'
    return dict(samples_ms=times,first_ms=times[0],warm_median_ms=statistics.median(times[1:]),max_ms=max(times),sha256=expected,bytes=len(raw))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--repeats',type=int,default=11);parser.add_argument('--out',type=Path,default=ROOT/'evals');args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120 second process cap')));signal.alarm(120)
    cap=513*1024*1024
    def memory_watch():
        while True:
            if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>cap:os._exit(91)
            time.sleep(.2)
    threading.Thread(target=memory_watch,daemon=True).start()
    before=protected_inputs();ids,rows,ordinals,values,fields,sources=load_truth();scenarios,selection=select_scenarios(ids,values,fields)
    # Explicit pre-existing eligibility scopes avoid claiming observed live MySQL state.
    scenarios.append(dict(label='explicit_all_registered_eligible',predicate=None,scope=ids))
    summary=dict(epochs=len(ids),fields=len(fields),sources=len(sources),membership_sha256=digest(ids),
        full_indexed_values_sha256=digest(values),selection=selection,scenarios=scenarios,
        caps=dict(process_seconds=120,peak_rss_bytes=cap),input_before=before)
    if not args.run:
        (args.out/'prepared.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(dict(prepared=True,epochs=len(ids),scenarios=len(scenarios),selected=selection),default=str));return
    from typed_real import TypedReal
    native=NativePreview(open_native(),ordinals);candidate=TypedReal(ROOT/'model'/'real-typed.sqlite')
    result=[];started=time.perf_counter()
    try:
        for case in scenarios:
            facet_fields=['protocol','cell']
            if case.get('predicate') and 'field' in case['predicate']:
                facet_fields=[case['predicate']['field'],'epoch' if case['predicate']['field']!='epoch' else 'protocol']
            kwargs=dict(predicate=case['predicate'],scope=case['scope'],facet_fields=facet_fields)
            expected_ids=truth_membership(case,ids,values)
            assert native.membership(case['predicate'],case['scope'])==expected_ids,case['label']+' native membership'
            assert candidate.membership(case['predicate'],case['scope'])==expected_ids,case['label']+' candidate membership'
            expected=truth_preview(case,ids,rows,ordinals,values,facet_fields)
            assert canonical(native.preview(**kwargs))==canonical(expected),case['label']+' native preview'
            assert canonical(candidate.preview(**kwargs))==canonical(expected),case['label']+' candidate preview'
            entry=dict(label=case['label'],predicate=case['predicate'],scope=case['scope'] if not isinstance(case['scope'],list) else {'explicit_eligible_ids':len(case['scope']),'sha256':digest(case['scope'])},count=len(expected_ids),membership_sha256=digest(expected_ids),facet_fields=facet_fields,expected_payload_sha256=digest(expected),facets_sha256=digest(expected['facets']))
            entry['production_bounded_preview']=timed(lambda:native.preview(**kwargs),args.repeats)
            entry['typed_sqlite_bounded_preview']=timed(lambda:candidate.preview(**kwargs),args.repeats)
            assert entry['production_bounded_preview']['sha256']==entry['typed_sqlite_bounded_preview']['sha256']
            if expected['cursor']:
                next_expected=truth_preview(case,ids,rows,ordinals,values,facet_fields,cursor=expected['cursor'])
                for arm in (native,candidate):assert canonical(arm.preview(**kwargs,cursor=expected['cursor']))==canonical(next_expected),case['label']+' next page'
                entry['next_page_sha256']=digest(next_expected)
                if case['label'] in ('global','largest_block'):
                    entry['production_next_page']=timed(lambda:native.preview(**kwargs,cursor=expected['cursor']),args.repeats)
                    entry['typed_sqlite_next_page']=timed(lambda:candidate.preview(**kwargs,cursor=expected['cursor']),args.repeats)
                    assert entry['production_next_page']['sha256']==entry['typed_sqlite_next_page']['sha256']
            result.append(entry)
            print(json.dumps(dict(event='scenario_done',label=case['label'],count=len(expected_ids),native_ms=entry['production_bounded_preview']['warm_median_ms'],typed_ms=entry['typed_sqlite_bounded_preview']['warm_median_ms'])),flush=True)
        # Full order across keyset boundaries with and without a large scope.
        page_receipts=[]
        for label,scope in [('global',None),('largest_block',max(collections.defaultdict(list, {key:[identity for identity in ids if values[identity].get('block')==key] for key in {values[identity].get('block') for identity in ids}}).values(),key=len))]:
            case=dict(predicate=None,scope=scope);expected_ids=truth_membership(case,ids,values);seen=[];cursor=None;pages=0
            while True:
                page=candidate.preview(scope=scope,facet_fields=(),limit=60,cursor=cursor)
                expected=truth_preview(case,ids,rows,ordinals,values,(),cursor=cursor)
                assert canonical(page)==canonical(expected),'full page order '+label
                seen.extend(row['epoch_uuid'] for row in page['rows']);pages+=1;cursor=page['cursor']
                if cursor is None:break
            assert seen==expected_ids
            page_receipts.append(dict(label=label,count=len(seen),pages=pages,ordered_ids_sha256=digest(seen)))
        after=protected_inputs();assert before==after,'Protected input changed'
        summary.update(results=result,page_walks=page_receipts,all_oracles_passed=True,input_after=after,input_unchanged=True,seconds=time.perf_counter()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            limitations=['Metadata-only backend + JSON bounded count/60 row/two requested facet payload; not full app preview latency.', 'Native chronology is date,start_time,epoch_uuid as production WorkspaceService._filter_rows. Baseline preloaded rows global rank costs excluded, matching warm service state.', 'No live MySQL source policy was read; all registered metadata and explicit full2781 eligible-ID universe tested.', 'Real 2781 epochs do not establish performance at one million.', 'Existing all-field catalog measured separately; no equivalence claim between two requested facets and full 140-field catalog.', 'First reported sample follows correctness preparation; warm timings, not cold application startup.'])
        (args.out/'receipt.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(dict(event='finished',seconds=summary['seconds'],peak_rss_bytes=summary['peak_rss_bytes'])),flush=True)
    finally:
        native.close()
        if hasattr(candidate,'close'):candidate.close()
if __name__=='__main__':main()
