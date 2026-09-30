"""Read-only physical-source metadata oracle; all derived artifacts are disposable.

Reads already imported acquisition metadata and H5 owner identities. It tests
normalization, not parser correctness or waveform values. The duplicated-detail
comparison is a controlled representation clone of the current index schema,
not an executable historical product build.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import statistics
import tempfile
import threading
import time
import traceback
import uuid
import zlib

import h5py
from workspace_disk_index import DiskMetadataIndex
from workspace_projection_cache import ProjectionCache
from workspace_recipes import checksum
import workspace_metadata_objects as objects
import workspace_disk_index as disk_module
import workspace_projection_cache as projection_module


def raw(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def sha(path):
    value=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()
def signature(path):
    stat=Path(path).stat();return [stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]
def storage(path):
    files=[path] if path.is_file() else [item for item in path.rglob('*') if item.is_file() and not item.is_symlink()]
    return {'apparent_bytes':sum(item.stat().st_size for item in files),'allocated_bytes':sum(item.stat().st_blocks*512 for item in files),'files':len(files)}
def date(value):
    for pattern in ('%m/%d/%Y','%Y-%m-%d'):
        try:return dt.datetime.strptime(value[:10],pattern).date().isoformat()
        except ValueError:pass
    raise ValueError('Unsupported source date')
def identity(value):return str(uuid.UUID(value.decode() if isinstance(value,bytes) else str(value)))
def timed(callback,repeat=1):
    samples=[];value=None
    for _ in range(repeat):
        started=time.perf_counter();value=callback();samples.append(time.perf_counter()-started)
    return value,{'samples_seconds':samples,'median_seconds':statistics.median(samples),'maximum_seconds':max(samples)}
def count_shapes(value):
    if isinstance(value,list):return [len(value),[count_shapes(item) for item in value]]
    return type(value).__name__


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--block-uuid',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Choose an unused receipt')
    modules=(objects,disk_module,projection_module);hashes=lambda:{module.__name__:sha(module.__file__) for module in modules}
    report={'scope':__doc__,'source_hashes_before':hashes(),'probe_sha256':sha(__file__),'cases':[],'release_ready':False,
            'started_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    temporary=Path(tempfile.mkdtemp(prefix='rieke-real-metadata-oracle-')).resolve();index=None
    stopping=threading.Event();phase=['input_verification'];peaks={}
    def sample_storage():
        while not stopping.is_set():
            apparent=allocated=files=0
            for path in temporary.rglob('*'):
                try:
                    if path.is_file() and not path.is_symlink():
                        stat=path.stat();apparent+=stat.st_size;allocated+=stat.st_blocks*512;files+=1
                except FileNotFoundError:pass
            value=peaks.setdefault(phase[0],{'apparent_bytes':0,'allocated_bytes':0,'files':0,'samples':0})
            for field,current in [('apparent_bytes',apparent),('allocated_bytes',allocated),('files',files)]:value[field]=max(value[field],current)
            value['samples']+=1;stopping.wait(.02)
    monitor=threading.Thread(target=sample_storage,daemon=True);monitor.start()
    def check(name,passed,**detail):
        report['cases'].append({'name':name,'passed':bool(passed),**detail});print(json.dumps(report['cases'][-1]),flush=True)
        if not passed:raise AssertionError(name)
    try:
        manifest=json.loads(args.manifest.read_text());metadata_path=Path(manifest['metadata_path']);h5_path=Path(manifest['source_path'])
        inputs={str(path):signature(path) for path in (args.manifest,metadata_path,h5_path)}
        check('metadata_matches_imported_sha256',sha(metadata_path)==manifest['metadata_sha256'])
        source_sha,report['source_hash_verification']=timed(lambda:sha(h5_path))
        check('physical_recording_matches_imported_sha256',source_sha==manifest['source_sha256'])
        document=json.loads(metadata_path.read_text());selected=[]
        for animal in document['animals']:
            for preparation in animal['preparations']:
                for cell in preparation['cells']:
                    for group in cell['epoch_groups']:
                        for block in group['epoch_blocks']:
                            if block['uuid']==args.block_uuid:selected.append((cell,group,block))
        check('block_identity_is_unique_in_source',len(selected)==1)
        cell,group,block=selected[0];rows={};details={};fingerprints={};frames=block['properties']['frameTimesMs']
        expected_frames_sha=hashlib.sha256(raw(frames)).hexdigest();expected_shape_sha=hashlib.sha256(raw(count_shapes(frames))).hexdigest()
        with h5py.File(h5_path,'r') as h5:
            for epoch in block['epochs']:
                streams=[]
                for kind in ('responses','stimuli'):
                    for device,stream in epoch.get(kind,{}).items():
                        handle=h5[stream['h5path']];owner=handle.parent.parent;ancestor=owner.parent.parent
                        assert identity(handle.attrs['uuid'])==stream['uuid'] and identity(owner.attrs['uuid'])==epoch['uuid'] and identity(ancestor.attrs['uuid'])==block['uuid']
                        data=handle.get('data');units=None
                        if kind=='responses' and data is not None and len(data):
                            unit=data[0]['units'];units=unit.decode() if isinstance(unit,bytes) else str(unit)
                        streams.append({'uuid':stream['uuid'],'device':device,'kind':kind,'sample_rate':stream.get('sampleRate'),
                            'sample_rate_units':stream.get('sampleRateUnits'),'sample_count':len(data) if data is not None else None,
                            'units':units,'h5_path':stream['h5path'],'data_path':data.name if data is not None else None})
                duration=max([item['sample_count']/item['sample_rate'] for item in streams if item['kind']=='responses' and item['sample_rate'] and item['sample_count'] is not None],default=0)
                row={'epoch_uuid':epoch['uuid'],'cell_uuid':cell['uuid'],'cell_label':cell['label'],'cell_type':cell.get('type'),
                    'date':date(epoch['start_time']),'start_time':epoch['start_time'],'group_uuid':group['uuid'],'group_label':group.get('label'),
                    'block_uuid':block['uuid'],'block_start_time':block.get('start_time'),'block_end_time':block.get('end_time'),
                    'protocol_name':block['protocolID'],'duration_seconds':duration,'streams':streams,'source_sha256':source_sha,
                    'metadata_hash':hashlib.sha256(json.dumps(epoch,sort_keys=True).encode()).hexdigest()}
                detail={'parameters':epoch.get('parameters',{}),'properties':epoch.get('properties',{}),'attributes':epoch.get('attributes',{}),
                    'metadata':{'cell':{key:value for key,value in cell.items() if key!='epoch_groups'},
                                'group':{key:value for key,value in group.items() if key!='epoch_blocks'},
                                'block':{key:value for key,value in block.items() if key!='epochs'},'epoch':epoch}}
                rows[epoch['uuid']]=row;details[epoch['uuid']]=detail
                fingerprints[epoch['uuid']]=hashlib.sha256(json.dumps({'epoch':detail,'source_sha256':source_sha},sort_keys=True,allow_nan=False).encode()).hexdigest()
        check('physical_stream_parent_ownership_matches_every_selected_epoch',True,epochs=len(rows),streams=sum(len(row['streams']) for row in rows.values()))
        report['fixture']={'metadata_path':str(metadata_path),'source_path':str(h5_path),'source_sha256':source_sha,
            'source_bytes':h5_path.stat().st_size,'metadata_bytes':metadata_path.stat().st_size,'block_uuid':block['uuid'],'epochs':len(rows),
            'frame_times_outer_count':len(frames),'frame_times_json_bytes':len(json.dumps(frames).encode()),'frame_times_canonical_bytes':len(raw(frames)),
            'frame_times_sha256':expected_frames_sha,'frame_times_shape_sha256':expected_shape_sha}
        source={'source_sha256':source_sha,'filename':h5_path.name,'source_path':str(h5_path),'experiment_uuid':document['uuid'],
            'metadata':{key:value for key,value in document.items() if key!='animals'}}
        cells={cell['uuid']:{'cell_uuid':cell['uuid'],'label':cell['label'],'cell_type':cell.get('type'),'date':date(cell['start_time']),'start_time':cell['start_time']}}
        projection={'rows':rows,'details':details,'cells':cells,'source':source,'fingerprints':fingerprints}
        expected={key:hashlib.sha256(raw(value)).hexdigest() for key,value in details.items()}
        phase[0]='index_build'
        index,report['index_build']=timed(lambda:DiskMetadataIndex.build(temporary/'normalized'/'index.sqlite',rows,details,[source],'physical-source-normalization',manifest['project_uuid']))
        phase[0]='index_validation'
        check('index_row_ownership_and_fingerprints_exact',index.rows()==rows and index.fingerprints()==fingerprints)
        def verify_details(mapping):
            for key in rows:
                actual=mapping[key]
                assert hashlib.sha256(raw(actual)).hexdigest()==expected[key]
                array=actual['metadata']['block']['properties']['frameTimesMs']
                assert hashlib.sha256(raw(array)).hexdigest()==expected_frames_sha
                assert hashlib.sha256(raw(count_shapes(array))).hexdigest()==expected_shape_sha
            return True
        _,report['all_index_details_read']=timed(lambda:verify_details(index.details))
        check('all_index_details_arrays_shapes_and_types_exact',True,decoded_ancestors=index._metadata_decoder.object_decodes)
        check('one_block_decoded_once_across_all_epochs',index._metadata_decoder.object_decodes==3)
        first=next(iter(rows));changed=index.details[first];changed['metadata']['block']['properties']['frameTimesMs'][0].append(-999)
        check('mutating_public_index_detail_does_not_change_next_result',hashlib.sha256(raw(index.details[first])).hexdigest()==expected[first])
        _,report['warm_single_detail_read']=timed(lambda:index.details[first],repeat=20)
        for lazy in (False,True):
            value,timing=timed(lambda:index.source_projection(source_sha,lazy_details=lazy));report['source_projection_'+('lazy' if lazy else 'eager')]=timing
            check('source_projection_'+('lazy' if lazy else 'eager')+'_preserves_exact_details',verify_details(value['details']) and value['fingerprints']==fingerprints)
        phase[0]='duplicated_index_comparison';baseline=temporary/'duplicated-detail-comparison.sqlite'
        with sqlite3.connect(index.path.as_uri()+'?mode=ro',uri=True) as source_db:
            with sqlite3.connect(baseline) as target:
                source_db.backup(target)
                target.executemany('UPDATE epochs SET detail_blob=? WHERE epoch_uuid=?',[(zlib.compress(raw(value)),key) for key,value in details.items()])
                target.execute('DROP TABLE metadata_objects');target.commit();target.execute('VACUUM')
        report['storage']={'normalized_index':storage(index.path),'duplicated_detail_index_comparison':storage(baseline)}
        with sqlite3.connect(index.path.as_uri()+'?mode=ro',uri=True) as database:
            report['index_sql_bytes']={'objects':database.execute('SELECT COUNT(*),SUM(LENGTH(payload)) FROM metadata_objects').fetchone(),
                'per_epoch_detail_blobs':database.execute('SELECT SUM(LENGTH(detail_blob)) FROM epochs').fetchone()[0]}
        with sqlite3.connect(baseline) as database:
            report['duplicated_detail_blob_bytes']=database.execute('SELECT SUM(LENGTH(detail_blob)) FROM epochs').fetchone()[0]
        cache=ProjectionCache(temporary/'projections');key={'source_sha256':source_sha,'metadata_sha256':manifest['metadata_sha256'],'oracle':'physical-block'}
        phase[0]='projection_write'
        _,report['projection_write']=timed(lambda:cache.write(key,projection))
        phase[0]='projection_read_and_validation';loaded,report['projection_read']=timed(lambda:cache.read(key))
        check('projection_cache_preserves_every_detail_and_fingerprint',loaded is not None and verify_details(loaded['details']) and loaded['fingerprints']==fingerprints and loaded['rows']==rows)
        loaded['details'][first]['metadata']['block']['properties']['frameTimesMs'][0].append(-999)
        reread=cache.read(key);check('projection_public_mutation_does_not_change_stored_result',hashlib.sha256(raw(reread['details'][first])).hexdigest()==expected[first])
        report['storage']['normalized_projection']=storage(temporary/'projections')
        phase[0]='duplicated_projection_comparison';old=temporary/'duplicated-projection-comparison.json.zlib'
        old.write_bytes(zlib.compress(json.dumps({'version':1,'key_hash':checksum(key),'projection':projection},allow_nan=False,separators=(',',':')).encode(),level=1))
        report['storage']['duplicated_projection_comparison']=storage(old)
        report['storage']['all_temporary_artifacts']=storage(temporary)
        check('all_original_input_signatures_unchanged',all(signature(path)==before for path,before in inputs.items()))
        report['source_hashes_after']=hashes();report['source_unchanged']=report['source_hashes_before']==report['source_hashes_after'];report['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()};print(traceback.format_exc(),flush=True)
    finally:
        stopping.set();monitor.join(timeout=2)
        report['peak_temporary_storage_by_phase']=peaks
        report['peak_storage_sampling_note']='20ms sampling of disposable files; each phase includes already-built artifacts. Values are observed lower bounds on instantaneous staging peaks.'
        report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        if index is not None:index.close()
        shutil.rmtree(temporary);report['temporary_artifacts_removed']=not temporary.exists()
        report['passed']=not report.get('error') and report.get('source_unchanged',False) and all(case['passed'] for case in report['cases']) and report['temporary_artifacts_removed']
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    return int(not report['passed'])

if __name__=='__main__':raise SystemExit(main())
