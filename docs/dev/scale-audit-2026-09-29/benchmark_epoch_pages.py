"""Disposable exact before/after protocol-page benchmark, including Flask overhead.

Uses the existing scale fixture and real sealed SQLite index. HTTP routes use
transactional SQL doubles with no saved tags. No real catalog or H5 data is used.
"""
import argparse
import gc
import json
from pathlib import Path
import statistics
import tempfile
import time
from unittest.mock import patch

from benchmark_service_scale import fixture, Details
from workspace_disk_index import DiskMetadataIndex
from test_workspace_api import WorkspaceAPITests


def legacy_page(service, protocol, filters=None, offset=0, limit=100, anchor_uuid=None):
    rows=service.filtered_rows(protocol,filters)
    if anchor_uuid is not None:
        position=next(index for index,row in enumerate(rows) if row['epoch_uuid']==anchor_uuid)
        offset=position//limit*limit
    return {'total':len(rows),'offset':offset,'limit':limit,'epochs':rows[offset:offset+limit]}


def measure(operation,repeats=3):
    samples=[]
    for _ in range(repeats):
        gc.collect()
        started=time.perf_counter();result=operation();samples.append(time.perf_counter()-started)
    return {'median_seconds':statistics.median(samples),'samples_seconds':samples},result


def run(count):
    service,protocol=fixture(count)
    with tempfile.TemporaryDirectory(prefix='rieke-epoch-page-benchmark-') as folder:
        started=time.perf_counter()
        index=DiskMetadataIndex.build(Path(folder)/'index.sqlite',service.rows,Details(service.rows),
            service.sources,'epoch-page-benchmark',service.project['project_uuid'])
        service.disk_index,service.details=index,index.details
        report={'epochs':count,'index_build_seconds':time.perf_counter()-started,
            'scope':'Synthetic one-protocol project. Real sealed SQLite index; no waveform or lab catalog I/O. Flask measurements include JSON and current global query-revision calculation but use SQL doubles with empty saved-curation tables, so exclude database/network latency and dense annotation cost.'}
        for label,filters in [('all',None),('one_cell',{'cell_uuid':next(iter(service.cells))})]:
            before,old=measure(lambda:legacy_page(service,protocol,filters,limit=60))
            cold,new=measure(lambda:service.epoch_page(protocol,filters,limit=60),1)
            after,new=measure(lambda:service.epoch_page(protocol,filters,limit=60))
            assert old==new
            report[label]={'legacy':before,'new_cold':cold,'new_warm':after,'exact_page_parity':True}
        # Use the actual production Flask route to expose its remaining full
        # state/revision computation, separately from service-only timings.
        api=WorkspaceAPITests();api.setUp()
        try:
            target=api.service
            for name in ('rows','details','cells','sources','_fingerprints','disk_index'):
                setattr(target,name,getattr(service,name))
            target.protocols={target.protocol_id:service.protocols[protocol]}
            target.protocols[target.protocol_id]['result']['protocol_uuid']=target.protocol_id
            path=api.base+'/epochs?limit=60'
            def get_page():
                response=api.client.get(path)
                assert response.status_code==200,response.get_json()
                return response.get_json()
            with patch.object(target,'epoch_page',side_effect=lambda *args,**kwargs:legacy_page(target,*args,**kwargs)):
                before,old=measure(get_page)
            after,new=measure(get_page)
            assert old==new
            report['flask_page_empty_curation_sql_double']={'legacy':before,'new':after,'exact_response_parity':True}
        finally:
            api.doCleanups()
        report['retained_epoch_scopes']={'count':len(service._epoch_page_cache[1]),
            'estimated_entry_bytes':sum(item[2] for item in service._epoch_page_cache[1].values())}
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,default=100000)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.epochs)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
