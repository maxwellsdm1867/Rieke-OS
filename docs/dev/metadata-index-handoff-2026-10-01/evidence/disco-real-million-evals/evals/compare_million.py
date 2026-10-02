"""Bounded same-output comparison on an immutable real-record million replay.
Warm native comparator substitutes a verified compact UUID rank cache for the
production service's eager full-row cache. This excludes eager app startup.
"""
from pathlib import Path
import argparse, collections, hashlib, importlib.util, json, os, resource, signal, sqlite3, statistics, sys, threading, time, shutil, subprocess, re
ROOT=Path('/private/tmp/disco-real-million-20261001')
SOURCE=ROOT/'base.sqlite'
REAL=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
REPO=Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
sys.path[:0]=[str(ROOT/'typed'),str(REPO),'/private/tmp/disco-real-typed-sqlite-20261001/evals',str(ROOT)]
import compare_preview as old
import workspace_predicates as predicates
from workspace_disk_index import DiskMetadataIndex
import workspace_disk_index as native_module
from typed_sidecar import TypedRealSidecar
from typed_bounded import TypedBoundedSidecar
from replay_real import identity_map, select_tail
canonical=old.canonical; digest=old.digest

def save(path,value):
    tmp=path.with_suffix('.part');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

def prepare():
    ids,rows,_,values,fields,sources=old.load_truth()
    con=sqlite3.connect(f'file:{REAL}?mode=ro&immutable=1',uri=True)
    replay_rows=[dict(epoch_id=number,row=rows[identity]) for number,identity in con.execute('SELECT epoch_id,epoch_uuid FROM epochs ORDER BY epoch_id')]
    con.close()
    mappings=identity_map(replay_rows,sources,0)
    cases,_=old.select_scenarios(ids,values,fields)
    selected=[]
    for case in cases:
        if case['label'] in ('largest_cell','largest_block'):
            original=dict(case['scope']); case=dict(case,scope={field:mappings[value] for field,value in original.items()},original_scope=original)
        if case['label'] in ('largest_cell','largest_block','number_eq','array_eq','array_contains','recorded_null','missing','mixed_types','compound_all','compound_any','largest_protocol','global'):
            selected.append(case)
    selected.sort(key=lambda x: ['largest_cell','largest_block','compound_all','array_eq','array_contains','number_eq','recorded_null','missing','mixed_types','compound_any','largest_protocol','global'].index(x['label']))
    tail_numbers,_=select_tail(replay_rows,1621)
    tail={r['row']['epoch_uuid'] for r in replay_rows if r['epoch_id'] in tail_numbers}
    receipt=json.loads((ROOT/'base.receipt.json').read_text())
    for case in selected:
        truth_case=dict(case,scope=case.get('original_scope',case['scope']))
        matched=old.truth_membership(truth_case,ids,values)
        case['expected_count']=len(matched) if 'original_scope' in case else receipt['full_copies']*len(matched)+sum(identity in tail for identity in matched)
    out=dict(cases=selected,facet_fields=['parameters/useRandomSeed','parameters/currentSpotSize'],real_epochs=len(ids),fields=len(fields),tail_epochs=len(tail),source_sha256=old.file_digest(REAL))
    save(ROOT/'evals'/'plan.json',out)
    print(json.dumps(dict(prepared=True,cases=len(selected),counts={c['label']:c['expected_count'] for c in selected})),flush=True)

class Limited(Exception):pass

def worker(args):
    path=ROOT/'evals'/f'{args.arm}{"-bounded" if args.candidate_version=="bounded" else ""}-{args.mode}.json'
    plan=json.loads((ROOT/'evals'/'plan.json').read_text())
    result=dict(pid=os.getpid(),candidate_version=args.candidate_version,arm=args.arm,mode=args.mode,results=[],status='running',caps=dict(process_seconds=360,operation_seconds=45,peak_rss_bytes=1024**3),input_stat=list((SOURCE.stat().st_ino,SOURCE.stat().st_size,SOURCE.stat().st_mtime_ns)))
    save(path,result)
    def cap(*_):raise Limited('45 second operation cap')
    signal.signal(signal.SIGALRM,cap)
    operation_deadline=[time.monotonic()+95]
    def memory_watch():
        last_system=0
        while True:
            reason=None
            if time.monotonic()>operation_deadline[0]:reason='operation hard deadline'
            if time.monotonic()-last_system>2:
                last_system=time.monotonic()
                vm=subprocess.check_output(['/usr/bin/vm_stat'],text=True)
                page_size=int(re.search(r'page size of (\d+)',vm)[1])
                counts={k:int(v) for k,v in re.findall(r'^(Pages[^:]+):\s+(\d+)\.',vm,re.M)}
                available=sum(counts.get(k,0) for k in ('Pages free','Pages inactive','Pages speculative'))*page_size
                if available<768*2**20:reason='768 MiB available RAM floor'
                if shutil.disk_usage(ROOT).free<4*2**30:reason='4 GiB free disk floor'
            if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>1024**3:reason='1 GiB peak RSS cap'
            if reason:
                result.update(status='resource_stop',reason=reason,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                save(path,result);os._exit(91)
            time.sleep(.2)
    threading.Thread(target=memory_watch,daemon=True).start()
    started=time.perf_counter(); arm=None
    try:
        signal.alarm(90)
        candidate=(TypedBoundedSidecar if args.candidate_version=='bounded' else TypedRealSidecar)(ROOT/'typed'/'sidecar.sqlite')
        if args.arm=='native':
            begin=time.perf_counter();seal=json.loads(Path(str(SOURCE)+'.sha256.json').read_text())
            if args.trusted_open:
                prior=json.loads((ROOT/'evals'/'native-page-slow5.json').read_text())
                assert prior['native_open_seconds']>0 and prior['source_stat_unchanged']
                assert result['input_stat']==prior['input_stat']
                native=DiskMetadataIndex();native.path=SOURCE;native.generation=seal['generation'];native.project_uuid=seal['project_uuid']
                native._lease=None;native._closed=False;native._signature=native_module._signature(SOURCE)
                native._catalog_cache=None;native._predicate_cache=None;native._definitions=candidate.definitions;native._epoch_count=1000000
                native._detail_cache=collections.OrderedDict();native._detail_lock=threading.RLock();native._details_reference=None
                native._detail_cache_costs={};native._detail_cache_bytes=0;native._metadata_decoder=native_module.MetadataDecoder()
                result['open_policy']='Warm verified reader reconstructed from prior successful full production open and unchanged file stat; production match/values/catalog methods unchanged'
            else:
                native=DiskMetadataIndex.open(SOURCE,seal['generation'],seal['project_uuid'])
            result['native_open_seconds']=time.perf_counter()-begin
            begin=time.perf_counter();ordinals={};previous=None
            # Verify chronological rank independently of predicates, with bounded
            # streaming memory. Exact row/core equivalence was proven at build.
            for identity,rank,date,start in candidate.connection.execute('SELECT epoch_uuid,sort_rank,date,start_time FROM typed_core ORDER BY sort_rank'):
                current=(date or '',start or '',identity)
                if previous is not None:assert current>previous,'chronology is not strictly increasing'
                assert rank==len(ordinals)+1
                ordinals[identity]=rank;previous=current
            result['rank_cache_seconds']=time.perf_counter()-begin
            result['rank_cache_epochs']=len(ordinals)
            arm=old.NativePreview(native,ordinals)
        else:arm=candidate
        result['setup_seconds']=time.perf_counter()-started
        save(path,result);signal.alarm(0);operation_deadline[0]=time.monotonic()+365
        for case in plan['cases']:
            if args.labels and case['label'] not in args.labels.split(','):continue
            if time.perf_counter()-started>330:
                result.update(status='budget_stop',reason='360 second worker cap');break
            entry=dict(label=case['label'],expected_count=case['expected_count'],predicate=case['predicate'],scope=case['scope'],status='running')
            result['results'].append(entry);save(path,result)
            times=[];checksum=None
            try:
                for _ in range(args.repeats):
                    operation_deadline[0]=time.monotonic()+47;signal.alarm(45);begin=time.perf_counter()
                    kwargs=dict(predicate=case['predicate'],scope=case['scope'],facet_fields=plan['facet_fields'] if args.mode=='facets' else ())
                    page=arm.preview(**kwargs)
                    raw=canonical(page);elapsed=(time.perf_counter()-begin)*1000
                    signal.alarm(0);operation_deadline[0]=time.monotonic()+365
                    assert page['count']==case['expected_count'],(case['label'],page['count'],case['expected_count'])
                    current=hashlib.sha256(raw).hexdigest()
                    if checksum is not None:assert current==checksum,'unstable output'
                    checksum=current;times.append(elapsed)
                    entry.update(samples_ms=times,sha256=checksum,count=page['count'],payload_bytes=len(raw),cursor=page['cursor'])
                    save(path,result)
                entry.update(status='passed',first_ms=times[0],warm_median_ms=statistics.median(times[1:] or times),max_ms=max(times))
                # Check next chronological page and exact native DTOs independently
                # of timed calls; at most 120 rows, no million detail materialization.
                if page['cursor'] and args.arm=='typed':
                    operation_deadline[0]=time.monotonic()+47;signal.alarm(45);next_page=arm.preview(**kwargs,cursor=page['cursor']);signal.alarm(0);operation_deadline[0]=time.monotonic()+365
                    assert next_page['count']==page['count']
                    assert not ({r['epoch_uuid'] for r in page['rows']} & {r['epoch_uuid'] for r in next_page['rows']})
                    entry['next_page_sha256']=digest(next_page)
                for row in page['rows']:
                    native_raw=candidate.connection.execute('SELECT row_json FROM epochs WHERE epoch_uuid=?',(row['epoch_uuid'],)).fetchone()[0]
                    assert canonical(json.loads(native_raw))==canonical(row),'native DTO differs'
                entry['row_dto_oracle_passed']=True
                print(json.dumps(dict(event='case_complete',arm=args.arm,mode=args.mode,label=case['label'],count=page['count'],median_ms=entry['warm_median_ms'],peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)),flush=True)
            except Limited as error:
                signal.alarm(0);entry.update(status='operation_timeout',reason=str(error),samples_ms=times)
                print(json.dumps(dict(event='case_timeout',arm=args.arm,mode=args.mode,label=case['label'])),flush=True)
                # Timeouts on broad queries are retained; continue other cases.
            except Exception as error:
                signal.alarm(0);entry.update(status='failed',error=repr(error),samples_ms=times)
                print(json.dumps(dict(event='case_failed',label=case['label'],error=repr(error))),flush=True)
            result['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            save(path,result)
        if result['status']=='running':result['status']='complete'
    except Exception as error:
        result.update(status='setup_failed',error=repr(error))
        raise
    finally:
        signal.alarm(0)
        if arm:arm.close()
        if args.arm=='native' and 'candidate' in locals():candidate.close()
        result.update(wall_seconds=time.perf_counter()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,input_stat_after=list((SOURCE.stat().st_ino,SOURCE.stat().st_size,SOURCE.stat().st_mtime_ns)))
        result['source_stat_unchanged']=result['input_stat']==result['input_stat_after']
        save(path,result)
        print(json.dumps(dict(event='worker_end',arm=args.arm,mode=args.mode,status=result['status'],seconds=result['wall_seconds'],peak_rss_bytes=result['peak_rss_bytes'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--arm',choices=['native','typed']);p.add_argument('--mode',choices=['page','facets'],default='page');p.add_argument('--repeats',type=int,default=5);p.add_argument('--labels',default='');p.add_argument('--trusted-open',action='store_true');p.add_argument('--candidate-version',choices=['previous','bounded'],default='previous');a=p.parse_args()
    prepare() if a.prepare else worker(a)
