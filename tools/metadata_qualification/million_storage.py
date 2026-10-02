"""Post-timing serial storage inspection; exact physical files and scoped ratios."""
import argparse
import hashlib
import json
import signal
import sqlite3
from pathlib import Path
import time
from storage import physical_assets,sqlite_components,normalized,ratio


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--handoff',type=Path,required=True);p.add_argument('--serial-authorized',action='store_true')
    args=p.parse_args()
    batch=json.loads((args.root/'batch.json').read_bytes())
    if not args.serial_authorized or batch['status']!='complete_ledger_including_incomplete_arms':
        p.error('Exclusive serial authorization and finished timing batch required')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300 second storage inspection cap')));signal.alarm(300)
    started=time.perf_counter();base=Path('/private/tmp/disco-real-million-20261001/base.sqlite')
    old=Path('/private/tmp/disco-real-million-20261001/typed/sidecar.sqlite');new=args.root/'candidate.sqlite'
    paths={'native_base':base,'retained_experimental_sidecar':old,'new_candidate_sidecar':new}
    components={role:sqlite_components(path,max_file_bytes=8*1024**3) for role,path in paths.items()}
    with sqlite3.connect(base.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        native_stored_columns={}
        for table,column in [('epochs','row_json'),('epochs','detail_blob'),('metadata_objects','payload'),('field_values','value_json'),('sources','source_json')]:
            count,total,small,large=c.execute(f'SELECT count(*),sum(length(CAST({column} AS BLOB))),min(length(CAST({column} AS BLOB))),max(length(CAST({column} AS BLOB))) FROM {table}').fetchone()
            native_stored_columns[table+'.'+column]=dict(rows=count,stored_payload_bytes=total,min_bytes=small,max_bytes=large,average_bytes=total/count if count else None)
    generation=json.loads(Path('/tmp/typed-qualification-corpus-verified.json').read_bytes())['lineage_receipt']['generation']
    assets=lambda selected:physical_assets([dict(path=paths[r],role=r,generation=generation if r!='retained_experimental_sidecar' else None) for r in selected])
    steady=assets(['native_base','new_candidate_sidecar']);coexist=assets(list(paths))
    runtime_assets=physical_assets([dict(path=path,role=role,generation=generation) for role,path in [('native_base',base),('new_candidate_sidecar',new),('native_preservation_seal',Path(str(base)+'.sha256.json')),('candidate_generation_seal',Path(str(new)+'.sha256.json'))]])
    recording=json.loads((args.handoff/'RECORDING-STORAGE.json').read_bytes())
    reference=json.loads((args.handoff/'STORAGE-BASELINE.json').read_bytes())
    projected=recording['projected_million'];base_bytes=base.stat().st_size;added=new.stat().st_size
    receipt=dict(status='passed_read_only_physical_inspection',generation=generation,
        size_definition='File length, allocated filesystem blocks, dbstat used pages and payload bytes are distinct; no full canonical project size claim',
        steady_candidate=steady,steady_runtime_with_proof_files=runtime_assets,old_new_coexistence=coexist,components=components,native_stored_columns=native_stored_columns,
        normalized=normalized(steady,1000000,77107863,base_bytes=base_bytes,added_bytes=added,
            projected_h5_bytes=projected['approximate_h5_container_bytes'],projected_response_bytes=projected['response_stored_bytes']),
        incremental_added_index_over_native_base=dict(file_bytes=added,bytes_per_epoch=added/1000000,scope='Same sealed million metadata, added complete typed sidecar'),
        new_vs_retained_experimental_index_delta_bytes=added-old.stat().st_size,
        replay_stress_metadata_over_reused_original_h5=ratio(steady['total_file_bytes'],recording['actual_source_file_bytes'],'Reused original H5 files physically present; scope differs from million metadata; stress-fixture ratio only'),
        original_source_ratio_preserved=dict(status='preserved_reference_not_fresh_H5_inspection',epochs=2781,
            metadata_bytes=reference['cases'][0]['base_plus_typed_file_bytes'],actual_h5_bytes=recording['actual_source_file_bytes'],
            percent=recording['actual_source_metadata_sqlite_over_h5_percent']),
        recording_reference_sha256=hashlib.sha256((args.handoff/'RECORDING-STORAGE.json').read_bytes()).hexdigest(),
        growth=dict(status='unrun_controlled_common_layout_curve',reason='Original clone and million sidecar reference have different layouts; no intermediate real-lineage replay built'),
        incremental_import=dict(status='unrun',epochs=None,sources=None,fields=None,distinct_values=None,reason='No independently controlled import mutation workload'),
        lifecycle_cleanup=dict(status='unrun_reader_safe_cleanup',reason='Preserved sidecars remain available; no old-generation deletion or restart test'),
        canonical_project_metadata_bytes=None,persistent_summary_cache_bytes=None,annotation_mapping_bytes=None,
        seconds=time.perf_counter()-started)
    (args.root/'storage.json').write_text(json.dumps(receipt,indent=2)+'\n')
    signal.alarm(0)
    print(json.dumps(dict(status=receipt['status'],seconds=receipt['seconds'],steady_file_bytes=steady['total_file_bytes'],coexist_file_bytes=coexist['total_file_bytes'])))


if __name__=='__main__':main()
