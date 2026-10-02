"""Same-output full-140 scope optimization and separate requested-summary work."""
import hashlib,json,resource,statistics,time
from pathlib import Path
import compare as harness
from scoped_full import FullScopedSidecar
from typed_bounded import TypedBoundedSidecar
from priority_sidecar import PrioritySidecar
ROOT=harness.ROOT; PRE=harness.PRE
def timing(arm,case):
    begin=time.perf_counter()
    value=arm.preview(case['predicate'],case['scope'],facet_fields=case['facets'])
    raw=harness.canonical(value)
    return (time.perf_counter()-begin)*1000,value,hashlib.sha256(raw).hexdigest()
def main():
    started=time.monotonic()
    paths=[PRE/'base.sqlite',PRE/'typed'/'sidecar.sqlite']
    stat=lambda: {str(p):[p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns] for p in paths}
    output=ROOT/'evals'/'scoped-comparison.json'
    result=json.loads(output.read_text()) if output.exists() else {'status':'running','source_stats':stat(),'results':[]}
    save=lambda:harness.save(output,result)
    save()
    full=TypedBoundedSidecar(paths[1]); scoped=FullScopedSidecar(paths[1])
    labels={'NDF_filter','light_path_filter','cold_canvas_query','cold_trial_count_query','cold_rig_query','cell_page_two_facets','saved_history_filter'}
    plan=json.loads((ROOT/'evals'/'plan.json').read_text())
    old={c['label']:c for c in json.loads((ROOT/'evals'/'comparison.json').read_text())['results']}
    try:
        for case in plan['cases']:
            if case['label'] not in labels:continue
            if case['label'] in {r['label'] for r in result['results']}:continue
            entry={'label':case['label'],'count':case['count'],'arms':{}}
            for i in range(5):
                order=[('full',full),('scoped',scoped)]
                if i%2:order.reverse()
                for name,arm in order:
                    ms,value,sha=timing(arm,case)
                    assert value['count']==case['count']
                    assert sha==old[case['label']]['arms']['full']['sha256']
                    entry['arms'].setdefault(name,{'samples_ms':[],'sha256':sha})['samples_ms'].append(ms)
            for arm in entry['arms'].values():arm['warm_median_ms']=statistics.median(arm['samples_ms'][1:])
            entry['same_payload']=True;result['results'].append(entry);save()
            print(json.dumps(entry),flush=True)
        cell=next(c for c in plan['cases'] if c['label']=='cell_page_two_facets')
        fields=list(scoped.fields)
        preferred=['parameters/currentSpotSize','properties/bathTemperature','parameters/NDF','parameters/lightPath']
        work={'scope':cell['scope'],'count':cell['count'],'arms':{},'different_requested_work':True}
        values={}
        for name,facets in [('all140',fields),('selected4',preferred),('rows_only',[])]:
            samples=[]
            for i in range(5):
                ms,value,sha=timing(scoped,dict(predicate=None,scope=cell['scope'],facets=facets))
                samples.append(ms);values[name]=value
            work['arms'][name]={'facet_count':len(facets),'samples_ms':samples,'warm_median_ms':statistics.median(samples[1:]),'sha256':sha}
        result['requested_summaries']=work
        result['summary_payload_keys']={k:list(v) for k,v in values.items()}
        for name,v in values.items():
            assert v['count']==cell['count']
            for key in ('rows','cursor'):
                if key in v:assert v[key]==values['all140'][key]
            if name=='selected4':
                for field in preferred:assert v['facets'][field]==values['all140']['facets'][field]
        work['same_count_rows_cursor']=True
        work['selected_facets_equal_full']=True
        result.pop('wall_seconds',None);result.pop('peak_rss_bytes',None)
        result.update(status='complete',source_stats_after=stat(),completion_phase_wall_seconds=time.monotonic()-started,completion_phase_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            paired_timed_samples_seconds=sum(sum(arm['samples_ms']) for r in result['results'] for arm in r['arms'].values())/1000)
        result['source_stats_unchanged']=result['source_stats']==result['source_stats_after'];save()
        print(json.dumps(work),flush=True)
    finally:full.close();scoped.close()
if __name__=='__main__':main()
