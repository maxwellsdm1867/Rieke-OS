"""Disposable synthetic metadata-only scale probe; no database or waveform I/O.

This isolates service computation, serialization and process memory. It does
not predict SQL latency, cold H5 verification cost, browser render time, or the
size of a particular lab dataset. Synthetic rows have real-shaped hierarchy,
UUIDs, typed parameters and lazy response pointers; no waveform arrays exist.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import gc
import gzip
import json
from pathlib import Path
import resource
import sys
import time
import uuid

from workspace_service import WorkspaceService, TREE_CACHE_VALUE_BUDGET, TREE_CACHE_MAX_SCOPES


def identity(value):
    return str(uuid.UUID(int=value))


def rss_mib():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024**2
    except ImportError:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / (1024**2 if sys.platform == 'darwin' else 1024)


def synthetic_service(count, extra_fields=0):
    service = WorkspaceService.__new__(WorkspaceService)
    service._loaded, service.curation_provider = True, None
    service.project = {'project_uuid': identity(1), 'name': 'Synthetic scale fixture'}
    service.config = {'database': 'synthetic-no-sql'}
    service.rows, service.details, service.cells, service._fingerprints = {}, {}, {}, {}
    service.sources = [{'source_sha256': f'{i+1:064x}', 'filename': f'synthetic-{i+1}.h5',
                        'source_path': f'/synthetic-not-a-real-file/{i+1}.h5'} for i in range(10)]
    names = ['VariableHistoryNoiseCurInject', 'VariableMeanNoiseCurInject', 'ExpandingSpots', 'SplitFieldCentering', 'SingleSpot']
    service.protocols = {}
    for index, name in enumerate(names):
        key = identity(100+index)
        query = {'version': 1, 'all': [{'field': 'EpochBlock.protocol_name','operator': 'eq','value': name}]}
        service.protocols[key] = {'definition': {'protocol_uuid': key, 'name': name, 'query': query},
            'result': {'protocol_uuid': key, 'protocol_name': name, 'epochs': [], 'cells': [],
                       'source_revisions': [s['source_sha256'] for s in service.sources]}}
    parents, source_bins = {}, [[] for _ in service.sources]
    extra_keys = [f'syntheticField{index:03d}' for index in range(extra_fields)]
    for i in range(count):
        cell_index, block_index = i//250, i//10
        cell_id, block_id, group_id = identity(1000+cell_index), identity(100000+block_index), identity(10000+cell_index*3+(i//100)%3)
        source_index = cell_index % 10
        source = service.sources[source_index]
        epoch_id = identity(1000000+i)
        protocol_id = identity(100+block_index%5)
        protocol_name = names[block_index%5]
        timestamp = dt.datetime(2026,9,1+source_index,12) + dt.timedelta(seconds=(i%250)*2)
        started = timestamp.strftime('%m/%d/%Y %H:%M:%S:%f')
        date = timestamp.date().isoformat()
        label, cell_type = f'Cell{cell_index+1}', ['ON parasol','OFF parasol','ON midget','OFF midget'][cell_index%4]
        params = {'frequencyCutoff': [25.,100.,200.,400.][i%4], 'currentMean': float((i%3)*100),
            'currentSD': float((i%4)*150), 'history1': [float((i%4)*100), float((i%3)*200)],
            'history2': [0.,0.], 'target': [0.,float(100+(i%3)*100)], 'isControl': i%11==0,
            'seed': i*9187+17, 'preTime':250.,'stimTime':1000.,'tailTime':250., 'sampleRate':10000.,
            'amp':'Amp1','currentSpotSize':float(40+(i%13)*40), 'contrast':[-1.,1.][i%2],
            'centerOffset':[float(i%5),float(i%7)], 'backgroundIntensity':.25, 'segmentTime':1000.}
        params.update({key: float((i+index)%7) for index,key in enumerate(extra_keys)})
        properties = {'bathTemperature':30.+(i%20)*.1} if i%7 else {}
        streams = [{'uuid':identity(2000000+i*2+j),'device':'Amp1' if j==0 else 'Frame Monitor',
            'kind':'responses','sample_rate':10000.,'sample_rate_units':'Hz','sample_count':15000,
            'units':'mV' if j==0 else 'V','h5_path':f'/synthetic/epochs/{epoch_id}/responses/{j}',
            'data_path':f'/synthetic/epochs/{epoch_id}/responses/{j}/data'} for j in range(2)]
        row = {'epoch_uuid':epoch_id,'cell_uuid':cell_id,'cell_label':label,'cell_type':cell_type,
            'date':date,'start_time':started,'group_uuid':group_id,'group_label':['Control','Drug recorded','Wash'][(i//100)%3],
            'block_uuid':block_id,'block_start_time':started,'protocol_name':protocol_name,
            'duration_seconds':1.5,'streams':streams,'source_sha256':source['source_sha256'],
            'metadata_hash':'b'*64,'epoch_number':i%10+1}
        service.rows[epoch_id] = row
        cell = parents.setdefault(cell_id,{'uuid':cell_id,'label':label,'type':cell_type,'start_time':started,'properties':{'type':cell_type},'attributes':{}})
        group = parents.setdefault(group_id,{'uuid':group_id,'label':row['group_label'],'properties':{'seriesResistanceCompensation':0},'attributes':{}})
        block = parents.setdefault(block_id,{'uuid':block_id,'protocolID':protocol_name,'start_time':started,'parameters':{'amp':'Amp1'},'properties':{},'attributes':{}})
        epoch = {'uuid':epoch_id,'start_time':started,'parameters':params,'properties':properties,
                 'attributes':{},'responses':{'Amp1':{'uuid':streams[0]['uuid'],'h5path':streams[0]['h5_path']}},'stimuli':{}}
        service.details[epoch_id] = {'parameters':params,'properties':properties,'attributes':{},
            'metadata':{'cell':dict(cell),'group':dict(group),'block':dict(block),'epoch':epoch}}
        service.cells[cell_id] = {'cell_uuid':cell_id,'label':label,'cell_type':cell_type,'date':date,'start_time':cell['start_time']}
        service._fingerprints[epoch_id] = 'b'*64
        service.protocols[protocol_id]['result']['epochs'].append({'uuid':epoch_id,'metadata_hash':'b'*64})
        source_bins[source_index].append(epoch_id)
    for entry in service.protocols.values():
        entry['result']['cells'] = [{'uuid':key} for key in sorted({service.rows[e['uuid']]['cell_uuid'] for e in entry['result']['epochs']})]
    service.events = lambda limit=25: []
    service.trace = lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('Synthetic benchmark must never read waveforms'))
    return service, source_bins


def benchmark(count, extra_fields=0):
    start = time.perf_counter()
    base_rss = rss_mib()
    service,bins = synthetic_service(count, extra_fields)
    constructed = time.perf_counter()-start
    model_rss = rss_mib()
    # Model the private per-source cache ownership introduced by refresh.
    service._source_metadata_cache = {}
    clone_start = time.perf_counter()
    for source,ids in zip(service.sources,bins):
        service._source_metadata_cache[source['source_sha256']] = copy.deepcopy({
            'rows':{key:service.rows[key] for key in ids}, 'details':{key:service.details[key] for key in ids},
            'fingerprints':{key:service._fingerprints[key] for key in ids}})
    clone_seconds = time.perf_counter()-clone_start
    cached_rss = rss_mib()
    measurements = []
    def measure(name, operation):
        gc.collect(); before = rss_mib(); started = time.perf_counter()
        result = operation(); seconds = time.perf_counter()-started; resident = rss_mib()
        serialized_at = time.perf_counter()
        encoded = json.dumps(result, separators=(',',':')).encode()
        size = len(encoded)
        serialization_seconds = time.perf_counter()-serialized_at
        compressed_at = time.perf_counter()
        compressed_size = len(gzip.compress(encoded, compresslevel=1))
        compression_seconds = time.perf_counter()-compressed_at
        measurements.append({'operation':name,'seconds':seconds,'json_serialization_seconds':serialization_seconds,'gzip_bytes':compressed_size,'compression_seconds':compression_seconds,
            'json_bytes':size,'rss_before_mib':before,'rss_with_result_mib':resident})
        del result
    protocol = identity(100)
    measure('overview',service.overview)
    measure('protocol_query',lambda:service.query_result(protocol))
    measure('epoch_page_100',lambda:service.epoch_page(protocol,limit=100))
    measure('project_tree_cold',lambda:service.tree(None,splits='date,cell,block'))
    measure('project_tree_warm',lambda:service.tree(None,splits='date,cell,block'))
    measure('predicate_fields_cold',service.predicate_fields)
    measure('predicate_fields_warm',service.predicate_fields)
    measure('filtered_preview_warm',lambda:service.explore_preview({'field':'parameters/frequencyCutoff','operator':'eq','value':100.},'cell,block'))
    return {'synthetic':True,'epochs':count,'cells':len(service.cells),'protocols':5,'sources':10,
        'no_waveform_or_sql_io':True,'field_count':len(service.tree_fields(None)['fields']),'construction_seconds':constructed,'private_cache_copy_seconds':clone_seconds,
        'memory_mib':{'initial':base_rss,'read_model':model_rss,'with_private_source_cache':cached_rss,
                      'after_queries':rss_mib()},'measurements':measurements,
        'scope_cache_limits':{'max_scopes':TREE_CACHE_MAX_SCOPES,'approximate_value_entries':TREE_CACHE_VALUE_BUDGET,
                              'single_current_oversized_scope_allowed':True},
        'remaining_limits':[
            'Registered discovery values retain O(epoch_count × field_count) memory; the source projection cache also keeps a separate private metadata copy.',
            'A full tree response still contains all matching epoch labels and UUIDs; gzip reduces wire size, not decoded browser memory.',
            'This fixture uses sequential synthetic UUIDs, which compress better than random acquisition UUIDs.',
            'These measurements do not cover SQL latency, cold H5 validation, concurrent clients or browser rendering.'],
        'limits':'Synthetic metadata-only process timings; excludes SQL/H5 verification, network and browser rendering.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,choices=(10000,50000),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--extra-fields',type=int,default=0,help='Additional synthetic numeric parameter fields (0–200)')
    args=parser.parse_args()
    if not 0 <= args.extra_fields <= 200:
        parser.error('--extra-fields must be 0–200')
    result=benchmark(args.epochs, args.extra_fields)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
