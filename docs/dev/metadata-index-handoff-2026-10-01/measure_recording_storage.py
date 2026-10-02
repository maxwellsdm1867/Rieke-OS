"""Read-only H5 sizes and lineage-weighted million-payload estimates.

Reads headers and hashes files; never decodes waveform values or writes sources.
"""
from pathlib import Path
from collections import defaultdict
import hashlib,json,re,sqlite3,time
import h5py
ROOT=Path(__file__).parent
SOURCE=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
def signature(p):
    s=p.stat();return [s.st_ino,s.st_size,s.st_mtime_ns]
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def main():
    started=time.monotonic();con=sqlite3.connect('file:'+str(SOURCE)+'?mode=ro&immutable=1',uri=True)
    sources=[json.loads(raw) for raw, in con.execute('SELECT source_json FROM sources')]
    epochs={uid:{'id':eid,'source':sha,'block':json.loads(raw)['block_uuid']} for eid,uid,sha,raw in con.execute('SELECT epoch_id,epoch_uuid,source_sha,row_json FROM epochs')}
    replay=json.loads((ROOT/'evidence/disco-real-million-evals/base.receipt.json').read_text());tail=set(replay['remainder_blocks'])
    weights={uid:replay['full_copies']+int(row['block'] in tail) for uid,row in epochs.items()}
    assert sum(weights.values())==1000000
    per_epoch=defaultdict(lambda:defaultdict(int));files=[]
    for source in sources:
        path=Path(source['source_path']);before=signature(path);actual=digest(path)
        assert actual==source['source_sha256'],path
        record={'filename':source['filename'],'source_sha256':actual,'epochs':source['counts']['epochs'],'file_bytes':path.stat().st_size,'allocated_disk_bytes':path.stat().st_blocks*512,'datasets':0,'response_datasets':0,'stimulus_datasets':0,'dataset_stored_bytes':0,'dataset_logical_bytes':0,'response_stored_bytes':0,'response_logical_bytes':0,'stimulus_stored_bytes':0,'stimulus_logical_bytes':0}
        with h5py.File(path,'r') as handle:
            def visit(name,obj):
                if not isinstance(obj,h5py.Dataset):return
                stored=int(obj.id.get_storage_size());logical=int(obj.nbytes)
                record['datasets']+=1;record['dataset_stored_bytes']+=stored;record['dataset_logical_bytes']+=logical
                match=re.search(r'/epochs/epoch-([0-9a-f-]{36})/',name)
                if not match:return
                uid=match[1];assert uid in epochs,name
                kind='response' if '/responses/' in name else 'stimulus' if '/stimuli/' in name else None
                if kind:
                    record[kind+'_datasets']+=1
                    for suffix,amount in [('stored_bytes',stored),('logical_bytes',logical)]:
                        key=kind+'_'+suffix;record[key]+=amount;per_epoch[uid][key]+=amount
            handle.visititems(visit)
        assert signature(path)==before,path
        record['sha256_verified']=True;record['source_stat_unchanged']=True
        files.append(record)
    assert len(per_epoch)==2781,len(per_epoch)
    assert sum(r['response_datasets'] for r in files)==4713
    projected={key:sum(weights[uid]*sizes.get(key,0) for uid,sizes in per_epoch.items()) for key in ['response_stored_bytes','response_logical_bytes','stimulus_stored_bytes','stimulus_logical_bytes']}
    # Whole original files for complete copies, per-source epoch fraction for tail.
    # Container overhead/shared resources make the partial tail an approximation.
    projected_files=0
    for record in files:
        tail_count=sum(row['source']==record['source_sha256'] and row['block'] in tail for row in epochs.values())
        record['tail_epochs']=tail_count
        projected_files+=(359+tail_count/record['epochs'])*record['file_bytes']
    storage=json.loads((ROOT/'STORAGE-BASELINE.json').read_text());original=storage['cases'][0];million=storage['cases'][1]
    raw=sum(r['file_bytes'] for r in files);payload=projected['response_stored_bytes']+projected['stimulus_stored_bytes']
    report={'status':'passed','created_at_unix':time.time(),'method':'Read-only source SHA256 and H5 dataset headers/allocation sizes; no waveform values decoded. Million estimates weighted by exact sealed replay lineage.','actual_source_epochs':2781,'sources':files,'actual_source_file_bytes':raw,'actual_source_response_stored_bytes':sum(r['response_stored_bytes'] for r in files),'actual_source_response_logical_bytes':sum(r['response_logical_bytes'] for r in files),'actual_source_metadata_sqlite_over_h5_percent':100*original['base_plus_typed_file_bytes']/raw,'projected_million':dict(projected,epochs=1000000,approximate_h5_container_bytes=projected_files,metadata_sqlite_bytes=million['base_plus_typed_file_bytes'],metadata_over_approximate_h5_container_percent=100*million['base_plus_typed_file_bytes']/projected_files,metadata_over_stored_response_stimulus_payload_percent=100*million['base_plus_typed_file_bytes']/payload,added_index_over_approximate_h5_container_percent=100*million['added_typed_index_file_bytes']/projected_files),'limitations':['Million recording files were not generated: these are projected sizes, not physical new files.','Header logical bytes include compound quantity/unit fields; they are not float-only scientific sample bytes.','Stored dataset allocation includes dataset compression, not H5 container metadata/shared resources.','Partial-tail H5 container size prorates observed source file size and is approximate.','Canonical MySQL, recovery/logs and other project metadata are excluded from the SQLite numerator.'],'inspection_seconds':time.monotonic()-started,'source_inputs_unchanged':True}
    (ROOT/'RECORDING-STORAGE.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sources'}))
    con.close()
if __name__=='__main__':main()
