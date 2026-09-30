"""Disposable current disk-index probe; run with PYTHONPATH=python.

No scientific data, MySQL connection, acquisition H5, or production cache is read.
Synthetic metadata comes from a lazy Mapping to avoid allocating all details.
"""
import argparse
from collections.abc import Mapping
import cProfile
import gc
import io
import json
from pathlib import Path
import platform
import pstats
import resource
import statistics
import tempfile
import time
from workspace_disk_index import DiskMetadataIndex


def run(count, parameter_fields, source_count, profile=False):
    rows = [dict(epoch_uuid=f'e-{i}',cell_uuid=f'c-{i//100}',cell_label=f'Cell {i//100}',
        date='2026-09-29',start_time=f'09/29/2026 12:00:{i%60:02d}:000000',cell_type='ON',
        block_uuid=f'b-{i//20}',block_start_time=f'09/29/2026 12:00:{i%60:02d}:000000',
        protocol_name='Synthetic',source_sha256=f's-{(i//100)%source_count}',group_uuid='g',
        group_label='g',duration_seconds=1.,epoch_number=i%20+1) for i in range(count)]
    sources = [{'source_sha256':f's-{i}'} for i in range(source_count)]
    class Details(Mapping):
        def __getitem__(self,key):
            i=int(key[2:])
            return {'parameters':{f'axis{k}':(i//(k+1))%7 for k in range(parameter_fields)},
                'metadata':{'cell':{'start_time':'09/29/2026 12:00:00:000000'}}}
        def __len__(self): return count
        def __iter__(self): return (r['epoch_uuid'] for r in rows)
    result={'epochs':count,'parameter_fields':parameter_fields,'sources':source_count,
        'python':platform.python_version(),'fixture':'synthetic lazy details; no H5/SQL/browser IO',
        'measurements':[]}
    def measure(name,fn,repeats=1):
        timings=[];value=None
        for _ in range(repeats):
            started=time.perf_counter();value=fn();timings.append(time.perf_counter()-started)
        item=dict(operation=name,seconds=timings,median_seconds=statistics.median(timings))
        result['measurements'].append(item)
        return value
    with tempfile.TemporaryDirectory(prefix='rieke-audit-index-') as folder:
        path=Path(folder)/'metadata.sqlite'
        index=measure('build',lambda:DiskMetadataIndex.build(path,rows,Details(),sources,'audit','project'))
        result['fields']=len(index.catalog()['fields']);result['db_bytes']=path.stat().st_size
        index=measure('open_verified',lambda:DiskMetadataIndex.open(path,'audit','project'),3)
        measure('cached_catalog',index.catalog,3)
        ids=[row['epoch_uuid'] for row in rows if int(row['epoch_uuid'][2:])%7==3]
        measure('scoped_catalog_one_seventh',lambda:index.catalog(ids),3)
        measure('low_cardinality_predicate',lambda:index.match({'field':'parameters/axis0','operator':'eq','value':3}),3)
        measure('epoch_uuid_equality',lambda:index.match({'field':'epoch','operator':'eq','value':f'e-{count//2}'}),3)
        measure('all_source_projections_lazy',lambda:[index.source_projection(s['source_sha256'],lazy_details=True) for s in sources],3)
        result['detail_cache_entries']=len(index.details.cache)
        if profile:
            profiler=cProfile.Profile();profiler.enable();index.catalog(ids);profiler.disable()
            output=io.StringIO();pstats.Stats(profiler,stream=output).strip_dirs().sort_stats('cumtime').print_stats(30)
            result['scoped_catalog_profile']=output.getvalue()
            profiler=cProfile.Profile();profiler.enable();index.match({'field':'epoch','operator':'eq','value':f'e-{count//2}'});profiler.disable()
            output=io.StringIO();pstats.Stats(profiler,stream=output).strip_dirs().sort_stats('cumtime').print_stats(25)
            result['epoch_equality_profile']=output.getvalue()
        # Do not retain the list of all-source projections across cleanup.
        del index
        gc.collect()
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result['peak_rss_mib']=rss/(1024**2 if platform.system()=='Darwin' else 1024)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--epochs',type=int,required=True)
    parser.add_argument('--fields',type=int,required=True);parser.add_argument('--sources',type=int,required=True)
    parser.add_argument('--profile',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.epochs,args.fields,args.sources,args.profile)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if not key.endswith('_profile')},indent=2))
