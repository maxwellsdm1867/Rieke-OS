"""Owned auxiliary build; source/base are shared read-only and never copied."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import threading
import time
from storage import physical_assets


def main():
    p=argparse.ArgumentParser();p.add_argument('--implementation-root',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--target',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True);p.add_argument('--verified-corpus',type=Path,required=True);args=p.parse_args()
    verified=json.loads(args.verified_corpus.read_bytes())
    if verified['status']!='seals_counts_generation_verified':raise ValueError('Verify exact corpus before construction')
    sys.path.insert(0,str(args.implementation_root/'python'))
    from disco.metadata.typed_index import build,TypedMetadataIndex
    receipt=dict(status='running',target_commit=subprocess.check_output(['git','-C',str(args.implementation_root),'rev-parse','HEAD'],text=True).strip(),
        corpus=verified,target=str(args.target),source=str(args.source),
        caps=dict(build_seconds=300,max_rss_bytes=1024**3,min_disk_bytes=4*1024**3,min_available_ram_bytes=768*1024**2),
        free_disk_before=shutil.disk_usage(args.target.parent).free,samples=[],progress=[],source_base_copied=False)
    stopped=threading.Event();cancelled=threading.Event();lock=threading.RLock();start=time.perf_counter()
    def save():
        with lock:
            temp=args.receipt.with_suffix('.part');temp.write_text(json.dumps(receipt,indent=2)+'\n');temp.replace(args.receipt)
    def observe(phase):
        assets=[dict(path=args.source,role='shared-native-base',generation=verified['lineage_receipt']['generation']),
                dict(path='/private/tmp/disco-real-million-20261001/typed/sidecar.sqlite',role='retained-baseline-sidecar')]
        assets.extend(dict(path=path,role='candidate-staging-or-temporary') for path in args.target.parent.rglob('*') if path.is_file())
        sample=physical_assets(assets);sample.update(phase=phase,elapsed_seconds=time.perf_counter()-start,free_disk_bytes=shutil.disk_usage(args.target.parent).free)
        with lock:receipt['samples'].append(sample)
    def watch():
        while not stopped.wait(.25):
            try:
                observe('building')
                rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if sys.platform!='darwin':rss*=1024
                free=shutil.disk_usage(args.target.parent).free
                if rss>1024**3 or free<4*1024**3:
                    receipt['resource_reason']='1GiB RSS or 4GiB disk floor';cancelled.set()
            except Exception as error:receipt['resource_reason']=repr(error);cancelled.set()
    observe('before');save();thread=threading.Thread(target=watch,daemon=True);thread.start()
    def progress(value):
        receipt['progress'].append(value);save();print(json.dumps(value),flush=True)
    try:
        result=build(args.source,args.target,max_seconds=300,min_free_gib=4,max_rss_gib=1,
            progress=progress,expected_generation=verified['lineage_receipt']['generation'],
            expected_project_uuid=verified['lineage_receipt']['project_uuid'],cancel_check=cancelled.is_set)
        receipt['build']=result
        opened=time.perf_counter();reader=TypedMetadataIndex(args.target,
            expected_generation=verified['lineage_receipt']['generation'],expected_project_uuid=verified['lineage_receipt']['project_uuid'])
        receipt['typed_verified_open_seconds']=time.perf_counter()-opened
        receipt['candidate_generation_token']=reader.generation_token
        receipt['candidate_seal']=json.loads(Path(str(args.target)+'.sha256.json').read_bytes());reader.close()
        receipt['status']='passed'
    except Exception as error:receipt.update(status='incomplete',error=repr(error))
    finally:
        stopped.set();thread.join();observe('steady-after-build');receipt['wall_seconds']=time.perf_counter()-start
        receipt['observed_highwater_file_bytes']=max(s['total_file_bytes'] for s in receipt['samples'])
        receipt['observed_highwater_allocated_bytes']=max(s['total_allocated_bytes'] for s in receipt['samples'])
        receipt['highwater_definition']='250ms sampled lower bound, includes retained native+baseline+candidate assets; unlinked OS temp pages can be missed'
        receipt['free_disk_after']=shutil.disk_usage(args.target.parent).free;save()
    print(json.dumps({k:receipt.get(k) for k in ('status','wall_seconds','observed_highwater_file_bytes','free_disk_after','error')}),flush=True)
    raise SystemExit(0 if receipt['status']=='passed' else 1)


if __name__=='__main__':main()
