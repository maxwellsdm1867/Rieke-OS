"""Actual Flask100k page before/after exact revision reuse, disposable SQL doubles."""
import argparse
import copy
import json
import sys
from pathlib import Path
import tempfile
from unittest.mock import patch

from benchmark_service_scale import fixture,Details
from benchmark_epoch_pages import measure
from workspace_disk_index import DiskMetadataIndex
from workspace_service import WorkspaceService
from workspace_protocol_state import _exact_equal
from test_workspace_api import WorkspaceAPITests


def run(count):
    api=WorkspaceAPITests();api.setUp()
    try:
        service,protocol=fixture(count)
        service.project['project_uuid']=api.service.project['project_uuid']
        with tempfile.TemporaryDirectory(prefix='rieke-state-benchmark-') as folder:
            index=DiskMetadataIndex.build(Path(folder)/'index.sqlite',service.rows,Details(service.rows),
                service.sources,'state-benchmark',service.project['project_uuid'])
            target=api.service
            target.__class__=WorkspaceService
            for name in ('rows','cells','sources','_fingerprints'):
                setattr(target,name,getattr(service,name))
            target.disk_index,target.details=index,index.details
            target.protocols={target.protocol_id:service.protocols[protocol]}
            target.protocols[target.protocol_id]['result']['protocol_uuid']=target.protocol_id
            reader=api.app.extensions['protocol_state_reader']
            path=api.base+'/epochs?limit=60'
            target.epoch_page(target.protocol_id,limit=60)  # Both HTTP cases use the optimized page service.
            def request():
                response=api.client.get(path)
                assert response.status_code==200,response.get_json()
                return response.get_json()
            def uncached(protocol,ids):
                result,states,revision=reader.full_state(protocol)
                return {key:states[key] for key in ids},revision,result.get('dataset_binding',{}).get('version',0)
            with patch.object(reader,'read_selected',side_effect=uncached):
                baseline,old=measure(request)
            cold,new=measure(request,1)
            assert old==new,'Cold cached path must preserve the exact legacy JSON response'
            assert target.protocol_id in reader.cache,'100k scope must fit the admission budget'
            with patch.object(reader,'full_state',side_effect=AssertionError('No full-state hydration on warm read')):
                warm,again=measure(request)
                calls=[]
                def profile(frame,event,arg):
                    if event=='call' and frame.f_code is api.store._state.__code__:calls.append(1)
                sys.setprofile(profile)
                try:structural=request()
                finally:sys.setprofile(None)
                assert len(calls)==60,len(calls)
            assert again==old==structural
            first=next(iter(target.rows))
            api.store.update(target.protocol_id,[first],{'tags_add':['after-save']},{first:0},
                {first:target._fingerprints[first]},'fixture')
            changed=request()
            _,current,revision=reader.full_state(target.protocol_id)
            assert changed['query_revision']==revision!=old['query_revision']
            assert changed['epochs'][0]['curation']['tags']==['after-save']
            sparse,_=measure(request)
            # Same-version direct SQL edits cannot hide behind a revision counter.
            api.curation.rows[0]['tags']=['same-version-change']
            edited=request()
            assert edited['query_revision']==reader.full_state(target.protocol_id)[2]!=revision
            previous=edited['query_revision']
            target._fingerprints[first]='c'*64
            metadata=request()
            assert metadata['query_revision']==reader.full_state(target.protocol_id)[2]!=previous
            previous=metadata['query_revision']
            api.curation.rows.clear()
            deleted=request()
            assert deleted['query_revision']==reader.full_state(target.protocol_id)[2]!=previous
            proof=reader._metadata(target.protocol_id)
            retained=reader.cache[target.protocol_id]['metadata']
            deepcopy_cost,_=measure(lambda:copy.deepcopy(proof))
            comparison_cost,equal=measure(lambda:reader._metadata_equal(proof,retained))
            assert equal
            query_comparison_cost,equal=measure(lambda:_exact_equal(proof['query'],retained['query']))
            assert equal
            fingerprint_cost,equal=measure(lambda:proof['fingerprints']==retained['fingerprints'])
            assert equal
            # Independently exercise a pinned100k dataset: header-only polls
            # must preserve the immutable recipe and exact legacy revision.
            preview=target.explore_preview({'all':[]},'cell',include_tree=False,include_catalog_summary=False)
            saved=api.explorer_history.create(preview,target.sources,'catalog.json','fixture')
            api.explorer_history.bind(saved['revision_uuid'],target.protocol_id,0,'fixture',{},count)
            target.epoch_page(target.protocol_id,limit=60)
            reader.cache.clear()
            with patch.object(reader,'read_selected',side_effect=uncached):
                bound_baseline,bound_old=measure(request)
            bound_cold,bound_new=measure(request,1)
            assert bound_old==bound_new
            assert target.protocol_id in reader.cache
            with patch.object(reader,'full_state',side_effect=AssertionError('Bound warm read must not hydrate recipe')):
                bound_warm,bound_new=measure(request)
            assert bound_old==bound_new
            bound_proof=reader._metadata(target.protocol_id)
            bound_cell_cost,_=measure(lambda:reader._bound_cells(reader.cache[target.protocol_id]['members'],bound_proof))
            return {'epochs':count,'response_epochs':60,
                'scope':'Actual production Flask GET route and JSON serialization with a real sealed SQLite metadata index. SQL catalog is a disposable transactional double; initial saved-curation/shared-tag rows are empty, then one saved curation row is added. Excludes real MySQL/network latency, dense tags, browser paint and physical waveform I/O.',
                'legacy_full_revision_http':baseline,'verified_cache_cold_http':cold,
                'verified_cache_warm_http':warm,'verified_cache_one_saved_row_warm_http':sparse,
                'cold_proof_deepcopy':deepcopy_cost,'warm_metadata_equality':comparison_cost,
                'warm_typed_query_comparison':query_comparison_cost,'warm_fingerprint_dictionary_equality':fingerprint_cost,
                'bound_protocol':{'legacy_full_revision_http':bound_baseline,'verified_cache_cold_http':bound_cold,
                    'verified_cache_warm_http':bound_warm,'warm_cell_ownership_check':bound_cell_cost,
                    'exact_legacy_response_parity':True},
                'warm_hydrated_curation_states':len(calls),
                'exact_legacy_response_parity':True,'mutation_checks':{
                    'saved_curation_write':True,'same_version_sql_tag_edit':True,'in_place_metadata_fingerprint_change':True,
                    'saved_curation_deletion':True,'pinned_binding':True},
                'cache_scopes':len(reader.cache),'estimated_revision_cache_bytes':sum(item['size'] for item in reader.cache.values()),
                'remaining_linear_checks':'Full fingerprint dictionary equality and typed protocol-metadata comparison occur on each hit. Bound protocols additionally check current cell ownership. Current sparse saved curation and exact shared-annotation snapshot are read every request.'}
    finally:
        api.doCleanups()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,default=100000)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.epochs)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
