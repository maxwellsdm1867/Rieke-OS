"""Disposable current disk-index service probe; no SQL, lab files, or mutations.

Run with PYTHONPATH=python .rieke-runtime/venv/bin/python <this file>
  --epochs 10000 --output <json path>
Timings cover service CPU/I/O only, excluding HTTP hooks and browser rendering.
"""
from __future__ import annotations
import argparse
from collections.abc import Mapping
import cProfile
import datetime as dt
import gc
import hashlib
import json
from pathlib import Path
import pstats
import platform
import statistics
import tempfile
import time
import uuid
import psutil
from workspace_disk_index import DiskMetadataIndex
from workspace_service import WorkspaceService
from workspace_tree_pages import TreePages


def uid(number):
    # Deterministic pseudorandom UUIDs avoid unrealistically cheap wire compression.
    return str(uuid.UUID(bytes=hashlib.sha256(str(number).encode()).digest()[:16]))


class Details(Mapping):
    def __init__(self, rows): self.rows = rows
    def __len__(self): return len(self.rows)
    def __iter__(self): return iter(self.rows)
    def __getitem__(self, key):
        row = self.rows[key]; i = row['synthetic_index']
        return {'parameters': {'contrast': (i % 5) / 10, 'seed': i,
            'stimTime': 1000, 'currentMean': (i % 3) * 100}, 'properties': {},
            'attributes': {}, 'metadata': {'cell': {'uuid': row['cell_uuid'],
                'label': row['cell_label'], 'properties': {'type': row['cell_type']}},
                'block': {'uuid': row['block_uuid'], 'parameters': {'amp': 'Amp1'}}}}


def fixture(count):
    service = WorkspaceService.__new__(WorkspaceService)
    service._loaded = True; service.curation_provider = None
    service.project = {'project_uuid': uid(-1), 'name': 'Disposable scale probe'}
    service.config = {'database': 'no-sql'}
    service.sources = [{'source_sha256': f'{i+1:064x}', 'filename': f'synthetic-{i}.h5'} for i in range(10)]
    service.rows = {}; service.cells = {}
    base = dt.datetime(2026, 9, 1, 12)
    for i in range(count):
        identity = uid(i); cell = uid(count+i//100); block = uid(2*count+i//20)
        started = (base + dt.timedelta(seconds=i)).strftime('%m/%d/%Y %H:%M:%S:%f')
        row = {'epoch_uuid': identity, 'cell_uuid': cell, 'cell_label': f'Cell{i//100}',
            'cell_type': ['ON', 'OFF'][(i//100)%2], 'date': '2026-09-01', 'start_time': started,
            'group_uuid': uid(3*count), 'group_label': 'Control', 'block_uuid': block,
            'block_start_time': started, 'protocol_name': 'Synthetic', 'duration_seconds': 1.,
            'epoch_number': i%20+1, 'streams': [], 'source_sha256': service.sources[(i//100)%10]['source_sha256'],
            'metadata_hash': 'b'*64, 'synthetic_index': i}
        service.rows[identity] = row
        service.cells[cell] = {'cell_uuid': cell, 'label': row['cell_label'], 'cell_type': row['cell_type'], 'date': row['date']}
    protocol = uid(-2)
    service.protocols = {protocol: {'definition': {'protocol_uuid': protocol, 'name': 'All epochs', 'query': {'version':1, 'all':[]}},
        'result': {'protocol_uuid': protocol, 'protocol_name': 'Synthetic',
            'epochs': [{'uuid': key, 'metadata_hash': 'b'*64} for key in service.rows],
            'cells': [{'uuid': key} for key in service.cells], 'source_revisions': [s['source_sha256'] for s in service.sources]}}}
    service._fingerprints = {key:'b'*64 for key in service.rows}
    service.events = lambda limit=25: []
    return service, protocol


def run(count, repeats):
    process = psutil.Process()
    rss = lambda: round(process.memory_info().rss/1024**2, 2)
    report = {'epochs':count, 'sources':10, 'protocol_members':count, 'synthetic':True,
        'python':platform.python_version(), 'platform':platform.platform(),
        'limits':'No SQL, API snapshot hooks, HTTP, tags, waveform data, or browser; 4 scalar parameters per epoch.',
        'rss_initial_mib':rss(), 'operations':[]}
    service, protocol = fixture(count)
    with tempfile.TemporaryDirectory(prefix='rieke-service-scale-') as directory:
        started = time.perf_counter()
        index = DiskMetadataIndex.build(Path(directory)/'index.sqlite', service.rows, Details(service.rows), service.sources, 'synthetic-generation', service.project['project_uuid'])
        report.update(build_seconds=time.perf_counter()-started, index_bytes=index.path.stat().st_size,
            fields=len(index.catalog()['fields']), rss_model_index_mib=rss())
        service.disk_index = index; service.details = index.details
        pager = TreePages(service)
        predicate = {'field':'parameters/contrast','operator':'eq','value':.3}
        operations = [
            ('epoch_page_60', lambda:service.epoch_page(protocol, limit=60)),
            ('epoch_page_60_filter_one_cell', lambda:service.epoch_page(protocol, {'cell_uuid':next(iter(service.cells))}, limit=60)),
            ('tree_root_page_80', lambda:pager.page({'splits':'cell,block','limit':80})),
            ('flat_tree_page_80', lambda:pager.page({'splits':'','limit':80})),
            ('select_one_epoch_predicate', lambda:service.match_predicate({'field':'epoch','operator':'eq','value':next(iter(service.rows))})),
            ('filter_preview_summary', lambda:service.explore_preview(predicate, 'cell,block', include_tree=False)),
            ('filter_preview_fast_summary', lambda:service.explore_preview(predicate, 'cell,block', include_tree=False, include_catalog_summary=False)),
            ('overview', service.overview)]
        for name, operation in operations:
            samples = []; cpu_samples = []
            for _ in range(repeats):
                gc.collect(); cpu = time.process_time(); started = time.perf_counter()
                result = operation()
                samples.append(time.perf_counter()-started); cpu_samples.append(time.process_time()-cpu)
            started = time.perf_counter(); encoded = json.dumps(result, separators=(',',':')).encode()
            serialization = time.perf_counter()-started
            record = {'name':name,'wall_seconds_samples':samples, 'median_seconds':statistics.median(samples),
                'median_cpu_seconds':statistics.median(cpu_samples), 'json_bytes':len(encoded),
                'serialization_seconds':serialization,'rss_mib':rss()}
            if isinstance(result,dict):
                for key in ('total','matched_count','count'):
                    if key in result: record[key]=result[key]
            if name in ('tree_root_page_80','filter_preview_summary','select_one_epoch_predicate'):
                profile=cProfile.Profile();profile.enable();operation();profile.disable()
                stats=pstats.Stats(profile)
                record['profile_top_cumulative']=[{'file':Path(key[0]).name,'line':key[1],
                    'function':key[2],'primitive_calls':value[0],'calls':value[1],
                    'self_seconds':value[2],'cumulative_seconds':value[3]}
                    for key,value in sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True)[:18]]
            report['operations'].append(record)
            print(json.dumps({'epochs':count,**record},default=str),flush=True)
            del result, encoded
        report['rss_after_operations_mib']=rss()
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.epochs,args.repeats)
    args.output.write_text(json.dumps(result,indent=2))
