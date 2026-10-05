"""Serial detail and minimal cell-count controls; neither is rendered/native tree UI."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import resource
import signal
import sqlite3
import statistics
import sys
import threading
import time
import uuid
from truth import canonical,digest
from million_worker import load_source,NAMESPACE,signature
from timing import paired


def main():
    p=argparse.ArgumentParser()
    for k in ('root','baseline-root','implementation-root'):p.add_argument('--'+k,type=Path,required=True)
    args=p.parse_args();batch=json.loads((args.root/'batch.json').read_bytes())
    if batch['status']!='complete_ledger_including_incomplete_arms':p.error('Timing batch must finish first')
    verified=json.loads(Path('/tmp/typed-qualification-corpus-verified.json').read_bytes())
    base=Path('/private/tmp/disco-real-million-20261001/base.sqlite');real=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
    target=args.root/'candidate.sqlite';before={str(p):signature(p) for p in (base,real,target)}
    sys.path.insert(0,str(args.baseline_root/'python'))
    import workspace_disk_index as native_module
    if Path(native_module.__file__).resolve()!=(args.baseline_root/'python/workspace_disk_index.py').resolve():
        raise AssertionError('Native comparator did not load from the baseline root')
    sys.path.insert(0,str(args.implementation_root/'python'))
    import disco.metadata.typed_index as candidate_module
    if Path(candidate_module.__file__).resolve()!=(args.implementation_root/'python/disco/metadata/typed_index.py').resolve():
        raise AssertionError('Typed candidate did not load from the implementation root')
    TypedMetadataIndex=candidate_module.TypedMetadataIndex
    reader=TypedMetadataIndex(target,expected_generation=verified['lineage_receipt']['generation'],expected_project_uuid=verified['lineage_receipt']['project_uuid'])
    index=native_module.DiskMetadataIndex();index.path=base;index.generation=verified['lineage_receipt']['generation'];index.project_uuid=verified['lineage_receipt']['project_uuid']
    index._lease=None;index._closed=False;index._signature=native_module._signature(base)
    index._detail_cache=collections.OrderedDict();index._detail_lock=threading.RLock();index._details_reference=None
    index._detail_cache_costs={};index._detail_cache_bytes=0;index._metadata_decoder=native_module.MetadataDecoder()
    c=sqlite3.connect(base.as_uri()+'?mode=ro&immutable=1',uri=True)
    original,_=load_source(real);counts=collections.Counter()
    tails=set(verified['lineage_receipt']['remainder_blocks'])
    for replica in range(360):
        for row in original.values():
            if replica==359 and row['block_uuid'] not in tails:continue
            counts[str(uuid.uuid5(NAMESPACE,f'{replica}/{row["cell_uuid"]}'))]+=1
    ordered=sorted(counts);cursor=ordered[59]
    expected_groups=dict(groups=[dict(uuid=i,count=counts[i]) for i in ordered[60:120]],cursor=ordered[119] if len(ordered)>120 else None)
    def native_groups():
        records=c.execute('SELECT cell_uuid,count(*) FROM epochs WHERE cell_uuid>? GROUP BY cell_uuid ORDER BY cell_uuid LIMIT 61',(cursor,)).fetchall()
        return dict(groups=[dict(uuid=i,count=n) for i,n in records[:60]],cursor=records[59][0] if len(records)>60 else None)
    identities=[str(uuid.uuid5(NAMESPACE,f'0/{original[n]["epoch_uuid"]}')) for n in (1,1000,2781)]
    # Full unchanged native decoder is the authority for this control; independent
    # source metadata reconstruction is separately checked by sealed small truth.
    details=index.details;expected_details={i:details[i] for i in identities}
    jobs=[dict(label='next60_cell_counts',expected=expected_groups,baseline=native_groups,candidate=lambda:reader.groups(cursor=cursor)),
          dict(label='three_full_details',expected=expected_details,baseline=lambda:{i:details[i] for i in identities},candidate=lambda:{i:reader.detail(i) for i in identities})]
    result=dict(status='running',target_commit=batch['target_commit'],baseline_commit='f03577e650ce5f604e9585f5bee983ef01bccad3',ui_timing=False,
        legacy_tree_dto=False,scope='minimal UUID/count group page and three native full decoded details',jobs=[],metadata_generation=index.generation)
    for job in jobs:
        item=paired(job['baseline'],job['candidate'],job['expected'],lambda:{str(p):signature(p) for p in (base,real,target)})
        item['label']=job['label'];result['jobs'].append(item)
    result.update(status='passed' if all(x['status']=='complete' for x in result['jobs']) else 'incomplete',input_signatures_before=before,input_signatures_after={str(p):signature(p) for p in (base,real,target)},
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        limitations=['Native group comparator is raw SQLite epochs cell count projection, not full legacy tree route/DTO/anchor','Details baseline cache primed when freezing native expected values; candidate detail cache policy may differ','No UI render, waveform decode, native MySQL write or cold startup measurement'])
    if before!=result['input_signatures_after']:raise AssertionError('Source generation changed')
    (args.root/'controls.json').write_text(json.dumps(result,indent=2)+'\n');reader.close();index.close();c.close()
    print(json.dumps(dict(status=result['status'],jobs=[x['label'] for x in result['jobs']],peak_rss_bytes=result['peak_rss_bytes'])))


if __name__=='__main__':main()
