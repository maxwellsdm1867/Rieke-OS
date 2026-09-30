"""Dense saved-curation revision fallback, disposable100k SQL-double project."""
import argparse
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from benchmark_service_scale import fixture,Details
from benchmark_epoch_pages import measure
from workspace_disk_index import DiskMetadataIndex
from workspace_service import WorkspaceService
from test_workspace_api import WorkspaceAPITests


def run(count):
    api=WorkspaceAPITests();api.setUp()
    try:
        service,protocol=fixture(count)
        service.project['project_uuid']=api.service.project['project_uuid']
        with tempfile.TemporaryDirectory(prefix='rieke-dense-state-') as folder:
            index=DiskMetadataIndex.build(Path(folder)/'index.sqlite',service.rows,Details(service.rows),
                service.sources,'dense-state-benchmark',service.project['project_uuid'])
            target=api.service
            target.__class__=WorkspaceService
            for name in ('rows','cells','sources','_fingerprints'):
                setattr(target,name,getattr(service,name))
            target.disk_index,target.details=index,index.details
            target.protocols={target.protocol_id:service.protocols[protocol]}
            target.protocols[target.protocol_id]['result']['protocol_uuid']=target.protocol_id
            api.curation.rows.extend({'project_uuid':target.project['project_uuid'],
                'protocol_uuid':target.protocol_id,'epoch_uuid':key,'included':True,
                'tags':['checked'],'review_state':'unreviewed','revision':1,
                'metadata_fingerprint':target._fingerprints[key]} for key in target.rows)
            reader=api.app.extensions['protocol_state_reader']
            target.epoch_page(target.protocol_id,limit=60)
            path=api.base+'/epochs?limit=60'
            read_counts=[]
            def request():
                before=len(api.curation.read_log)
                response=api.client.get(path)
                assert response.status_code==200,response.get_json()
                read_counts.append(len(api.curation.read_log)-before)
                return response.get_json()
            def uncached(protocol,ids):
                result,states,revision=reader.full_state(protocol)
                return {key:states[key] for key in ids},revision,result.get('dataset_binding',{}).get('version',0)
            with patch.object(reader,'read_selected',side_effect=uncached):
                legacy,old=measure(request)
            legacy_reads=read_counts[:];read_counts.clear()
            cold,new=measure(request,1)
            cold_reads=read_counts[:];read_counts.clear()
            repeated,again=measure(request)
            assert old==new==again
            return {'epochs':count,'saved_curation_rows':count,'tags_per_row':1,
                'scope':'Actual Flask GET plus JSON, real sealed SQLite metadata index, transactional SQL-double curation table with one saved tag on every epoch. Excludes real MySQL/network, browser, shared annotations and waveform I/O.',
                'legacy_full_revision_http':legacy,'cache_attempt_cold_http':cold,
                'cache_attempt_repeated_http':repeated,'full_curation_reads':{
                    'legacy_samples':legacy_reads,'cold_sample':cold_reads,'repeated_samples':read_counts},
                'retained_revision_scopes':len(reader.cache),
                'estimated_retained_revision_bytes':sum(item['size'] for item in reader.cache.values()),
                'exact_legacy_response_parity':True}
    finally:
        api.doCleanups()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,default=100000)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.epochs)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
