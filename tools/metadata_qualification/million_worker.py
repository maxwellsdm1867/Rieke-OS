"""Serial equal-output warm native/new-core observations over the sealed real replay.

Never imports optimized code into the source oracle; does not publish app state.
The warm native reader initialization avoids original DiskMetadataIndex.open's
lease write into the retained corpus and excludes eager app row startup.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import uuid
from truth import canonical,digest,matches,kind,equal

NAMESPACE=uuid.UUID('8f0a5eed-375e-5ddb-8a57-6d59fce17b28')


def signature(path):
    s=Path(path).stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def rss():
    n=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return n if sys.platform=='darwin' else n*1024


def value_key(v):
    k=kind(v)
    if isinstance(v,list):return k,tuple(value_key(x) for x in v)
    if isinstance(v,dict):return k,tuple(sorted((f,value_key(x)) for f,x in v.items()))
    return k,v


def load_source(path):
    c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    rows={number:json.loads(raw) for number,raw in c.execute('SELECT epoch_id,row_json FROM epochs')}
    values={number:{} for number in rows}
    for number,field,raw in c.execute('SELECT ev.epoch_id,f.field_id,v.value_json FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id)'):
        values[number][field]=json.loads(raw)
    c.close();return rows,values


class NativePreview:
    def __init__(self,index,ranks):self.index=index;self.ranks=ranks
    def membership(self,predicate=None,scope=None):
        if isinstance(scope,dict):
            scope=self.index.match({'all':[dict(field=f,operator='eq',value=v) for f,v in scope.items()]})[1]
        if predicate is not None:ids=self.index.match(predicate,ids=scope)[1]
        elif scope is not None:ids=scope
        else:
            with self.index._connect() as c:ids=[i for i, in c.execute('SELECT epoch_uuid FROM epochs ORDER BY epoch_id')]
        return sorted(ids,key=self.ranks.__getitem__)
    def preview(self,predicate=None,scope=None,facet_fields=()):
        ids=self.membership(predicate,scope)
        selected=ids[:60]
        with self.index._connect(selected) as c:
            rows=[json.loads(raw) for raw, in c.execute('SELECT e.row_json FROM scope s JOIN epochs e USING(epoch_id) ORDER BY s.ordinal')]
        facets={}
        if facet_fields:
            # Preserve historical comparator's eager values matrix and its cost.
            values=dict(self.index.values(ids,facet_fields).items())
            import workspace_predicates as native_predicates
            for field in facet_fields:
                buckets={};present=0
                for i in ids:
                    if field not in values[i]:continue
                    present+=1;value=values[i][field];key=native_predicates.equality_key(value)
                    buckets.setdefault(key,dict(value=value,type=native_predicates.kind(value),count=0))['count']+=1
                facets[field]=dict(values=list(buckets.values())[:60],present_count=present,
                    missing_count=len(ids)-present,values_truncated=len(buckets)>60)
        return dict(count=len(ids),rows=rows,cursor=self.ranks[selected[-1]] if len(ids)>60 else None,facets=facets)


def worker(args):
    verified=json.loads(args.verified_corpus.read_bytes());build=json.loads(args.build_receipt.read_bytes())
    if verified['status']!='seals_counts_generation_verified' or build['status']!='passed':raise ValueError('Verified corpus and completed candidate build required')
    case=json.loads(args.plan.read_bytes())['cases'][args.case]
    facet_fields=json.loads(args.plan.read_bytes())['facet_fields'] if args.mode=='facets' else []
    paths=[args.source,args.real,args.candidate,Path(str(args.candidate)+'.sha256.json')]
    before={str(p):signature(p) for p in paths}
    receipt=dict(status='running',case=case,mode=args.mode,facet_fields=facet_fields,pid=os.getpid(),
        baseline_commit='f03577e650ce5f604e9585f5bee983ef01bccad3',target_commit=args.target_commit,
        caps=dict(sample_seconds=45,max_rss_bytes=1024**3,free_disk_bytes=4*1024**3,min_available_ram_bytes=768*1024**2),
        arms={name:dict(samples_ms=[],status='running') for name in args.arms.split(',')},input_signature=before,
        source_sha256=verified['source_sha256'],replay_sha256=verified['replay_sha256'],
        metadata_generation=verified['lineage_receipt']['generation'],operation='exact count + first60 chronological native DTOs + requested facets + JSON serialization',
        ui_timing=False,legacy_matching_epochs='unchanged unbounded path; not measured here',samples_are_cold_start=False,
        runtime=dict(python=sys.version,sqlite=sqlite3.sqlite_version,platform=platform.platform()))
    lock=threading.RLock();stopped=threading.Event();deadline=[time.monotonic()+180];start=time.perf_counter()
    def save():
        with lock:
            temp=args.receipt.with_suffix('.part');temp.write_text(json.dumps(receipt,indent=2)+'\n');temp.replace(args.receipt)
    save()
    def watch():
        last_ram=0
        while not stopped.wait(.05):
            reason=None
            if rss()>1024**3:reason='1GiB peak RSS cap'
            if time.monotonic()>deadline[0]:reason='operation hard deadline'
            if time.monotonic()-last_ram>2:
                last_ram=time.monotonic()
                import shutil
                if shutil.disk_usage(args.receipt.parent).free<4*1024**3:reason='4GiB free-disk floor'
                if sys.platform=='darwin':
                    raw=subprocess.check_output(['/usr/bin/vm_stat'],text=True)
                    size=int(re.search(r'page size of (\d+)',raw)[1]);counts={k:int(v) for k,v in re.findall(r'^(Pages[^:]+):\s+(\d+)\.',raw,re.M)}
                    available=sum(counts.get(k,0) for k in ('Pages free','Pages inactive','Pages speculative'))*size
                    receipt['last_available_ram_bytes']=available
                    if available<768*1024**2:reason='768MiB available-RAM floor'
            if reason:
                receipt.update(status='resource_stop',reason=reason,peak_rss_bytes=rss(),wall_seconds=time.perf_counter()-start)
                save();print(json.dumps(dict(resource_stop=reason)),flush=True);os._exit(91)
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    native=None;candidate=None
    try:
        sys.path.insert(0,str(args.baseline_root/'python'))
        import workspace_disk_index as native_module
        if Path(native_module.__file__).resolve()!=(args.baseline_root/'python/workspace_disk_index.py').resolve():
            raise AssertionError('Native comparator did not load from the baseline root')
        sys.path.insert(0,str(args.implementation_root/'python'))
        import disco.metadata.typed_index as candidate_module
        if Path(candidate_module.__file__).resolve()!=(args.implementation_root/'python/disco/metadata/typed_index.py').resolve():
            raise AssertionError('Typed candidate did not load from the implementation root')
        TypedMetadataIndex=candidate_module.TypedMetadataIndex
        candidate=TypedMetadataIndex(args.candidate,expected_generation=verified['lineage_receipt']['generation'],expected_project_uuid=verified['lineage_receipt']['project_uuid'])
        source_rows,source_values=load_source(args.real)
        # Independently prove all global ranks, chronology and mapped acquisition UUIDs.
        ranks={};previous=None;global_count=0
        for number,identity,rank in candidate.connection.execute('SELECT epoch_id,epoch_uuid,sort_rank FROM typed_core ORDER BY sort_rank'):
            original=(number-1)%2781+1;replica=(number-1)//2781;row=source_rows[original]
            if identity!=str(uuid.uuid5(NAMESPACE,f'{replica}/{row["epoch_uuid"]}')):raise AssertionError('Replay identity mapping differs')
            current=(row['date'],row['start_time'],identity)
            if previous is not None and current<=previous:raise AssertionError('Independent native chronology differs')
            global_count+=1
            if rank!=global_count:raise AssertionError('Rank sequence differs')
            ranks[identity]=rank;previous=current
        if global_count!=1000000:raise AssertionError('Global completeness differs')
        native=native_module.DiskMetadataIndex();native.path=args.source.resolve();native.generation=verified['lineage_receipt']['generation'];native.project_uuid=verified['lineage_receipt']['project_uuid']
        native._lease=None;native._closed=False;native._signature=native_module._signature(args.source)
        native._catalog_cache=None;native._predicate_cache=None
        with sqlite3.connect(args.source.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
            native._definitions=[json.loads(raw) for raw, in c.execute('SELECT definition_json FROM fields ORDER BY field_no')]
        native._epoch_count=1000000;native._detail_cache=collections.OrderedDict();native._detail_lock=threading.RLock();native._details_reference=None
        native._detail_cache_costs={};native._detail_cache_bytes=0;native._metadata_decoder=native_module.MetadataDecoder()
        baseline=NativePreview(native,ranks)
        receipt['native_open_policy']='Warm reader initialized only after full SHA/count/generation proof; unchanged production match/values methods, compact proven UUID/rank cache, no lease writes to retained corpus; eager app/startup excluded'
        # Independent source membership and exact lineage-weighted completeness.
        original_scope=case.get('original_scope',case.get('scope'))
        source_members={n for n,v in source_values.items() if matches(case['predicate'],v) and
            (not original_scope or all(f in v and equal(v[f],value) for f,value in original_scope.items()))}
        tail_blocks=set(verified['lineage_receipt']['remainder_blocks'])
        tail={n for n,row in source_rows.items() if row['block_uuid'] in tail_blocks}
        expected_count=len(source_members) if 'original_scope' in case else 359*len(source_members)+len(source_members&tail)
        if expected_count!=case['expected_count']:raise AssertionError('Frozen plan count differs from independent source truth')
        where,parameters=candidate._where(case['predicate'],case['scope'])
        ids=[];last_rank=None;count=0;sha=hashlib.sha256();buckets={f:{} for f in facet_fields};present={f:0 for f in facet_fields}
        for number,identity,rank in candidate.connection.execute('SELECT c.epoch_id,c.epoch_uuid,c.sort_rank FROM typed_core c WHERE '+where+' ORDER BY c.sort_rank',parameters):
            original=(number-1)%2781+1
            if original not in source_members:raise AssertionError('Candidate returned nonmatching source lineage')
            if 'original_scope' in case and number>2781:raise AssertionError('Structural scope leaked into another acquisition replica')
            if last_rank is not None and rank<=last_rank:raise AssertionError('Matched chronology differs')
            last_rank=rank;count+=1;sha.update(identity.encode()+b'\n')
            if len(ids)<60:ids.append(identity)
            for field in facet_fields:
                if field not in source_values[original]:continue
                present[field]+=1;value=source_values[original][field];key=value_key(value)
                buckets[field].setdefault(key,dict(value=value,type=kind(value),count=0))['count']+=1
        if count!=expected_count:raise AssertionError('Candidate missed native lineage members')
        with sqlite3.connect(args.source.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
            rows=[json.loads(c.execute('SELECT row_json FROM epochs WHERE epoch_uuid=?',(i,)).fetchone()[0]) for i in ids]
        expected=dict(count=count,rows=rows,cursor=ranks[ids[-1]] if count>60 else None,
            facets={f:dict(values=list(buckets[f].values())[:60],present_count=present[f],missing_count=count-present[f],values_truncated=len(buckets[f])>60) for f in facet_fields})
        expected_hash=digest(expected)
        receipt.update(expected_payload_sha256=expected_hash,expected_count=count,ordered_membership_sha256=sha.hexdigest(),all_members_source_checked=True,
                       independent_full_chronology_mapping=True,setup_seconds=time.perf_counter()-start)
        save();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('45s sample cap')))
        calls={'baseline':lambda:baseline.preview(case['predicate'],case['scope'],facet_fields),
               'candidate':lambda:candidate.preview(case['predicate'],case['scope'],facet_fields=facet_fields)}
        for sample in range(5):
            order=list(receipt['arms'])
            if sample%2:order.reverse()
            for name in order:
                arm=receipt['arms'][name]
                if arm['status']!='running':continue
                if before!={str(p):signature(p) for p in paths}:raise ValueError('Generation changed before sample')
                receipt['current_arm']=name;receipt['current_sample']=sample;save()
                deadline[0]=time.monotonic()+47;signal.alarm(45);started=time.perf_counter()
                try:
                    value=calls[name]();payload=canonical(value);elapsed=(time.perf_counter()-started)*1000
                    if hashlib.sha256(payload).hexdigest()!=expected_hash:raise AssertionError('Independent payload/DTO/cursor/facets differ')
                    if before!={str(p):signature(p) for p in paths}:raise ValueError('Generation changed during sample')
                    arm['samples_ms'].append(elapsed);arm['sha256']=expected_hash;arm['payload_bytes']=len(payload)
                    print(json.dumps(dict(arm=name,label=case['label'],mode=args.mode,sample=sample,ms=elapsed)),flush=True)
                except Exception as error:
                    arm.update(status='incomplete',error=repr(error));print(json.dumps(dict(arm=name,error=repr(error))),flush=True)
                finally:signal.alarm(0);deadline[0]=time.monotonic()+180
                save()
        for arm in receipt['arms'].values():
            s=arm['samples_ms'];arm.update(status='passed' if len(s)==5 else 'incomplete',first_ms=s[0] if s else None,
                warm_median_ms=statistics.median(s[1:]) if len(s)>1 else None,max_ms=max(s) if s else None,p95_ms=None,p99_ms=None)
        receipt['status']='passed' if all(a['status']=='passed' for a in receipt['arms'].values()) else 'incomplete'
        receipt['same_payload_pair']=len(receipt['arms'])==2 and receipt['status']=='passed'
    except Exception as error:receipt.update(status='failed',error=repr(error))
    finally:
        stopped.set();thread.join();signal.alarm(0)
        if native:native.close()
        if candidate:candidate.close()
        receipt.update(wall_seconds=time.perf_counter()-start,peak_rss_bytes=rss(),input_signature_after={str(p):signature(p) for p in paths})
        receipt['source_generations_unchanged']=before==receipt['input_signature_after'];save()
    print(json.dumps(dict(case=case['label'],mode=args.mode,status=receipt['status'])),flush=True)
    return 0 if receipt['status']=='passed' else 1


def main():
    p=argparse.ArgumentParser()
    for key in ('baseline-root','implementation-root','source','real','candidate','verified-corpus','build-receipt','plan','receipt'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--case',type=int,required=True);p.add_argument('--mode',choices=['page','facets'],required=True)
    p.add_argument('--target-commit',required=True);p.add_argument('--arms',default='baseline,candidate')
    raise SystemExit(worker(p.parse_args()))


if __name__=='__main__':main()
