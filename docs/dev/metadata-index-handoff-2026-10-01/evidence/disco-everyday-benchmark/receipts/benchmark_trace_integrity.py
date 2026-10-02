"""Measure fresh-process integrity verification versus bounded trace reading.

Temporary real H5 payloads, 32 and 256 MiB; file caches are warm after writing.
This is not a cold-disk or tens-of-GB production benchmark.
"""
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
import time
import uuid
from unittest.mock import patch
import h5py
import numpy as np
import workspace_service as module
from recording_workspace import digest
from workspace_service import WorkspaceService


def run(size_mib):
    with tempfile.TemporaryDirectory(prefix='rieke-trace-integrity-') as directory:
        path=Path(directory)/'synthetic.h5'
        epoch,stream_id=str(uuid.uuid4()),str(uuid.uuid4())
        with h5py.File(path,'w') as file:
            group=file.create_group('/epochs/'+epoch+'/responses/'+stream_id)
            group.attrs['uuid']=stream_id;group.attrs['sampleRate']=10000.
            group.parent.parent.attrs['uuid']=epoch
            values=np.zeros(200000,dtype=[('quantity','f8'),('units','S8')])
            values['quantity']=np.arange(len(values));values['units']=b'pA'
            group.create_dataset('data',data=values)
            # Actually allocate the payload; no sparse-file timing shortcut.
            padding=file.create_dataset('fixture_payload',(size_mib*1024*1024,),dtype='u1')
            chunk=np.random.default_rng(7).integers(0,256,1024*1024,dtype='u1')
            for offset in range(0,len(padding),len(chunk)):padding[offset:offset+len(chunk)]=chunk
        sha=digest(path)
        service=WorkspaceService.__new__(WorkspaceService)
        service._loaded=True;service._source_signatures={}
        service.rows={epoch:{'epoch_uuid':epoch,'source_sha256':sha,'streams':[
            {'uuid':stream_id,'kind':'responses','h5_path':group.name or '/epochs/'+epoch+'/responses/'+stream_id,
             'sample_rate':10000.,'sample_count':len(values),'units':'pA'}]}}
        service.manifests={sha:{'source_path':str(path),'source_sha256':sha,'source_size':path.stat().st_size}}
        def measured():
            started=time.perf_counter();result=service.trace(epoch,stream_id,start=400,count=20000)
            elapsed=time.perf_counter()-started
            assert result['values']==list(range(400,20400))
            return elapsed
        with patch.object(module,'digest',wraps=digest) as checked:
            first=measured();cold_checks=checked.call_count
            warm=[measured() for _ in range(5)];warm_checks=checked.call_count-cold_checks
        # A same-size content mutation must invalidate the signature and fail.
        with h5py.File(path,'a') as file:file['fixture_payload'][0]=int(file['fixture_payload'][0])^1
        try:service.trace(epoch,stream_id,count=1)
        except ValueError as error:mutation_result=str(error)
        else:raise AssertionError('Changed source must be rejected')
        return {'fixture_payload_mib':size_mib,'file_bytes':path.stat().st_size,
            'first_uncached_integrity_trace_seconds':first,'warm_trace_seconds':warm,
            'warm_median_seconds':statistics.median(warm),'first_full_hash_calls':cold_checks,
            'warm_full_hash_calls':warm_checks,'samples_per_window':20000,
            'same_size_mutation_rejected':mutation_result,
            'limits':'Real temp H5; OS page cache warm after construction; no API/HTTP/browser. Not a cold-disk benchmark.'}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    results=[run(size) for size in (32,256)]
    args.output.write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
