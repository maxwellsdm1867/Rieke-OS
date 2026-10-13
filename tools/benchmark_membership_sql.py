#!/usr/bin/env python3
"""Fixed-member SQL queries against actual 20k/200k/1m in-memory relations.

Reuses the everyday fixture schema/indexes; native seal admission is a double.
No HTTP, browser, project startup, disk-index build or installed-app qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run(source, epochs):
    sys.path[:0] = [str(source/'python'), str(ROOT/'benchmarks/everyday')]
    import fixture
    from benchmark_everyday import source as identity, environment
    from disco.navigation import predicates
    import h5py
    fixture.N = epochs
    original = fixture.row
    # Keep all metadata for the first 2,000 members identical across sizes.
    def stable_row(i):
        return {**original(i), 'cell_uuid':fixture.uid(1_000_000+i//100),
                'block_uuid':fixture.uid(2_000_000+i//20), 'group_uuid':fixture.uid(3_000_000)}
    fixture.row = stable_row
    receipt = {'status':'incomplete', 'epochs':epochs, 'members':2000,
        'source_start':identity(source), 'environment':environment(),
        'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()+(ROOT/'benchmarks/everyday/fixture.py').read_bytes()).hexdigest(),
        'operations':{}, 'limitations':['Actual in-memory SQLite relations with production query methods; native admission is replaced.',
            'Fixture/index construction excluded from query timings. No HTTP/UI/native qualification.']}
    reader = None
    try:
        with patch.object(h5py, 'File', side_effect=AssertionError('Metadata query touched H5')):
            reader = fixture.typed_fixture(lambda event, **values:print(json.dumps({'event':event, **values}), flush=True))
            ids = [fixture.uid(i) for i in range(2000)]
            scope = {'sources':[fixture.SOURCE_SHA], 'epoch_ids':ids}
            equal = {'field':'parameters/category','operator':'eq','value':5}
            contains = {'field':'parameters/unique','operator':'contains','value':'000000001'}
            expected_contains = [fixture.uid(i) for i in range(2000) if '000000001' in f'unique-{i:012d}']
            def page_check(answer, wanted):
                assert [row['epoch_uuid'] for row in answer['rows']] == wanted
            def measure(name, fn, oracle):
                samples=[]
                for _ in range(5):
                    start=time.perf_counter();answer=fn();samples.append((time.perf_counter()-start)*1000)
                    oracle(answer)
                receipt['operations'][name]={'milliseconds':samples,'median_ms':statistics.median(samples),'correct':True}
            measure('sql.member_source_page',lambda:reader.page(scope=scope),lambda a:page_check(a,ids[:60]))
            measure('sql.member_source_deep',lambda:reader.page(scope=scope,cursor=1900),lambda a:page_check(a,ids[1900:1960]))
            measure('sql.member_equality',lambda:reader.page(equal,scope),lambda a:page_check(a,[fixture.uid(i) for i in range(5,600,10)]))
            measure('sql.member_contains',lambda:reader.page(contains,scope),lambda a:page_check(a,expected_contains[:60]))
            def facet_check(answer):
                assert answer['count']==2000
                facet=answer['facets']['parameters/category']
                assert facet['present_count']==2000 and facet['missing_count']==0
                assert facet['values']==[{'value':i,'type':'number','count':200} for i in range(10)]
            measure('sql.member_facets',lambda:reader.summaries(scope=scope,facet_fields=['parameters/category']),facet_check)
            assert reader.membership(equal,{'sources':[], 'epoch_ids':ids})==[]
            assert reader.membership(contains,{'sources':[fixture.SOURCE_SHA], 'epoch_ids':[]})==[]
            # Work counts are a separate diagnostic pass, not latency samples.
            work={'sqlite_vm_steps_approx':0,'dictionary_values_evaluated':0,'statements':0}
            def progress():
                work['sqlite_vm_steps_approx']+=1000
                return 0
            def trace(sql):work['statements']+=1
            match=predicates.matches
            def observe(node,values):
                work['dictionary_values_evaluated']+=1
                return match(node,values)
            reader.connection.set_progress_handler(progress,1000)
            reader.connection.set_trace_callback(trace)
            with patch.object(predicates,'matches',side_effect=observe):
                page_check(reader.page(contains,scope),expected_contains[:60])
            reader.connection.set_trace_callback(None)
            reader.connection.set_progress_handler(lambda:int(reader._cancel_requested()),10000)
            receipt['contains_work']=work
            receipt['equality_plan']=reader.explain(equal,scope)
            receipt['source_page_plan']=reader.explain(scope=scope)
            receipt['source_end']=identity(source)
            assert receipt['source_start']==receipt['source_end']
            receipt.update(status='passed',h5_open_attempts=0)
            return receipt
    finally:
        if reader is not None:reader.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--epochs',type=int,choices=(20000,200000,1000000),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output already exists')
    receipt=run(args.source_root.resolve(),args.epochs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'epochs':args.epochs,'contains_work':receipt['contains_work'],
                      'medians':{key:value['median_ms'] for key,value in receipt['operations'].items()}}))
